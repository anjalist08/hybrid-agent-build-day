"""Scripted concert CUJ adapter, enabled only by the fake-mode HTTP routes.

All people, event details and provider effects are fixtures. Session state really
persists in the isolated demo SQLite DB; no real memory or connected app is used.
"""
import json
import re
import time
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field

from .db import DB

EVENT = {"artist": "Maggie Rogers", "venue": "Fox Theater", "city": "Oakland, CA",
         "date": "Friday, Nov 13, 2026", "time": "8–10:30 PM", "doors": "7 PM · All ages",
         "address": "1807 Telegraph Ave, Oakland"}
TICKETS = [
    {"id": "standing", "price": 65, "title": "Standing", "detail": "General admission · Floor", "seated": False},
    {"id": "seated", "price": 85, "title": "Seated", "detail": "Reserved balcony · Row J", "seated": True},
    {"id": "view", "price": 95, "title": "Seated, Better View", "detail": "Reserved loge · Row C · Center", "seated": True},
]


class CUJRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9-]+$")
    action: Literal["start", "search", "refine", "select", "invite", "calendar", "remember", "ask"]
    text: str = Field(default="", max_length=2000)
    option_id: str | None = None
    remember: bool = False
    online_approved: bool = False


def run(db: DB, request: CUJRequest) -> dict:
    started = time.perf_counter()
    # DB's RLock keeps one session read/modify/write atomic under concurrent clicks.
    with db.lock:
        db.execute("CREATE TABLE IF NOT EXISTS demo_cuj_sessions (id TEXT PRIMARY KEY, state TEXT NOT NULL)")
        rows = db.query("SELECT state FROM demo_cuj_sessions WHERE id=?", (request.session_id,))
        state = json.loads(rows[0]["state"]) if rows else {
            "budget": 100, "seated_only": False, "selected": None,
            "invited": False, "calendar": False, "remembered": False, "searched": False,
        }
        message = ""
        if request.action == "search":
            if not request.online_approved:
                raise HTTPException(400, "Approve the one-time search first")
            budget = re.search(r"(?:under|below|up to|budget(?: of)?|\$)\s*\$?\s*(\d+)", request.text, re.I)
            state.update(budget=min(1000, max(1, int(budget[1]))) if budget else 100,
                         selected=None, searched=True, invited=False, calendar=False)
        elif request.action in {"refine", "select"}:
            if not state["searched"]:
                raise HTTPException(400, "Search before choosing tickets")
            if request.action == "refine":
                state["seated_only"] = "all" not in request.text.lower()
                if state["seated_only"] and state["selected"] == "standing":
                    state["selected"] = None
            else:
                candidates = [t for t in TICKETS if t["price"] <= state["budget"]
                              and (not state["seated_only"] or t["seated"])]
                if request.option_id not in {t["id"] for t in candidates}:
                    raise HTTPException(400, "Choose an available ticket option")
                if state["selected"] != request.option_id:
                    state.update(invited=False, calendar=False)
                state["selected"] = request.option_id
        elif request.action in {"invite", "calendar"}:
            if not state["selected"]:
                raise HTTPException(400, "Select a ticket option before confirming a draft")
            state["invited" if request.action == "invite" else "calendar"] = True
        elif request.action == "remember":
            state["remembered"] = request.remember
        elif request.action == "ask":
            message = ("Mia said she’s free on Friday after 7 PM. She’d love to catch a show with you."
                       if "mia" in request.text.lower() else
                       "Your Friday evening is free. Maggie Rogers is playing at the Fox Theater at 8 PM.")
        db.execute("INSERT OR REPLACE INTO demo_cuj_sessions VALUES (?, ?)",
                   (request.session_id, json.dumps(state)))
    options = [t for t in TICKETS if t["price"] <= state["budget"] and (not state["seated_only"] or t["seated"])]
    db.log_route("cuj:" + request.action, "local", "fake-demo", int((time.perf_counter()-started)*1000), True,
                 "SIMULATED concert scenario; no provider, messaging, calendar or model call")
    return {"event": EVENT, "tickets": options, "state": state, "message": message,
            "simulated": True, "external_actions": 0}
