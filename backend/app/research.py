"""On-demand topic research: screen memory (local) + web (Claude web search) -> blog post or note.

Nothing is written anywhere until the user taps "Add to Notion" (save_to_notion tool). The
local step sends only the matching text rows (titles, handles), never screenshots.
"""

import json
import logging
import secrets
import time
from typing import Literal

import anthropic
from pydantic import BaseModel, Field

from . import kb, notion
from .config import settings
from .db import DB

log = logging.getLogger("lens.research")

_results: dict[str, dict] = {}


class Person(BaseModel):
    name: str = Field(description="Real full name")
    handle: str | None = Field(description="Social handle if known, e.g. @karpathy")
    affiliation: str | None = Field(description="University, lab or company")
    role: str | None = Field(description="e.g. 'Professor of CS', 'Founder & CEO'")
    profile_url: str | None = Field(description="Homepage, Google Scholar, X or LinkedIn URL found on the web")
    seen_on: Literal["X", "YouTube", "Instagram", "Facebook", "LinkedIn", "Web"] | None
    why_relevant: str = Field(description="One sentence: what they said or do about the topic")


class Organization(BaseModel):
    name: str
    url: str | None
    kind: Literal["Startup", "Company", "Research lab", "University", "Nonprofit"]
    what_they_do: str = Field(description="One sentence on their work on this topic")


class Source(BaseModel):
    title: str
    url: str | None
    app: Literal["X", "YouTube", "Instagram", "Facebook", "Web"]
    author: str | None = Field(description="Exact name from `people` if the author is one of them")


class Section(BaseModel):
    heading: str
    paragraphs: list[str]


class Research(BaseModel):
    topic: str
    title: str = Field(description="Post or note title")
    decision: Literal["blog_post", "note"]
    decision_reason: str = Field(description="One sentence on why this is a blog post (unique angle) or a note")
    summary: str = Field(description="2-3 sentence summary")
    key_takeaways: list[str]
    sections: list[Section]
    people: list[Person]
    organizations: list[Organization]
    sources: list[Source]


_client: anthropic.Anthropic | None = None


def _claude() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def _web_research(topic: str, seen: list[dict]) -> str:
    """Claude with web search: who is who, who builds what. Returns research notes with URLs."""
    seen_lines = "\n".join(f"- {s['app']} · {s.get('author') or '?'} · {s['title']}" for s in seen[:25]) or "(nothing)"
    messages = [{"role": "user", "content": f"""Research this topic for a personal knowledge base: "{topic}".

What the user recently saw about it on their phone (from their own screen memory):
{seen_lines}

Use web search to find:
1. For each author/handle above that matters: their real name, current affiliation (university, lab or company), role, and a profile URL.
2. 2-3 other notable people actively commenting on or researching this topic, with affiliation and profile URL.
3. 2-3 startups, companies or research labs working on it, with their website and one line on what they do.
4. What is genuinely new or contested about the topic right now.

Be brief: short bullet notes with every URL you rely on. Do not invent people, affiliations or links."""}]
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 3}]
    notes = []
    for _ in range(4):  # continue across pause_turn
        resp = _claude().messages.create(model=settings.claude_model, max_tokens=12000,
                                         output_config={"effort": "low"}, tools=tools, messages=messages)
        notes += [b.text for b in resp.content if b.type == "text"]
        if resp.stop_reason != "pause_turn":
            break
        messages.append({"role": "assistant", "content": resp.content})
    return "\n".join(notes)


def research_topic(db: DB, topic: str) -> dict:
    start = time.perf_counter()
    seen = kb.recall(db, topic, limit=25)["items"]
    existing = notion.existing_writing_titles()
    notes = _web_research(topic, seen)
    web_ms = int((time.perf_counter() - start) * 1000)

    resp = _claude().messages.parse(
        model=settings.claude_model, max_tokens=16000, output_config={"effort": "low"}, output_format=Research,
        messages=[{"role": "user", "content": f"""Turn this research into a structured entry for the user's Notion.

Topic: {topic}

Seen by the user (screen memory, JSON): {json.dumps(seen[:25])}

Web research notes:
{notes}

Already in the user's Notion "Writing" database: {json.dumps(existing) if existing else "nothing yet"}

Decide the format:
- "blog_post" only if the angle is unique: not already covered in their Notion above, and more than a generic
  rehash of a well-known topic (e.g. it connects what they saw with who is working on it in a fresh way).
  Then write 2 short sections of 1-2 paragraphs each, in a clear first-person blog voice (brief — this is a draft).
- Otherwise "note": 1 short section of 2-4 one-line paragraphs, for the user to build on later.
Keep everything concise: at most 3 key takeaways, at most 4 people, at most 3 organizations, at most 5 sources.
People must be real and come from the notes or the seen items; keep only those with a known affiliation or
clear relevance. Sources are the items the user actually saw (with their links), plus at most 3 key web sources."""}],
    )
    if resp.parsed_output is None:
        raise RuntimeError(f"research structuring failed (stop_reason={resp.stop_reason})")
    result = resp.parsed_output.model_dump()
    rid = "res_" + secrets.token_hex(4)
    _results[rid] = result
    ms = int((time.perf_counter() - start) * 1000)
    db.log_route("research", "cloud", settings.claude_model, ms, True,
                 f"{len(seen)} memory items as text + web search ({web_ms} ms), 0 images")
    log.info("research %s on %r: %s, %d people, %d orgs in %d ms", rid, topic, result["decision"],
             len(result["people"]), len(result["organizations"]), ms)
    return {"research_id": rid, "seen_count": len(seen), "already_in_notion": existing[:10], **result}


def save_to_notion(research_id: str) -> dict:
    research = _results.get(research_id)
    if research is None:
        raise notion.NotionError("That research expired (server restarted). Ask me to research it again.")
    return notion.save_research(research)
