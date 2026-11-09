"""Lens Research in Notion: a hub page with five linked databases, written on demand.

  🔭 Lens Research (hub page)
    ├─ Topics         one page per researched topic
    ├─ Writing        blog posts and notes (Type), linked to everything below
    ├─ People         who talks about it: name, handle, affiliation, profile
    ├─ Organizations  startups, labs, companies, universities
    └─ Sources        posts/videos the user actually saw (from screen memory)

Relations are two-way, so graph tools (e.g. Graphify) see every post, person, organization
and source as connected nodes. Entries are found by name before creating, so people and
organizations accumulate across research runs instead of duplicating.
"""

import json
import logging
import os
import threading
import time
from datetime import date

import httpx

from .config import settings

log = logging.getLogger("lens.notion")

API = "https://api.notion.com/v1"
VERSION = "2022-06-28"
_lock = threading.Lock()


class NotionError(Exception):
    pass


def _token() -> str:
    t = os.environ.get("NOTION_TOKEN", "").strip()
    if not t:
        raise NotionError("NOTION_TOKEN is not set on the Lens server.")
    return t


def _call(method: str, path: str, body: dict | None = None) -> dict:
    for attempt in range(4):
        r = httpx.request(method, f"{API}{path}", json=body, timeout=30,
                          headers={"Authorization": f"Bearer {_token()}", "Notion-Version": VERSION,
                                   "Content-Type": "application/json"})
        if r.status_code != 429:
            break
        time.sleep(float(r.headers.get("Retry-After", 1 + attempt)))  # Notion allows ~3 requests/s
    if r.status_code >= 400:
        raise NotionError(f"Notion {method} {path}: {r.status_code} {r.json().get('message', r.text)[:300]}")
    return r.json()


def _text(s: str, limit: int = 1900) -> list[dict]:
    s = (s or "")[:limit]
    return [{"type": "text", "text": {"content": s}}] if s else []


def _title(s: str) -> dict:
    return {"title": _text(s, 200)}


# ---------------------------------------------------------------- workspace setup

_STATE_PATH = None


def _state_path():
    return settings.data_dir / "notion.json"


def _load_state() -> dict:
    try:
        return json.loads(_state_path().read_text())
    except (OSError, ValueError):
        return {}


def _save_state(state: dict) -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    _state_path().write_text(json.dumps(state, indent=2))


def _find_hub() -> str:
    """The 🔭 Lens Research page: reuse it if it exists, else create it at the workspace root."""
    found = _call("POST", "/search", {"query": "Lens Research", "filter": {"property": "object", "value": "page"}})
    for page in found.get("results", []):
        title = "".join(t.get("plain_text", "") for p in page.get("properties", {}).values()
                        if p.get("type") == "title" for t in p["title"])
        if title == "Lens Research" and not page.get("archived"):
            return page["id"]
    page = _call("POST", "/pages", {
        "parent": {"type": "workspace", "workspace": True}, "icon": {"type": "emoji", "emoji": "🔭"},
        "properties": {"title": _title("Lens Research")},
    })
    return page["id"]


def _create_db(hub: str, name: str, emoji: str, properties: dict) -> str:
    db = _call("POST", "/databases", {
        "parent": {"type": "page_id", "page_id": hub}, "icon": {"type": "emoji", "emoji": emoji},
        "title": _text(name), "is_inline": True, "properties": properties,
    })
    return db["id"]


def _relate(db_id: str, prop: str, target_db: str, back_name: str) -> None:
    """Two-way relation db.prop <-> target_db.back_name."""
    _call("PATCH", f"/databases/{db_id}", {"properties": {
        prop: {"relation": {"database_id": target_db, "type": "dual_property",
                            "dual_property": {"synced_property_name": back_name}}}}})


