"""Hybrid answer router: decide, per question, whether it can be answered locally or needs the cloud.

Three tiers, cheapest and most private first:

1. **Knowledge-base rules (local, instant, works offline).** Simple lookups over the user's own
   history: time per app, top people, top topics, the last item seen, "what did I watch about X".
   Nothing leaves the machine.
2. **Cloud (Claude).** Open-ended questions that need reasoning: summarize, recommend, explain.
   Only extracted text is sent, never screenshots.
3. **Local LLM (Ollama).** If the cloud is unreachable, fails, or offline mode is on, the local model
   answers the open-ended question instead. If that fails too, the knowledge base answers with
   what it can and says honestly that Lens is offline.

Every answer carries a `route` explaining where it ran, why, and how much text went to the cloud.
"""

import logging
import re
import time
from datetime import datetime

import httpx

from .config import settings
from .db import DB
from .kb import _fts_query, app_stats, interests, link_for
from .query import SYSTEM, _ago, answer_cloud, build_context, user_prompt
from .schemas import Action, LensAnswer, UIBar, UIComponent, UIItem, UIScreen

log = logging.getLogger("lens.router")

# Runtime switches, changeable through POST /mode (e.g. to "unplug" Lens during a demo).
mode: dict = {"router": settings.router_mode, "offline": settings.offline}

ROUTER_MODES = {"auto", "cloud", "local"}

# ---------- Classification ----------

# Words that signal the user wants reasoning, not a lookup. These always go to the cloud when online.
_REASONING = re.compile(
    r"\b(why|summari[sz]e|summary|recommend\w*|suggest\w*|should i|explain|compare|what do you think|"
    r"advice|advise|insights?|patterns?|analy[sz]e|learn(ed|t)?|takeaways?|opinion)\b"
)
_TIME = re.compile(r"\b(how (much|long)|time (did|have) i spen[dt]|time spent|screen ?time|minutes|hours)\b")
_PEOPLE = re.compile(r"\bwho\b.*\b(most|read|watch\w*|follow\w*|see|seen)\b")
_TOPICS = re.compile(r"\b(topics?|interests?|interested in|into lately)\b")
_LAST = re.compile(r"\b(last|latest|most recent)\b")
_OPEN = re.compile(r"^\s*(please\s+)?(open|play|show me|take me to)\b")
_RECALL = re.compile(r"\bwhat (have|did|was) i\b.*\b(watch|read|see|seen|saw|brows|look)\w*")


def classify(question: str) -> tuple[str | None, str]:
    """Returns (local intent or None, human-readable reason)."""
    q = question.lower().strip()
    if _REASONING.search(q):
        return None, "needs reasoning (summarize, recommend or explain)"
    if _TIME.search(q):
        return "time_by_app", "simple lookup: time spent per app"
    if _PEOPLE.search(q):
        return "top_people", "simple lookup: who you read or watch most"
    if _TOPICS.search(q):
        return "top_topics", "simple lookup: your top topics"
    if _OPEN.search(q) or _LAST.search(q):
        return "last_item", "simple lookup: the last item you saw"
    if _RECALL.search(q):
        return "recall", "simple lookup: search your history"
    return None, "open-ended question"


# ---------- Local knowledge-base answers (tier 1) ----------

_KINDS = {"video": "video", "videos": "video", "post": "post", "tweet": "post", "posts": "post",
          "article": "article", "articles": "article", "profile": "profile"}
_APPS = {"youtube": "YouTube", "x": "X", "twitter": "X", "medium": "Medium", "safari": "Safari", "chrome": "Chrome"}


def _dur(seconds: float) -> str:
    s = int(round(seconds))
    if s < 90:
        return f"{s} seconds"
    m = round(s / 60)
    if m < 90:
        return f"{m} minute{'s' if m != 1 else ''}"
    return f"{s / 3600:.1f} hours"


def _short_dur(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s}s" if s < 90 else f"{round(s / 60)}m"


def _today_start(now: float) -> float:
    return datetime.fromtimestamp(now).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


