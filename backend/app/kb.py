"""Knowledge base: turns per-frame observations into impressions with dwell time,
links them to entities (topics, people, apps), and scores interests."""

import hashlib
import json
import math
import re
import time
from urllib.parse import quote_plus

from .config import settings
from .db import DB, row_topics
from .schemas import FrameObservation, VisibleItem


def _norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


_APP_ALIASES = {"twitter": "X", "x": "X", "x (twitter)": "X", "youtube": "YouTube", "medium": "Medium",
                "safari": "Safari", "chrome": "Chrome", "google chrome": "Chrome", "google": "Google",
                "instagram": "Instagram", "reddit": "Reddit", "linkedin": "LinkedIn", "tiktok": "TikTok"}


def _norm_app(app: str) -> str:
    return _APP_ALIASES.get(_norm(app), app.strip() or "Unknown")


def item_key(app: str, item: VisibleItem) -> str:
    raw = f"{_norm_app(app)}|{_norm(item.author)}|{_norm(item.title)[:80]}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def link_for(app: str, kind: str, title: str, author: str | None, url: str | None) -> str | None:
    """Best-effort deep link back to the source so the UI can always offer 'open'."""
    if url:
        return url if url.startswith("http") else f"https://{url}"
    q = quote_plus(title[:100])
    app = _norm_app(app)
    if app == "YouTube":
        return f"https://www.youtube.com/results?search_query={q}"
    if app == "X":
        handle = (author or "").lstrip("@").split()[0] if author else ""
        if kind == "profile" and handle:
            return f"https://x.com/{handle}"
        return f"https://x.com/search?q={q}"
    if app == "Medium":
        return f"https://medium.com/search?q={q}"
    return f"https://www.google.com/search?q={q}"


def _upsert_entity(db: DB, etype: str, name: str) -> int | None:
    name = name.strip()
    if not name:
        return None
    db.execute("INSERT OR IGNORE INTO entities(type, name) VALUES (?, ?)", (etype, name))
    return db.query("SELECT id FROM entities WHERE type=? AND name=?", (etype, name))[0]["id"]


def _index_fts(db: DB, impression_id: int) -> None:
    row = db.query("SELECT * FROM impressions WHERE id=?", (impression_id,))[0]
    db.execute("DELETE FROM impressions_fts WHERE rowid=?", (impression_id,))
    db.execute(
        "INSERT INTO impressions_fts(rowid, title, author, summary, topics, app) VALUES (?,?,?,?,?,?)",
        (impression_id, row["title"], row["author"] or "", row["summary"] or "", " ".join(row_topics(row)), row["app"]),
    )


_JUNK_TITLE = re.compile(r"^[\d:.,\s]*[kmb]?\s*(views?|ago|watching|likes?)?\s*$", re.I)


def is_ignored_app(app: str) -> bool:
    return _norm(app) in settings.ignore_apps


def is_junk_title(title: str) -> bool:
    """Durations ("0:40"), counts ("1.2M views"), or near-empty strings aren't content."""
    t = title.strip()
    return len(t) < 4 or bool(_JUNK_TITLE.match(t))


def record_observation(db: DB, obs: FrameObservation, ts: float) -> list[int]:
    """Merge one frame's items into impressions. Returns the impression ids touched."""
    if obs.sensitive or is_ignored_app(obs.app):
        return []
    app = _norm_app(obs.app)
    touched: list[int] = []
    for item in obs.items[:8]:
        if is_junk_title(item.title):
            continue
        key = item_key(app, item)
        topics = sorted({_norm(t) for t in item.topics if t.strip()})[:4]
        existing = db.query(
            "SELECT * FROM impressions WHERE key=? AND ts_end >= ? ORDER BY ts_end DESC LIMIT 1",
            (key, ts - settings.impression_gap_s),
        )
        if existing:
            imp = existing[0]
            merged_topics = sorted(set(row_topics(imp)) | set(topics))[:6]
            ts_end = max(imp["ts_end"], ts)
            db.execute(
                "UPDATE impressions SET ts_end=?, dwell_s=?, frame_count=frame_count+1, topics=?, "
                "url=COALESCE(url, ?) WHERE id=?",
                (ts_end, ts_end - imp["ts_start"] + settings.frame_interval_s, json.dumps(merged_topics),
                 item.url, imp["id"]),
            )
            imp_id = imp["id"]
        else:
            cur = db.execute(
                "INSERT INTO impressions(key, app, kind, title, author, url, summary, topics, ts_start, ts_end, dwell_s) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (key, app, item.kind, item.title.strip()[:300], item.author, item.url, item.summary,
                 json.dumps(topics), ts, ts, settings.frame_interval_s),
            )
            imp_id = cur.lastrowid
            entity_ids = [_upsert_entity(db, "app", app)]
            entity_ids += [_upsert_entity(db, "topic", t) for t in topics]
            if item.author:
                entity_ids.append(_upsert_entity(db, "person", item.author.strip()))
            for eid in filter(None, entity_ids):
                db.execute("INSERT OR IGNORE INTO impression_entities VALUES (?, ?)", (imp_id, eid))
        _index_fts(db, imp_id)
        touched.append(imp_id)
    return touched