def ensure_workspace() -> dict:
    """Creates the hub and databases once; returns their ids (cached in data/notion.json)."""
    with _lock:
        state = _load_state()
        if state.get("databases"):
            return state
        hub = state.get("hub") or _find_hub()
        sel = lambda *names: {"select": {"options": [{"name": n} for n in names]}}  # noqa: E731
        dbs = {
            "topics": _create_db(hub, "Topics", "🧭", {
                "Name": {"title": {}}, "Summary": {"rich_text": {}}, "Last researched": {"date": {}}}),
            "writing": _create_db(hub, "Writing", "✍️", {
                "Name": {"title": {}}, "Type": sel("Blog post", "Note"), "Status": sel("Draft", "Edited", "Published"),
                "Why this type": {"rich_text": {}}, "Created": {"created_time": {}}}),
            "people": _create_db(hub, "People", "🧑‍🔬", {
                "Name": {"title": {}}, "Handle": {"rich_text": {}}, "Affiliation": {"rich_text": {}},
                "Role": {"rich_text": {}}, "Profile": {"url": {}}, "Seen on": sel("X", "YouTube", "Instagram",
                                                                                    "Facebook", "LinkedIn", "Web")}),
            "orgs": _create_db(hub, "Organizations", "🏢", {
                "Name": {"title": {}}, "Website": {"url": {}},
                "Kind": sel("Startup", "Company", "Research lab", "University", "Nonprofit"),
                "What they do": {"rich_text": {}}}),
            "sources": _create_db(hub, "Sources", "🔗", {
                "Name": {"title": {}}, "URL": {"url": {}}, "App": sel("X", "YouTube", "Instagram", "Facebook", "Web"),
                "Seen": {"date": {}}}),
        }
        # Graph edges (each creates the reverse property on the target too).
        _relate(dbs["writing"], "Topic", dbs["topics"], "Writing")
        _relate(dbs["writing"], "People", dbs["people"], "Writing")
        _relate(dbs["writing"], "Organizations", dbs["orgs"], "Writing")
        _relate(dbs["writing"], "Sources", dbs["sources"], "Writing")
        _relate(dbs["people"], "Topics", dbs["topics"], "People")
        _relate(dbs["people"], "Organizations", dbs["orgs"], "People")
        _relate(dbs["orgs"], "Topics", dbs["topics"], "Organizations")
        _relate(dbs["sources"], "Author", dbs["people"], "Sources")
        _relate(dbs["sources"], "Topics", dbs["topics"], "Sources")
        state = {"hub": hub, "databases": dbs}
        _save_state(state)
        log.info("Created Lens Research workspace in Notion: %s", state)
        return state


# ---------------------------------------------------------------- find-or-create


def _find_by_name(db_id: str, name: str) -> dict | None:
    res = _call("POST", f"/databases/{db_id}/query",
                {"filter": {"property": "Name", "title": {"equals": name[:200]}}, "page_size": 1})
    return (res.get("results") or [None])[0]


def _upsert(db_id: str, name: str, props: dict, merge_relations: tuple[str, ...] = ()) -> str:
    """Create, or update an existing entry (relations in `merge_relations` are unioned)."""
    existing = _find_by_name(db_id, name)
    if existing:
        for rel in merge_relations:
            if rel in props:
                old = [r["id"] for r in existing["properties"].get(rel, {}).get("relation", [])]
                new = [r["id"] for r in props[rel]["relation"]]
                props[rel] = {"relation": [{"id": i} for i in dict.fromkeys(old + new)]}
        _call("PATCH", f"/pages/{existing['id']}", {"properties": props})
        return existing["id"]
    page = _call("POST", "/pages", {"parent": {"database_id": db_id},
                                    "properties": {"Name": _title(name), **props}})
    return page["id"]


def _rel(ids: list[str]) -> dict:
    return {"relation": [{"id": i} for i in ids if i]}


def existing_writing_titles(limit: int = 50) -> list[str]:
    """Titles already in Writing, so the researcher can tell a new angle from a repeat."""
    try:
        state = ensure_workspace()
        res = _call("POST", f"/databases/{state['databases']['writing']}/query", {"page_size": limit})
    except NotionError:
        return []
    out = []
    for page in res.get("results", []):
        title = "".join(t.get("plain_text", "") for t in page["properties"]["Name"]["title"])
        kind = (page["properties"].get("Type", {}).get("select") or {}).get("name", "")
        out.append(f"{title} ({kind})" if kind else title)
    return out


# ---------------------------------------------------------------- page body


