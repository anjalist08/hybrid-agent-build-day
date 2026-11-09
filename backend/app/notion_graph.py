"""Lens Research as a knowledge graph of plain Notion pages (what graph views like Graphify read).

  🔭 Lens Research
  ├─ 🧭 <topic>                one page per topic — each topic is a cluster
  │   ├─ 📝 / 🗒️ <post or note>
  │   └─ 🔗 <source the user saw>
  ├─ 🧑‍🔬 People         ─┐
  ├─ 🏢 Organizations    ├─ shared across topics: these bridge the clusters
  └─ 🔑 Key phrases      ─┘

Every page @mentions its neighbours (topic ↔ post ↔ people ↔ organizations ↔ key phrases ↔
sources), so mention-based graph tools draw one connected graph. People, organizations and key
phrases are found by name before creating, so they accumulate across research runs.
"""

import logging
import re

from . import notion
from .notion import _call, _link, _mention, _text, _title

log = logging.getLogger("lens.notion_graph")

SECTIONS = {"people": ("People", "🧑‍🔬"), "orgs": ("Organizations", "🏢"), "phrases": ("Key phrases", "🔑")}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _state() -> dict:
    state = notion._load_state()
    graph = state.setdefault("graph", {})
    if not state.get("hub"):
        state["hub"] = notion._find_hub()
    sections = graph.setdefault("sections", {})
    for key, (name, emoji) in SECTIONS.items():
        if key not in sections:
            sections[key] = _page(state["hub"], name, emoji, [
                _para(f"Everyone and everything Lens has found across your research. Each page links back to its topics.")
            ])
    graph.setdefault("pages", {})
    graph.setdefault("posts", [])
    notion._save_state(state)
    return state


def _page(parent: str, title: str, emoji: str, children: list[dict]) -> str:
    page = _call("POST", "/pages", {
        "parent": {"type": "page_id", "page_id": parent}, "icon": {"type": "emoji", "emoji": emoji},
        "properties": {"title": _title(title)}, "children": children[:95],
    })
    return page["id"]


def _para(text: str, url: str | None = None) -> dict:
    rich = _text(text)
    if url and rich:
        rich[0]["text"]["link"] = {"url": url}
    return {"type": "paragraph", "paragraph": {"rich_text": rich}}


def _heading(text: str) -> dict:
    return {"type": "heading_2", "heading_2": {"rich_text": _text(text)}}


def _bullet(rich: list[dict]) -> dict:
    return {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rich}}


def _entity(state: dict, kind: str, name: str, parent: str, emoji: str, children: list[dict]) -> str:
    """Find-or-create a page for a named entity (kind: topic/person/org/phrase/source)."""
    key = f"{kind}:{_norm(name)}"
    pages = state["graph"]["pages"]
    if key in pages:
        return pages[key]
    pid = _page(parent, name[:200], emoji, children)
    pages[key] = pid
    notion._save_state(state)
    return pid


def existing_titles() -> list[str]:
    try:
        return [f"{p['title']} ({p['type']})" for p in notion._load_state().get("graph", {}).get("posts", [])]
    except Exception:  # noqa: BLE001
        return []


