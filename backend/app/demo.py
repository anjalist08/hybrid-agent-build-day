"""Deterministic, offline demo responses using the existing native UI contract.

No model is called, no screenshots are read, and no external action is returned.
Fixtures are fictional; links deliberately stay unset so Siri cannot launch them.
"""

import time

from . import kb
from .config import settings
from .db import DB
from .schemas import Action, FrameObservation, LensAnswer, UIComponent, UIItem, UIBar, UIScreen, VisibleItem

FIXTURES = (
    ("YouTube", "video", "Building an AI agent from scratch", "Demo Studio", ["ai agents", "tools"], 720),
    ("X", "post", "Why AI agents need better memory", "@demo_alex", ["ai agents", "memory"], 180),
    ("Medium", "article", "A practical guide to local-first AI", "Demo Writer", ["local-first", "ai", "privacy"], 360),
    ("YouTube", "video", "F1 race weekend highlights", "Demo Racing", ["f1", "motorsport"], 540),
)


def seed_demo(db: DB, now: float | None = None) -> None:
    """Seed only an empty DB; repeated startups do not duplicate history."""
    if db.query("SELECT id FROM impressions LIMIT 1"):
        return
    now = time.time() if now is None else now
    for index, (app, kind, title, author, topics, dwell) in enumerate(FIXTURES):
        end = now - (len(FIXTURES) - index) * 1200
        item = VisibleItem(kind=kind, title=title, author=author, url=None, topics=topics,
                           summary=f"Fictional demo content: {title}.")
        ids = kb.record_observation(db, FrameObservation(app=app, screen_kind="detail", sensitive=False,
                                                       items=[item]), end - dwell + settings.frame_interval_s)
        kb.extend_dwell(db, ids, end)
    db.log_route("seed", "local", "fake-demo", 0, True, "SIMULATED: four fictional browsing records seeded")


def answer_demo(db: DB, question: str) -> tuple[LensAnswer, dict]:
    start = time.perf_counter()
    q = question.lower()
    rows = db.query("SELECT * FROM impressions ORDER BY ts_end DESC")
    notice = UIComponent(type="text", body="Demo mode · Fictional browsing history. No AI or external services are called.")
    components = [notice]
    title = "Your demo activity"
    speech = "In this demo, here is a snapshot of your fictional browsing history."
    if not rows:
        title = "A fresh start"
        speech = "Demo mode is on, but your knowledge base is empty. Restart the demo backend to load the sample history."
        components.append(UIComponent(type="text", body=speech))
    elif any(word in q for word in ("open", "play", "打开", "播放")):
        videos = [row for row in rows if row["kind"] == "video"]
        if "agent" in q or " ai" in q:
            videos = [row for row in videos if "ai" in row["title"].lower()]
        elif "f1" in q:
            videos = [row for row in videos if "f1" in row["title"].lower()]
        row = videos[0] if videos else rows[0]
        title = "Your last demo video" if videos else "Your last demo item"
        speech = f"The latest demo item is {row['title']}. It is fictional, so I will not open a real app or link."
        components.append(UIComponent(type="card", title=row["title"], subtitle=row["author"],
                                      body="Preview only · No real video or external action."))
    elif any(word in q for word in ("how much", "how long", "time", "多久", "时间")):
        stats = kb.app_stats(db, 0)
        if "youtube" in q:
            stats = [s for s in stats if s["app"] == "YouTube"]
        minutes = sum(s["dwell_s"] for s in stats) / 60
        title = "Your demo screen time"
        speech = f"In this fictional history, you spent {minutes:g} minutes across the apps shown."
        components.append(UIComponent(type="bar_chart", title="Time by app", subtitle="Fictional minutes · Seeded session",
                                      bars=[UIBar(label=s["app"], value=round(s["dwell_s"] / 60, 1)) for s in stats]))
    elif any(word in q for word in ("who", "creator", "person", "谁")):
        people = kb.interests(db, "person", limit=5)
        if " on x" in q or "twitter" in q:
            authors = {r["author"] for r in rows if r["app"] == "X"}
            people = [p for p in people if p["name"] in authors]
        person = people[0] if people else None
        title = "People in your demo history"
        if person:
            related = [r for r in rows if r["author"] == person["name"]]
            speech = f"In the demo history, {person['name']} is the most viewed creator for this selection."
            components.append(UIComponent(type="person", title=person["name"], subtitle="Fictional demo creator",
                                          body=f"{person['dwell_s'] / 60:g} minutes of sample viewing.",
                                          items=[UIItem(title=r["title"], subtitle=r["app"]) for r in related]))
        else:
            speech = "There is no matching creator in this demo history."
            components.append(UIComponent(type="text", body=speech))
    else:
        if any(word in q for word in ("agent", "ai", "人工智能", "智能体")):
            rows = [r for r in rows if any(t in " ".join((r["title"], r["topics"])).lower() for t in ("ai", "agent"))]
            title = "Your AI rabbit hole"
        elif any(word in q for word in ("f1", "racing", "motorsport", "赛车")):
            rows = [r for r in rows if "f1" in r["title"].lower()]
            title = "Your demo racing highlights"
        else:
            title = "Your demo activity"
            speech = "This demo supports AI topics, creators, screen time, and the latest video. Here is the sample history."
        components.append(UIComponent(type="timeline", title="Recently explored · Demo", items=[
            UIItem(title=r["title"], subtitle=f"{r['app']} · {r['author']}",
                   meta=f"Sample session · {r['dwell_s'] / 60:g} min") for r in rows
        ]))
        if "AI" in title:
            speech = f"In this demo, you explored {len(rows)} items about AI, including agent memory and local-first processing."
    result = LensAnswer(speech=speech, ui=UIScreen(title=title, components=components), action=Action(kind="none"))
    ms = int((time.perf_counter() - start) * 1000)
    db.log_route("query", "local", "fake-demo", ms, True, "SIMULATED: deterministic answer; no outbound calls")
    return result, {"location": "local", "model": "fake-demo", "ms": ms, "simulated": True,
                    "impressions_sent": 0, "images_sent": 0}