def _blocks(research: dict, person_pages: dict[str, str], org_pages: dict[str, str],
            topic_id: str = "", source_pages: dict[str, str] | None = None) -> list[dict]:
    def para(text: str) -> dict:
        return {"type": "paragraph", "paragraph": {"rich_text": _text(text)}}

    def heading(text: str, level: int = 2) -> dict:
        key = f"heading_{level}"
        return {"type": key, key: {"rich_text": _text(text)}}

    def mention_line(page_id: str, label: str, rest: str) -> dict:
        rich = [{"type": "mention", "mention": {"page": {"id": page_id}}}] if page_id else _text(label)
        return {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rich + _text(" — " + rest if rest else "")}}

    blocks = []
    if topic_id:
        blocks.append({"type": "paragraph", "paragraph": {"rich_text": _text("Topic: ") + [_mention(topic_id)]}})
    blocks.append({"type": "callout", "callout": {"rich_text": _text(research["summary"]), "icon": {"emoji": "🔭"}}})
    if research.get("key_takeaways"):
        blocks.append(heading("Key takeaways"))
        blocks += [{"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": _text(t)}}
                   for t in research["key_takeaways"]]
    for section in research.get("sections", []):
        blocks.append(heading(section["heading"]))
        blocks += [para(p) for p in section.get("paragraphs", [])]
    if research.get("people"):
        blocks.append(heading("Who's talking about it"))
        blocks += [mention_line(person_pages.get(p["name"], ""), p["name"],
                                ", ".join(x for x in (p.get("role"), p.get("affiliation")) if x))
                   for p in research["people"]]
    if research.get("organizations"):
        blocks.append(heading("Who's building it"))
        blocks += [mention_line(org_pages.get(o["name"], ""), o["name"], o.get("what_they_do", ""))
                   for o in research["organizations"]]
    if source_pages:
        blocks.append(heading("Sources"))
        blocks += [mention_line(pid, title, "") for title, pid in source_pages.items()]
    blocks.append({"type": "divider", "divider": {}})
    blocks.append(para("Drafted by Lens from your screen memory and web research. Edit freely."))
    return blocks[:95]  # Notion accepts up to 100 children per request


# ---------------------------------------------------------------- save


def save_research(research: dict) -> dict:
    """Writes one research result: topic, people, organizations, sources, then the post/note."""
    state = ensure_workspace()
    dbs = state["databases"]
    topic = research["topic"]
    topic_id = _upsert(dbs["topics"], topic, {
        "Summary": {"rich_text": _text(research["summary"])},
        "Last researched": {"date": {"start": date.today().isoformat()}},
    })

    org_pages: dict[str, str] = {}
    for o in research.get("organizations", []):
        props = {"Topics": _rel([topic_id]), "What they do": {"rich_text": _text(o.get("what_they_do", ""))}}
        if o.get("url"):
            props["Website"] = {"url": o["url"]}
        if o.get("kind") in ("Startup", "Company", "Research lab", "University", "Nonprofit"):
            props["Kind"] = {"select": {"name": o["kind"]}}
        org_pages[o["name"]] = _upsert(dbs["orgs"], o["name"], props, merge_relations=("Topics",))

    person_pages: dict[str, str] = {}
    for p in research.get("people", []):
        props = {"Topics": _rel([topic_id]),
                 "Handle": {"rich_text": _text(p.get("handle") or "")},
                 "Affiliation": {"rich_text": _text(p.get("affiliation") or "")},
                 "Role": {"rich_text": _text(p.get("role") or "")}}
        if p.get("profile_url"):
            props["Profile"] = {"url": p["profile_url"]}
        if p.get("seen_on") in ("X", "YouTube", "Instagram", "Facebook", "LinkedIn", "Web"):
            props["Seen on"] = {"select": {"name": p["seen_on"]}}
        affiliated = [org_pages[o] for o in org_pages if o.lower() in (p.get("affiliation") or "").lower()]
        if affiliated:
            props["Organizations"] = _rel(affiliated)
        person_pages[p["name"]] = _upsert(dbs["people"], p["name"], props,
                                          merge_relations=("Topics", "Organizations"))

    source_pages: dict[str, str] = {}
    source_authors: dict[str, list[str]] = {}
    for s in research.get("sources", []):
        props = {"Topics": _rel([topic_id])}
        if s.get("url"):
            props["URL"] = {"url": s["url"]}
        if s.get("app") in ("X", "YouTube", "Instagram", "Facebook", "Web"):
            props["App"] = {"select": {"name": s["app"]}}
        if s.get("author") in person_pages:
            props["Author"] = _rel([person_pages[s["author"]]])
        sid = _upsert(dbs["sources"], s["title"][:180], props, merge_relations=("Topics",))
        source_pages[s["title"][:180]] = sid
        if s.get("author") in person_pages:
            source_authors[sid] = [person_pages[s["author"]]]

    kind = "Blog post" if research.get("decision") == "blog_post" else "Note"
    page = _call("POST", "/pages", {
        "parent": {"database_id": dbs["writing"]},
        "icon": {"type": "emoji", "emoji": "📝" if kind == "Blog post" else "🗒️"},
        "properties": {
            "Name": _title(research["title"]),
            "Type": {"select": {"name": kind}},
            "Status": {"select": {"name": "Draft"}},
            "Why this type": {"rich_text": _text(research.get("decision_reason", ""))},
            "Topic": _rel([topic_id]),
            "People": _rel(list(person_pages.values())),
            "Organizations": _rel(list(org_pages.values())),
            "Sources": _rel(list(source_pages.values())),
        },
        "children": _blocks(research, person_pages, org_pages, topic_id, source_pages),
    })
    person_orgs = {person_pages[p["name"]]: [org_pages[o] for o in org_pages
                                             if o.lower() in (p.get("affiliation") or "").lower()]
                   for p in research.get("people", []) if p["name"] in person_pages}
    connect_graph(state["hub"], topic_id, [page["id"]], list(person_pages.values()), list(org_pages.values()),
                  list(source_pages.values()), person_orgs, source_authors)
    hub_url = f"https://www.notion.so/{state['hub'].replace('-', '')}"
    return {"url": page.get("url", hub_url), "type": kind, "title": research["title"], "hub_url": hub_url,
            "people": len(person_pages), "organizations": len(org_pages), "sources": len(source_pages)}


