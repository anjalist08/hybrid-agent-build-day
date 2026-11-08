"""Answer a voice/text question over the knowledge base with Claude.

Hybrid boundary: only extracted text (titles, handles, topics, dwell) leaves the box,
never screenshots. Claude returns speech + a generative UI screen + an optional action.
"""

import json
import time
from datetime import datetime

import anthropic

from .config import settings
from . import debug
from .db import DB, row_topics
from .kb import app_stats, interests, link_for, search
from .schemas import LensAnswer

SYSTEM = """You are Lens, a personal memory assistant on the user's iPhone. You can see a log
of what the user has read and watched on their phone (X/Twitter, YouTube, Medium, browsers),
captured from screenshots they chose to share, with time spent on each item.

Answer the user's question using ONLY that log. Return:
- speech: 1-3 short, natural sentences that will be read aloud. No markdown, no URLs, no lists.
- ui: a screen built from the component catalog that best shows the answer. Prefer:
  * "timeline" for "what did I watch/read" questions (meta = relative time + dwell, e.g. "2h ago · 45s"),
  * "person" for questions about a specific account or creator,
  * "bar_chart" for "how much / which most" questions (values in minutes),
  * "chips" for topic overviews, "card" for a single highlighted item,
  * "link_button" when the user will likely want to open something.
  Put the item's `link` in `url` so the user can tap through. Keep it to 2-5 components.
- action: kind "open_url" only if the user explicitly asked to open/play/show a specific item; else "none".

If `indexing_backlog.frames_pending` is above 0, the most recent screens are still being read:
when the answer looks incomplete, say so naturally (e.g. "I'm still catching up on the last minute").
If the log has nothing relevant, say so plainly in speech and show what they HAVE been looking at instead.
Never invent items, handles, or links that are not in the log."""

_client: anthropic.Anthropic | None = None


def _claude() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def _ago(ts: float, now: float) -> str:
    d = now - ts
    if d < 90:
        return "just now"
    if d < 3600:
        return f"{int(d // 60)}m ago"
    if d < 86400:
        return f"{int(d // 3600)}h ago"
    return f"{int(d // 86400)}d ago"


def build_context(db: DB, question: str, now: float | None = None, backlog: dict | None = None) -> dict:
    now = now or time.time()
    hits = search(db, question)
    return {
        "now": datetime.fromtimestamp(now).strftime("%A %Y-%m-%d %H:%M"),
        "indexing_backlog": backlog or {"frames_pending": 0, "behind_s": 0},
        "matching_impressions": [
            {
                "app": r["app"],
                "kind": r["kind"],
                "title": r["title"],
                "author": r["author"],
                "summary": r["summary"],
                "topics": row_topics(r),
                "when": _ago(r["ts_end"], now),
                "dwell_s": round(r["dwell_s"]),
                "link": link_for(r["app"], r["kind"], r["title"], r["author"], r["url"]),
            }
            for r in hits
        ],
        "top_topics": interests(db, "topic", 12, now),
        "top_people": interests(db, "person", 8, now),
        "time_by_app_last_7d": app_stats(db, now - 7 * 86400),
    }


def answer(db: DB, question: str, backlog: dict | None = None) -> tuple[LensAnswer, dict]:
    context = build_context(db, question, backlog=backlog)
    asked_at = time.time()
    start = time.perf_counter()
    try:
        response = _claude().messages.parse(
            model=settings.claude_model,
            max_tokens=8000,
            # Voice UX: keep latency down. Raise effort if answers look shallow.
            output_config={"effort": "low"},
            # Server-side fallback: if the model declines, the API reroutes by refusal category.
            extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"},
            extra_body={"fallbacks": "default"},
            system=SYSTEM,
            output_format=LensAnswer,
            messages=[
                {
                    "role": "user",
                    "content": f"<activity_log>\n{json.dumps(context, indent=1)}\n</activity_log>\n\nQuestion: {question}",
                }
            ],
        )
    except anthropic.APIError as e:
        ms = int((time.perf_counter() - start) * 1000)
        db.log_route("query", "cloud", settings.claude_model, ms, False, repr(e))
        debug.query(asked_at, question, context, None, ms, repr(e))
        raise
    ms = int((time.perf_counter() - start) * 1000)
    if response.stop_reason == "refusal" or response.parsed_output is None:
        db.log_route("query", "cloud", settings.claude_model, ms, False, f"stop_reason={response.stop_reason}")
        debug.query(asked_at, question, context, None, ms, f"stop_reason={response.stop_reason}")
        raise RuntimeError(f"no answer (stop_reason={response.stop_reason})")
    sent = len(context["matching_impressions"])
    db.log_route("query", "cloud", settings.claude_model, ms, True, f"{sent} impressions sent as text, 0 images")
    debug.query(asked_at, question, context, response.parsed_output.speech, ms, None)
    route = {"location": "cloud", "model": settings.claude_model, "ms": ms, "impressions_sent": sent, "images_sent": 0}
    return response.parsed_output, route