def _timeline_item(r: dict, now: float) -> UIItem:
    who = " · ".join(x for x in (r["author"], r["app"]) if x)
    return UIItem(title=r["title"], subtitle=who or None, meta=f"{_ago(r['ts_end'], now)} · {_short_dur(r['dwell_s'])}",
                  url=link_for(r["app"], r["kind"], r["title"], r["author"], r["url"]))


def _recent(db: DB, limit: int = 5, since: float | None = None) -> list[dict]:
    if since is None:
        return db.query("SELECT * FROM impressions ORDER BY ts_end DESC LIMIT ?", (limit,))
    return db.query("SELECT * FROM impressions WHERE ts_end >= ? ORDER BY ts_end DESC LIMIT ?", (since, limit))


def _answer(speech: str, title: str, components: list[UIComponent], url: str | None = None) -> LensAnswer:
    action = Action(kind="open_url", url=url) if url else Action(kind="none")
    return LensAnswer(speech=speech, ui=UIScreen(title=title, components=components), action=action)


def _nothing_yet(what: str) -> LensAnswer:
    return _answer(f"I haven't seen {what} yet. Start screen capture and I'll start remembering.",
                   "Nothing yet", [UIComponent(type="text", body="Tap the red dot to start screen capture.")])


def _time_by_app(db: DB, q: str, now: float) -> LensAnswer:
    today = "today" in q
    since = _today_start(now) if today else now - 7 * 86400
    label = "today" if today else "this week"
    rows = app_stats(db, since)
    if not rows:
        return _nothing_yet(f"any app use {label}")
    asked = next((name for key, name in _APPS.items() if re.search(rf"\b{key}\b", q)), None)
    focus = next((r for r in rows if r["app"] == asked), None) if asked else rows[0]
    if asked and focus is None:
        speech = f"I haven't seen you on {asked} {label}. You spent the most time on {rows[0]['app']}."
    elif asked:
        speech = f"You've spent about {_dur(focus['dwell_s'])} on {asked} {label}."
    else:
        speech = f"{label.capitalize()} you've spent the most time on {focus['app']}, about {_dur(focus['dwell_s'])}."
    bars = [UIBar(label=r["app"], value=round(r["dwell_s"] / 60, 1)) for r in rows[:6]]
    return _answer(speech, f"Time by app {label}", [
        UIComponent(type="header", title="Minutes per app", subtitle=f"From your on-device history, {label}"),
        UIComponent(type="bar_chart", bars=bars),
    ])


def _top_people(db: DB, q: str, now: float) -> LensAnswer:
    people = interests(db, "person", 5, now)
    if not people:
        return _nothing_yet("any accounts or creators")
    top = people[0]
    items = db.query(
        "SELECT i.* FROM impressions i JOIN impression_entities ie ON ie.impression_id=i.id "
        "JOIN entities e ON e.id=ie.entity_id WHERE e.type='person' AND e.name=? ORDER BY i.ts_end DESC LIMIT 5",
        (top["name"],),
    )
    app = items[0]["app"] if items else None
    components = [UIComponent(
        type="person", title=top["name"], subtitle=app,
        body=f"{top['impressions']} item{'s' if top['impressions'] != 1 else ''} · {_dur(top['dwell_s'])} in total",
        url=link_for(app or "", "profile", top["name"], top["name"], None),
        items=[_timeline_item(r, now) for r in items],
    )]
    if len(people) > 1:
        components.append(UIComponent(type="chips", title="Also often", items=[UIItem(title=p["name"]) for p in people[1:]]))
    speech = f"You've spent the most time with {top['name']}: {top['impressions']} items, about {_dur(top['dwell_s'])}."
    return _answer(speech, "Who you read most", components)


def _top_topics(db: DB, q: str, now: float) -> LensAnswer:
    topics = interests(db, "topic", 10, now)
    if not topics:
        return _nothing_yet("any topics")
    names = [t["name"] for t in topics]
    lead = names[0] if len(names) == 1 else ", ".join(names[:2]) + f" and {names[2]}" if len(names) >= 3 else " and ".join(names)
    return _answer(f"Lately you're most into {lead}.", "Your topics", [
        UIComponent(type="header", title="Your top topics", subtitle="Ranked by time spent, recent first"),
        UIComponent(type="chips", items=[UIItem(title=n) for n in names]),
    ])