# ---------------------------------------------------------------- knowledge-graph mentions


def _mention(page_id: str) -> dict:
    return {"type": "mention", "mention": {"page": {"id": page_id}}}


def _mentioned_ids(page_id: str) -> set[str]:
    """Pages already @mentioned in a page's body (so re-runs don't repeat lines)."""
    found: set[str] = set()
    cursor = None
    for _ in range(5):
        res = _call("GET", f"/blocks/{page_id}/children?page_size=100" + (f"&start_cursor={cursor}" if cursor else ""))
        for block in res.get("results", []):
            for rt in block.get(block.get("type", ""), {}).get("rich_text", []) or []:
                if rt.get("type") == "mention" and rt["mention"].get("type") == "page":
                    found.add(rt["mention"]["page"]["id"].replace("-", ""))
        if not res.get("has_more"):
            break
        cursor = res.get("next_cursor")
    return found


def _link(page_id: str, lines: list[tuple[str, list[str]]]) -> None:
    """Append "Label: @A, @B" lines to a page, skipping pages it already mentions."""
    already = _mentioned_ids(page_id)
    blocks = []
    for label, targets in lines:
        new = [t for t in dict.fromkeys(targets) if t and t.replace("-", "") not in already
               and t.replace("-", "") != page_id.replace("-", "")]
        if not new:
            continue
        rich = _text(f"{label}: ")
        for i, t in enumerate(new[:40]):
            rich += ([] if i == 0 else _text(", ")) + [_mention(t)]
            already.add(t.replace("-", ""))
        blocks.append({"type": "paragraph", "paragraph": {"rich_text": rich}})
    if blocks:
        _call("PATCH", f"/blocks/{page_id}/children", {"children": blocks})


def connect_graph(hub: str, topic: str, writing: list[str], people: list[str], orgs: list[str], sources: list[str],
                  person_orgs: dict[str, list[str]], source_authors: dict[str, list[str]]) -> None:
    """@mentions in every page body, so mention-based graph views (e.g. Graphify) see one connected graph:
    hub → topics → posts/people/orgs/sources, people ↔ orgs, sources → authors."""
    _link(hub, [("Topics", [topic])])
    _link(topic, [("Writing", writing), ("People", people), ("Organizations", orgs), ("Sources", sources)])
    for pid in people:
        _link(pid, [("Talks about", [topic]), ("Works at", person_orgs.get(pid, [])),
                    ("Shared", [s for s, authors in source_authors.items() if pid in authors]),
                    ("Featured in", writing)])
    for oid in orgs:
        _link(oid, [("Working on", [topic]), ("People", [p for p, os in person_orgs.items() if oid in os]),
                    ("Featured in", writing)])
    for sid in sources:
        _link(sid, [("About", [topic]), ("By", source_authors.get(sid, [])), ("Cited in", writing)])


def backfill_mentions() -> int:
    """Add the graph mentions to everything already saved (reads the database relations)."""
    state = ensure_workspace()
    dbs = state["databases"]
    rel = lambda page, prop: [r["id"] for r in page["properties"].get(prop, {}).get("relation", [])]  # noqa: E731
    posts = _call("POST", f"/databases/{dbs['writing']}/query", {"page_size": 100}).get("results", [])
    for post in posts:
        people, orgs, sources = rel(post, "People"), rel(post, "Organizations"), rel(post, "Sources")
        person_orgs = {pid: rel(_call("GET", f"/pages/{pid}"), "Organizations") for pid in people}
        source_authors = {sid: rel(_call("GET", f"/pages/{sid}"), "Author") for sid in sources}
        for topic in rel(post, "Topic") or [""]:
            if topic:
                _link(post["id"], [("Topic", [topic]), ("Sources", sources)])
                connect_graph(state["hub"], topic, [post["id"]], people, orgs, sources, person_orgs, source_authors)
    return len(posts)
