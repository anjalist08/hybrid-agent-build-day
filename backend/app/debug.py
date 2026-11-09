"""Human-readable trail of what Lens saw and what it learned, for tuning extraction.

data/debug/<YYYY-MM-DD>/
  index.md                 every frame in order: thumbnail, items, what the KB did
  HHMMSS-<n>.jpg/.json/.md one set per extracted frame (image skipped for sensitive screens)
  queries.md               every question, what was sent to the cloud, and the answer
data/debug/knowledge.md    current knowledge base snapshot (rewritten after each frame)

Open the .md files in VS Code's Markdown preview (Cmd+Shift+V) to see images inline.
"""

import itertools
import json
import threading
from datetime import datetime
from pathlib import Path

from .config import settings
from .db import DB, row_topics

_lock = threading.Lock()
_seq = itertools.count(1)


def _day_dir(ts: float) -> Path:
    d = settings.debug_dir / datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _hms(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S")


def _append(path: Path, text: str) -> None:
    with _lock, path.open("a", encoding="utf-8") as f:
        f.write(text)


def _md_escape(s: str | None) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ")


def frame(db: DB, *, ts: float, device: str, jpeg: bytes, result, touched: list[int], ignored_reason: str | None,
          behind_s: float) -> None:
    if not settings.debug_dump:
        return
    day = _day_dir(ts)
    stem = f"{datetime.fromtimestamp(ts).strftime('%H%M%S')}-{next(_seq)}"
    obs = result.obs
    sensitive = bool(obs and obs.sensitive)
    if not sensitive:
        (day / f"{stem}.jpg").write_bytes(jpeg)

    rows = db.query(f"SELECT * FROM impressions WHERE id IN ({','.join('?' * len(touched))})", tuple(touched)) \
        if touched else []
    status = "failed" if obs is None else "sensitive" if sensitive else "ignored" if ignored_reason else "ok"
    record = {
        "ts": ts,
        "time": datetime.fromtimestamp(ts).isoformat(timespec="seconds"),
        "device": device,
        "status": status,
        "ignored_reason": ignored_reason,
        "extractor": result.label,
        "ms": result.ms,
        "behind_s": round(behind_s, 1),
        "error": result.error,
        "observation": obs.model_dump() if obs and not sensitive else None,
        "raw_output": result.raw if obs is None else None,
        "impressions": [
            {"id": r["id"], "app": r["app"], "title": r["title"], "author": r["author"],
             "topics": row_topics(r), "dwell_s": round(r["dwell_s"], 1), "frame_count": r["frame_count"],
             "new": r["frame_count"] == 1}
            for r in rows
        ],
    }
    (day / f"{stem}.json").write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [f"## {_hms(ts)} · {obs.app if obs else '—'} · {status} · {result.ms / 1000:.1f}s {result.label}"]
    if behind_s > 10:
        lines.append(f"_processed {behind_s:.0f}s after capture_")
    if not sensitive:
        lines.append(f'<img src="{stem}.jpg" width="220">')
    if result.error:
        lines.append(f"**Error:** `{_md_escape(result.error)[:300]}`")
    if ignored_reason:
        lines.append(f"**Not indexed:** {ignored_reason}")
    if obs and obs.items and not sensitive:
        lines.append("\n| kind | title | author | topics |\n|---|---|---|---|")
        lines += [f"| {i.kind} | {_md_escape(i.title)} | {_md_escape(i.author)} | {', '.join(i.topics)} |"
                  for i in obs.items]
    if rows:
        lines.append("\n**Knowledge base:** " + "; ".join(
            f"{'new' if r['frame_count'] == 1 else 'extended'} #{r['id']} ({r['dwell_s']:.0f}s)" for r in rows))
    lines.append(f"\n[json]({stem}.json)\n\n")
    block = "\n".join(lines)
    (day / f"{stem}.md").write_text(block, encoding="utf-8")
    _append(day / "index.md", block)
    write_knowledge(db)


def duplicate(ts: float, touched: list[int]) -> None:
    if settings.debug_dump:
        _append(_day_dir(ts) / "index.md",
                f"- {_hms(ts)} same screen as before → +dwell on {len(touched)} impression(s)\n\n")


def query(ts: float, question: str, context: dict, answer_speech: str | None, ms: int, error: str | None) -> None:
    if not settings.debug_dump:
        return
    hits = context.get("matching_impressions", [])
    lines = [f"## {_hms(ts)} · “{question}”", f"- sent to cloud: {len(hits)} impressions, 0 images · {ms} ms"]
    if context.get("indexing_backlog", {}).get("frames_pending"):
        lines.append(f"- backlog: {context['indexing_backlog']}")
    lines.append("- top matches: " + "; ".join(f"{h['app']}: {h['title'][:60]}" for h in hits[:8]))
    lines.append(f"- **answer:** {answer_speech}" if answer_speech else f"- **error:** {error}")
    _append(_day_dir(ts) / "queries.md", "\n".join(lines) + "\n\n")


def write_knowledge(db: DB) -> None:
    from . import kb  # local import: kb imports nothing from here, avoids a cycle at module load

    out = ["# Lens knowledge base\n", f"_updated {datetime.now().strftime('%H:%M:%S')}_\n"]
    for etype, label in (("app", "Apps"), ("topic", "Topics"), ("person", "People / channels")):
        out.append(f"\n## {label}\n\n| name | score | impressions | dwell (s) |\n|---|---|---|---|")
        out += [f"| {_md_escape(e['name'])} | {e['score']} | {e['impressions']} | {e['dwell_s']} |"
                for e in kb.interests(db, etype, 15)]
    out.append("\n## Recent impressions\n\n| last seen | app | title | author | topics | dwell (s) |\n|---|---|---|---|---|---|")
    for r in db.query("SELECT * FROM impressions ORDER BY ts_end DESC LIMIT 60"):
        out.append(f"| {_hms(r['ts_end'])} | {r['app']} | {_md_escape(r['title'])[:80]} | {_md_escape(r['author'])} | "
                   f"{', '.join(row_topics(r))} | {r['dwell_s']:.0f} |")
    settings.debug_dir.mkdir(parents=True, exist_ok=True)
    with _lock:
        (settings.debug_dir / "knowledge.md").write_text("\n".join(out) + "\n", encoding="utf-8")