def extend_dwell(db: DB, impression_ids: list[int], ts: float) -> None:
    """Called for duplicate frames: the user is still looking at the same thing."""
    for imp_id in impression_ids:
        db.execute(
            "UPDATE impressions SET ts_end=MAX(ts_end, ?), dwell_s=MAX(ts_end, ?) - ts_start + ? WHERE id=?",
            (ts, ts, settings.frame_interval_s, imp_id),
        )


def interests(db: DB, etype: str | None = None, limit: int = 15, now: float | None = None) -> list[dict]:
    """Entities ranked by dwell time with exponential recency decay."""
    now = now or time.time()
    half_life_s = settings.interest_half_life_h * 3600
    sql = (
        "SELECT e.type, e.name, i.dwell_s, i.ts_end FROM entities e "
        "JOIN impression_entities ie ON ie.entity_id=e.id JOIN impressions i ON i.id=ie.impression_id"
    )
    params: tuple = ()
    if etype:
        sql += " WHERE e.type=?"
        params = (etype,)
    scores: dict[tuple[str, str], dict] = {}
    for r in db.query(sql, params):
        decay = math.pow(0.5, max(0.0, now - r["ts_end"]) / half_life_s)
        s = scores.setdefault((r["type"], r["name"]), {"type": r["type"], "name": r["name"], "score": 0.0,
                                                      "impressions": 0, "dwell_s": 0.0})
        s["score"] += r["dwell_s"] * decay
        s["impressions"] += 1
        s["dwell_s"] += r["dwell_s"]
    ranked = sorted(scores.values(), key=lambda s: s["score"], reverse=True)[:limit]
    for s in ranked:
        s["score"] = round(s["score"], 1)
        s["dwell_s"] = round(s["dwell_s"], 1)
    return ranked


def _fts_query(text: str) -> str | None:
    stop = {"what", "have", "been", "about", "the", "and", "for", "with", "that", "this", "show", "tell",
            "watching", "watched", "reading", "read", "browsed", "seen", "did", "today", "week", "who",
            "most", "lately", "recently", "any", "some", "from", "into", "you", "your", "are", "was"}
    words = [w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2 and w not in stop]
    if not words:
        return None
    return " OR ".join(f'"{w}"*' for w in dict.fromkeys(words))


def search(db: DB, text: str, limit: int = 40) -> list[dict]:
    """Full-text match first; fall back to most recent impressions so broad questions still work."""
    rows: list[dict] = []
    q = _fts_query(text)
    if q:
        rows = db.query(
            "SELECT i.* FROM impressions_fts f JOIN impressions i ON i.id=f.rowid "
            "WHERE impressions_fts MATCH ? ORDER BY bm25(impressions_fts), i.dwell_s DESC LIMIT ?",
            (q, limit),
        )
    # "my YouTube activity" -> make sure that app's recent items are in the context.
    lowered = text.lower()
    named_apps = {canon for alias, canon in _APP_ALIASES.items() if re.search(rf"\b{re.escape(alias)}\b", lowered)}
    if named_apps:
        seen = {r["id"] for r in rows}
        marks = ",".join("?" * len(named_apps))
        recent_app = db.query(f"SELECT * FROM impressions WHERE app IN ({marks}) ORDER BY ts_end DESC LIMIT ?",
                              (*named_apps, limit))
        rows = [r for r in recent_app if r["id"] not in seen] + rows
        rows = rows[:limit]
    if len(rows) < 10:
        seen = {r["id"] for r in rows}
        recent = db.query("SELECT * FROM impressions ORDER BY ts_end DESC LIMIT ?", (limit,))
        rows += [r for r in recent if r["id"] not in seen][: limit - len(rows)]
    return rows


def app_stats(db: DB, since: float) -> list[dict]:
    return db.query(
        "SELECT app, COUNT(*) AS impressions, ROUND(SUM(dwell_s)) AS dwell_s FROM impressions "
        "WHERE ts_end >= ? GROUP BY app ORDER BY dwell_s DESC",
        (since,),
    )