def _last_item(db: DB, q: str, now: float) -> LensAnswer:
    kind = next((k for word, k in _KINDS.items() if re.search(rf"\b{word}\b", q)), None)
    rows = (db.query("SELECT * FROM impressions WHERE kind=? ORDER BY ts_end DESC LIMIT 1", (kind,)) if kind
            else _recent(db, 1))
    if not rows:
        return _nothing_yet(f"any {kind}s" if kind else "anything")
    r = rows[0]
    link = link_for(r["app"], r["kind"], r["title"], r["author"], r["url"])
    wants_open = bool(_OPEN.search(q))
    by = f" by {r['author']}" if r["author"] else ""
    speech = f"The last {r['kind']} was “{r['title']}”{by}, on {r['app']}." + (" Opening it now." if wants_open else "")
    return _answer(speech, f"Last {r['kind']}", [
        UIComponent(type="card", title=r["title"], subtitle=f"{r['author'] or r['app']} · {_ago(r['ts_end'], now)}",
                    body=r["summary"], url=link),
        UIComponent(type="link_button", title=f"Open in {r['app']}", url=link),
    ], url=link if wants_open else None)


def _recall(db: DB, q: str, now: float) -> LensAnswer:
    m = re.search(r"\babout (.+?)[?.!]*$", q)
    topic = m.group(1).strip() if m else None
    fts = _fts_query(topic or q)
    rows: list[dict] = []
    if fts:
        rows = db.query(
            "SELECT i.* FROM impressions_fts f JOIN impressions i ON i.id=f.rowid "
            "WHERE impressions_fts MATCH ? ORDER BY bm25(impressions_fts), i.dwell_s DESC LIMIT 8", (fts,))
    if not rows and not topic:
        rows = _recent(db, 8, _today_start(now) if "today" in q else None)
    if not rows:
        recent = _recent(db, 3)
        if not recent:
            return _nothing_yet("anything")
        return _answer(f"I haven't seen anything about {topic or 'that'} yet. Here's what you looked at most recently.",
                       "Nothing about that yet", [UIComponent(type="timeline", title="Recently",
                                                              items=[_timeline_item(r, now) for r in recent])])
    rows.sort(key=lambda r: r["ts_end"], reverse=True)
    longest = max(rows, key=lambda r: r["dwell_s"])
    about = f" about {topic}" if topic else ""
    speech = (f"I found {len(rows)} thing{'s' if len(rows) != 1 else ''}{about}. "
              f"You spent the longest on “{longest['title']}”.")
    return _answer(speech, f"What you saw{about}", [
        UIComponent(type="timeline", title=f"What you saw{about}", items=[_timeline_item(r, now) for r in rows]),
    ])


_RULES = {"time_by_app": _time_by_app, "top_people": _top_people, "top_topics": _top_topics,
          "last_item": _last_item, "recall": _recall}


def answer_local_rules(db: DB, intent: str, question: str, now: float | None = None) -> LensAnswer:
    return _RULES[intent](db, question.lower().strip(), now or time.time())


def offline_fallback(db: DB, now: float | None = None) -> LensAnswer:
    """Last resort when neither the cloud nor the local model can answer an open-ended question."""
    now = now or time.time()
    recent = _recent(db, 5)
    speech = ("I can't reach the cloud right now, so I can't reason about that, "
              "but here's what you've been looking at recently.")
    if not recent:
        return _answer("I can't reach the cloud right now, and I haven't seen anything yet.", "Offline",
                       [UIComponent(type="text", body="Answers that need the cloud will work again when you're back online.")])
    return _answer(speech, "Offline", [
        UIComponent(type="header", title="Offline mode", subtitle="Answered from your on-device history only"),
        UIComponent(type="timeline", title="Recently", items=[_timeline_item(r, now) for r in recent]),
    ])


# ---------- Local LLM answers (tier 3) ----------