def save(research: dict) -> dict:
    state = _state()
    hub, sections = state["hub"], state["graph"]["sections"]
    topic = research["topic"].strip()

    topic_id = _entity(state, "topic", topic, hub, "🧭", [
        {"type": "callout", "callout": {"rich_text": _text(research.get("summary", "")), "icon": {"emoji": "🧭"}}},
    ])

    org_ids: dict[str, str] = {}
    for o in research.get("organizations", []):
        body = [_para(o.get("what_they_do", ""))]
        if o.get("kind"):
            body.append(_para(o["kind"]))
        if o.get("url"):
            body.append(_para("Website ↗", o["url"]))
        org_ids[o["name"]] = _entity(state, "org", o["name"], sections["orgs"], "🏢", body)

    person_ids: dict[str, str] = {}
    person_orgs: dict[str, list[str]] = {}
    for p in research.get("people", []):
        line = " · ".join(x for x in (p.get("role"), p.get("affiliation"), p.get("handle")) if x)
        body = [_para(line)] if line else []
        if p.get("why_relevant"):
            body.append(_para(p["why_relevant"]))
        if p.get("profile_url"):
            body.append(_para("Profile ↗", p["profile_url"]))
        pid = _entity(state, "person", p["name"], sections["people"], "🧑‍🔬", body)
        person_ids[p["name"]] = pid
        person_orgs[pid] = [oid for name, oid in org_ids.items()
                            if _norm(name) and _norm(name) in _norm(p.get("affiliation") or "")]

    phrase_ids: dict[str, str] = {}
    for k in research.get("key_phrases", []):
        phrase = k["phrase"] if isinstance(k, dict) else str(k)
        meaning = k.get("meaning", "") if isinstance(k, dict) else ""
        phrase_ids[phrase] = _entity(state, "phrase", phrase, sections["phrases"], "🔑",
                                     [_para(meaning)] if meaning else [])

    source_ids: dict[str, str] = {}
    source_authors: dict[str, list[str]] = {}
    for s in research.get("sources", []):
        body = [_para(f"Seen on {s.get('app', 'the web')}")]
        if s.get("url"):
            body.append(_para("Open source ↗", s["url"]))
        sid = _entity(state, "source", s["title"][:180], topic_id, "🔗", body)
        source_ids[s["title"][:180]] = sid
        if s.get("author") in person_ids:
            source_authors[sid] = [person_ids[s["author"]]]

    # The post or note, as a child of its topic.
    kind = "Blog post" if research.get("decision") == "blog_post" else "Note"
    blocks = [{"type": "paragraph", "paragraph": {"rich_text": _text("Topic: ") + [_mention(topic_id)]}},
              {"type": "callout", "callout": {"rich_text": _text(research.get("summary", "")), "icon": {"emoji": "🔭"}}}]
    if research.get("decision_reason"):
        blocks.append(_para(f"{kind} — {research['decision_reason']}"))
    if research.get("key_takeaways"):
        blocks.append(_heading("Key takeaways"))
        blocks += [_bullet(_text(t)) for t in research["key_takeaways"]]
    for section in research.get("sections", []):
        blocks.append(_heading(section["heading"]))
        blocks += [_para(p) for p in section.get("paragraphs", [])]
    if person_ids:
        blocks.append(_heading("Who's talking about it"))
        for p in research.get("people", []):
            extra = ", ".join(x for x in (p.get("role"), p.get("affiliation")) if x)
            blocks.append(_bullet([_mention(person_ids[p["name"]])] + _text(f" — {extra}" if extra else "")))
    if org_ids:
        blocks.append(_heading("Who's building it"))
        for o in research.get("organizations", []):
            blocks.append(_bullet([_mention(org_ids[o["name"]])] + _text(f" — {o.get('what_they_do', '')}")))
    if phrase_ids:
        rich = _text("Key phrases: ")
        for i, pid in enumerate(phrase_ids.values()):
            rich += ([] if i == 0 else _text(", ")) + [_mention(pid)]
        blocks.append({"type": "paragraph", "paragraph": {"rich_text": rich}})
    if source_ids:
        blocks.append(_heading("Sources"))
        blocks += [_bullet([_mention(sid)]) for sid in source_ids.values()]
    blocks.append({"type": "divider", "divider": {}})
    blocks.append(_para("Drafted by Lens from your screen memory and web research. Edit freely."))
    post_id = _page(topic_id, research["title"], "📝" if kind == "Blog post" else "🗒️", blocks)
    state["graph"]["posts"].append({"title": research["title"], "type": kind, "topic": topic, "id": post_id})
    notion._save_state(state)

    # Back-links so every node points at its neighbours.
    people, orgs, phrases, sources = (list(person_ids.values()), list(org_ids.values()),
                                      list(phrase_ids.values()), list(source_ids.values()))
    _link(hub, [("Topics", [topic_id])])
    _link(topic_id, [("Writing", [post_id]), ("Key phrases", phrases), ("People", people),
                     ("Organizations", orgs)])
    for pid in people:
        _link(pid, [("Talks about", [topic_id]), ("Works at", person_orgs.get(pid, [])),
                    ("Shared", [s for s, a in source_authors.items() if pid in a]), ("Featured in", [post_id])])
    for oid in orgs:
        _link(oid, [("Working on", [topic_id]),
                    ("People", [p for p, os in person_orgs.items() if oid in os]), ("Featured in", [post_id])])
    for kid in phrases:
        _link(kid, [("Appears in", [topic_id, post_id])])
    for sid in sources:
        _link(sid, [("About", [topic_id]), ("By", source_authors.get(sid, [])), ("Cited in", [post_id])])

    return {"url": f"https://www.notion.so/{post_id.replace('-', '')}", "type": kind, "title": research["title"],
            "hub_url": f"https://www.notion.so/{hub.replace('-', '')}",
            "people": len(people), "organizations": len(orgs), "sources": len(sources), "key_phrases": len(phrases)}