def answer_local_llm(db: DB, question: str) -> LensAnswer:
    context = build_context(db, question)
    context["matching_impressions"] = context["matching_impressions"][:20]  # keep the small model fast
    resp = httpx.post(
        f"{settings.ollama_url}/api/chat",
        json={
            "model": settings.ollama_text_model,
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": user_prompt(context, question)}],
            "format": LensAnswer.model_json_schema(),
            "stream": False,
        },
        timeout=settings.local_llm_timeout_s,
    )
    resp.raise_for_status()
    return LensAnswer.model_validate_json(resp.json()["message"]["content"])


# ---------- The router ----------

def _route(location: str, engine: str, model: str, reason: str, intent: str | None, start: float,
           fallback_from: str | None = None, sent: dict | None = None) -> dict:
    sent = sent or {"impressions_sent": 0, "images_sent": 0, "chars_sent": 0}
    return {"location": location, "engine": engine, "model": model, "reason": reason, "intent": intent,
            "offline": mode["offline"], "fallback_from": fallback_from,
            "ms": int((time.perf_counter() - start) * 1000), **sent}


def answer_question(db: DB, question: str) -> tuple[LensAnswer, dict]:
    """Answer a question with the cheapest tier that can handle it. Never raises for network failures."""
    start = time.perf_counter()
    intent, reason = classify(question)
    router = mode["router"]

    if router != "cloud" and intent:
        result = answer_local_rules(db, intent, question)
        route = _route("local", "rules", "knowledge base", reason + ": answered on this machine", intent, start)
        db.log_route("query", "local", "knowledge base", route["ms"], True, route["reason"])
        return result, route

    if router == "local" or mode["offline"]:
        why = "offline mode" if mode["offline"] else "router set to local"
        return _answer_without_cloud(db, question, intent, f"{reason}; {why}", start, fallback_from=None)

    try:
        result, sent = answer_cloud(db, question)
    except Exception as e:  # noqa: BLE001 - network, timeout, API or refusal: all fall back to local
        ms = int((time.perf_counter() - start) * 1000)
        db.log_route("query", "cloud", settings.claude_model, ms, False, repr(e))
        log.warning("cloud answer failed, falling back to local: %r", e)
        return _answer_without_cloud(db, question, intent, f"cloud unavailable ({type(e).__name__})", start,
                                     fallback_from="cloud")
    route = _route("cloud", "claude", settings.claude_model, reason + ": sent to the cloud", intent, start, sent=sent)
    db.log_route("query", "cloud", settings.claude_model, route["ms"], True,
                 f"{route['reason']}; {sent['impressions_sent']} rows, {sent['chars_sent']} chars, 0 images")
    return result, route


def _answer_without_cloud(db: DB, question: str, intent: str | None, reason: str, start: float,
                          fallback_from: str | None) -> tuple[LensAnswer, dict]:
    if intent:
        result = answer_local_rules(db, intent, question)
        route = _route("local", "rules", "knowledge base", reason, intent, start, fallback_from)
        db.log_route("query", "local", "knowledge base", route["ms"], True, route["reason"])
        return result, route
    try:
        result = answer_local_llm(db, question)
        route = _route("local", "ollama", settings.ollama_text_model, reason + ": answered by the local model",
                       intent, start, fallback_from)
        db.log_route("query", "local", settings.ollama_text_model, route["ms"], True, route["reason"])
        return result, route
    except Exception as e:  # noqa: BLE001
        ms = int((time.perf_counter() - start) * 1000)
        db.log_route("query", "local", settings.ollama_text_model, ms, False, repr(e))
        log.warning("local model failed, using knowledge-base fallback: %r", e)
    result = offline_fallback(db)
    route = _route("local", "rules", "knowledge base", reason + "; local model unavailable", intent, start,
                   fallback_from)
    db.log_route("query", "local", "knowledge base", route["ms"], True, route["reason"])
    return result, route


def set_mode(router: str | None = None, offline: bool | None = None) -> dict:
    if router is not None:
        if router not in ROUTER_MODES:
            raise ValueError(f"router must be one of {sorted(ROUTER_MODES)}")
        mode["router"] = router
    if offline is not None:
        mode["offline"] = offline
    return dict(mode)