# ---------------------------------------------------------------- migrate earlier database-based saves


def _plain(block: dict) -> str:
    return "".join(t.get("plain_text", "") for t in block.get(block["type"], {}).get("rich_text", []) or [])


def _has_mention(block: dict) -> bool:
    return any(t.get("type") == "mention" for t in block.get(block["type"], {}).get("rich_text", []) or [])


def _prop_text(page: dict, name: str) -> str:
    prop = page["properties"].get(name, {})
    t = prop.get("type")
    if t in ("title", "rich_text"):
        return "".join(x.get("plain_text", "") for x in prop[t])
    if t == "url":
        return prop["url"] or ""
    if t == "select":
        return (prop["select"] or {}).get("name", "")
    return ""


def migrate_from_databases(extract_phrases=None) -> list[str]:
    """Rebuild each post saved in the old Writing database as pages in the graph structure."""
    state = notion._load_state()
    dbs = state.get("databases")
    if not dbs:
        return []
    done = {p["title"] for p in state.get("graph", {}).get("posts", [])}
    rel = lambda page, prop: [r["id"] for r in page["properties"].get(prop, {}).get("relation", [])]  # noqa: E731
    migrated = []
    for post in _call("POST", f"/databases/{dbs['writing']}/query", {"page_size": 100}).get("results", []):
        title = _prop_text(post, "Name")
        if title in done:
            continue
        topics = [_call("GET", f"/pages/{t}") for t in rel(post, "Topic")]
        topic = _prop_text(topics[0], "Name") if topics else title
        summary = _prop_text(topics[0], "Summary") if topics else ""
        people = []
        for pid in rel(post, "People"):
            pg = _call("GET", f"/pages/{pid}")
            people.append({"name": _prop_text(pg, "Name"), "handle": _prop_text(pg, "Handle"),
                           "affiliation": _prop_text(pg, "Affiliation"), "role": _prop_text(pg, "Role"),
                           "profile_url": _prop_text(pg, "Profile") or None})
        orgs = []
        for oid in rel(post, "Organizations"):
            pg = _call("GET", f"/pages/{oid}")
            orgs.append({"name": _prop_text(pg, "Name"), "url": _prop_text(pg, "Website") or None,
                         "kind": _prop_text(pg, "Kind"), "what_they_do": _prop_text(pg, "What they do")})
        sources = []
        for sid in rel(post, "Sources"):
            pg = _call("GET", f"/pages/{sid}")
            authors = rel(pg, "Author")
            author = next((p["name"] for p in people for a in authors
                           if _prop_text(_call("GET", f"/pages/{a}"), "Name") == p["name"]), None) if authors else None
            sources.append({"title": _prop_text(pg, "Name"), "url": _prop_text(pg, "URL") or None,
                            "app": _prop_text(pg, "App") or "Web", "author": author})
        # Body: keep the writing, drop the old mention lists (rebuilt against the new pages).
        sections, takeaways, heading = [], [], None
        for block in _call("GET", f"/blocks/{post['id']}/children?page_size=100").get("results", []):
            if block["type"].startswith("heading"):
                heading = _plain(block)
                if heading not in ("Key takeaways", "Who's talking about it", "Who's building it", "Sources"):
                    sections.append({"heading": heading, "paragraphs": []})
            elif heading == "Key takeaways" and block["type"] == "bulleted_list_item":
                takeaways.append(_plain(block))
            elif block["type"] == "paragraph" and sections and not _has_mention(block) and _plain(block) \
                    and heading == sections[-1]["heading"]:
                sections[-1]["paragraphs"].append(_plain(block))
            elif block["type"] == "callout" and not summary:
                summary = _plain(block)
        research = {"topic": topic, "title": title, "summary": summary, "key_takeaways": takeaways,
                    "decision": "blog_post" if _prop_text(post, "Type") == "Blog post" else "note",
                    "decision_reason": _prop_text(post, "Why this type"), "sections": sections,
                    "people": people, "organizations": orgs, "sources": sources, "key_phrases": []}
        if extract_phrases:
            research["key_phrases"] = extract_phrases(research)
        save(research)
        migrated.append(title)
    return migrated
