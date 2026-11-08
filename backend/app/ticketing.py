"""Events, seat maps, holds and bookings.

Each event in openui/events.json is backed either by seats.io (when it has a
`seatsio_event_key` and SEATSIO_SECRET_KEY is set) or by a simulated venue held in memory,
so the agent flow works before a real chart exists. Prices live here, not in seats.io:
seats.io stores seat categories, our catalog maps each category to a price.
"""

import json
import os
import random
import re
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

CATALOG_PATH = Path(__file__).parent / "openui" / "events.json"
HOLD_MINUTES = 10


class TicketingError(Exception):
    pass


def _catalog() -> list[dict]:
    events = json.loads(CATALOG_PATH.read_text())
    override = os.environ.get("SEATSIO_EVENT_KEY", "").strip()
    if override and events:
        # Convenience: SEATSIO_EVENT_KEY in .env backs the first demo event with seats.io.
        events[0]["seatsio_event_key"] = override
    return events


def get_catalog_event(event_id: str) -> dict:
    for e in _catalog():
        if e["id"] == event_id:
            return e
    raise TicketingError(f"Unknown event '{event_id}'")


def find_events(query: str) -> list[dict]:
    """Match free text (a friend's message, a link) against the catalog. Returns summaries."""
    q = query.lower()
    words = set(re.findall(r"[a-z0-9]+", q))
    scored = []
    for e in _catalog():
        score = sum(3 for a in e["aliases"] if a in q)
        score += len(words & set(re.findall(r"[a-z0-9]+", f"{e['artist']} {e['venue']} {e['city']}".lower())))
        scored.append((score, e))
    scored.sort(key=lambda s: s[0], reverse=True)
    return [
        {"id": e["id"], "name": e["name"], "artist": e["artist"], "venue": e["venue"], "city": e["city"],
         "date": e["date"], "match_score": s}
        for s, e in scored
    ]


def _backend(event: dict) -> "SeatBackend":
    key = event.get("seatsio_event_key")
    if key and os.environ.get("SEATSIO_SECRET_KEY"):
        return SeatsioBackend(event)
    return _simulated(event)


# ---------------------------------------------------------------- tool implementations


def get_event(event_id: str) -> dict:
    event = get_catalog_event(event_id)
    seats = _backend(event).seats()
    tiers = []
    for c in event["categories"]:
        free = sum(1 for s in seats if s["category"] == c["key"] and s["status"] == "free")
        tiers.append({"category": c["key"], "label": c["label"], "price": c["price"], "color": c["color"],
                      "available": free})
    return {
        "id": event["id"], "name": event["name"], "artist": event["artist"], "venue": event["venue"],
        "city": event["city"], "date": event["date"], "doors": event["doors"], "description": event["description"],
        "seats_available": sum(t["available"] for t in tiers), "price_tiers": tiers,
        "source": "seats.io" if isinstance(_backend(event), SeatsioBackend) else "simulated",
    }


def get_seats(event_id: str) -> dict:
    event = get_catalog_event(event_id)
    seats = _backend(event).seats()
    xs = [s["x"] for s in seats] or [0]
    ys = [s["y"] for s in seats] or [0]
    # Normalize to a 0-based box so the app can scale it to any width.
    minx, miny = min(xs), min(ys)
    for s in seats:
        s["x"] = round(s["x"] - minx, 1)
        s["y"] = round(s["y"] - miny, 1)
    return {
        "event_id": event_id,
        "width": round(max(xs) - minx, 1),
        "height": round(max(ys) - miny, 1),
        "stage": "top",
        "categories": [{"key": c["key"], "label": c["label"], "color": c["color"], "price": c["price"]}
                       for c in event["categories"]],
        "seats": seats,
    }


def hold_seats(event_id: str, seats: list[str]) -> dict:
    if not seats:
        raise TicketingError("Pick at least one seat first.")
    event = get_catalog_event(event_id)
    backend = _backend(event)
    by_id = {s["id"]: s for s in backend.seats()}
    unknown = [s for s in seats if s not in by_id]
    if unknown:
        raise TicketingError(f"Unknown seats: {', '.join(unknown)}")
    taken = [s for s in seats if by_id[s]["status"] != "free"]
    if taken:
        raise TicketingError(f"Just taken by someone else: {', '.join(taken)}. Pick different seats.")
    token = backend.hold(seats)
    subtotal = sum(by_id[s]["price"] for s in seats)
    fees = round(event["fee_per_ticket"] * len(seats), 2)
    expires = datetime.now(timezone.utc) + timedelta(minutes=HOLD_MINUTES)
    return {
        "hold_token": token, "expires_at": expires.isoformat(timespec="seconds"), "seats": seats,
        "subtotal": subtotal, "fees": fees, "total": round(subtotal + fees, 2),
        "message": f"Held {len(seats)} seat(s) for {HOLD_MINUTES} minutes.",
    }


def book_seats(event_id: str, hold_token: str, name: str, email: str) -> dict:
    if not hold_token:
        raise TicketingError("Hold your seats first.")
    event = get_catalog_event(event_id)
    backend = _backend(event)
    seats = backend.book(hold_token)
    by_id = {s["id"]: s for s in backend.seats()}
    total = round(sum(by_id[s]["price"] for s in seats if s in by_id) + event["fee_per_ticket"] * len(seats), 2)
    order_id = "LNS-" + secrets.token_hex(3).upper()
    return {"order_id": order_id, "seats": seats, "total": total,
            "message": f"Booked {len(seats)} seat(s) for {name}. Confirmation sent to {email} (demo)."}


TOOLS = {"get_event": get_event, "get_seats": get_seats, "hold_seats": hold_seats, "book_seats": book_seats}


# ---------------------------------------------------------------- backends


class SeatBackend:
    def seats(self) -> list[dict]: ...
    def hold(self, seat_ids: list[str]) -> str: ...
    def book(self, hold_token: str) -> list[str]: ...


class SimulatedBackend(SeatBackend):
    """A small theatre: floor in front of the stage, a lower bowl in three sections, a balcony."""

    def __init__(self, event: dict):
        self.event = event
        self.lock = threading.Lock()
        rng = random.Random(event["id"])
        price = {c["key"]: c["price"] for c in event["categories"]}
        self._seats: dict[str, dict] = {}

        def add(section, row, n, x0, y, cat, gap=14.0):
            for i in range(n):
                sid = f"{section}-{row}-{i + 1}"
                status = "booked" if rng.random() < 0.3 else "free"
                self._seats[sid] = {"id": sid, "section": section, "row": row, "seat": str(i + 1),
                                    "x": x0 + i * gap, "y": y, "category": cat, "price": price[cat], "status": status}

        for r, row in enumerate("ABCDE"):
            add("Floor", row, 12, 132, 40 + r * 14, "floor")
        for r, row in enumerate("FGHJ"):
            y = 130 + r * 14
            add("101", row, 6, 20, y, "lower")
            add("102", row, 10, 146, y, "lower")
            add("103", row, 6, 320, y, "lower")
        for r, row in enumerate("KLM"):
            add("Balcony", row, 22, 50, 215 + r * 14, "balcony")
        self.holds: dict[str, tuple[list[str], float]] = {}

    def _expire(self) -> None:
        now = time.time()
        for token, (ids, exp) in list(self.holds.items()):
            if exp < now:
                for sid in ids:
                    if self._seats[sid]["status"] == "held":
                        self._seats[sid]["status"] = "free"
                del self.holds[token]

    def seats(self) -> list[dict]:
        with self.lock:
            self._expire()
            return [dict(s) for s in self._seats.values()]

    def hold(self, seat_ids: list[str]) -> str:
        with self.lock:
            self._expire()
            if any(self._seats[s]["status"] != "free" for s in seat_ids):
                raise TicketingError("Some of those seats were just taken.")
            token = "sim-" + secrets.token_hex(6)
            for s in seat_ids:
                self._seats[s]["status"] = "held"
            self.holds[token] = (seat_ids, time.time() + HOLD_MINUTES * 60)
            return token

    def book(self, hold_token: str) -> list[str]:
        with self.lock:
            self._expire()
            if hold_token not in self.holds:
                raise TicketingError("Your hold expired. Pick your seats again.")
            ids, _ = self.holds.pop(hold_token)
            for s in ids:
                self._seats[s]["status"] = "booked"
            return ids


_sim_cache: dict[str, SimulatedBackend] = {}


def _simulated(event: dict) -> SimulatedBackend:
    if event["id"] not in _sim_cache:
        _sim_cache[event["id"]] = SimulatedBackend(event)
    return _sim_cache[event["id"]]


class SeatsioBackend(SeatBackend):
    """seats.io: geometry from the published chart drawing, live status per object, hold tokens."""

    _geometry_cache: dict[str, tuple[float, list[dict]]] = {}
    _holds: dict[str, list[str]] = {}

    def __init__(self, event: dict):
        self.event = event
        self.key = event["seatsio_event_key"]
        region = os.environ.get("SEATSIO_REGION", "na")
        self.client = httpx.Client(base_url=f"https://api-{region}.seatsio.net",
                                   auth=(os.environ["SEATSIO_SECRET_KEY"], ""), timeout=15)

    def _get(self, path: str, **params) -> dict:
        r = self.client.get(path, params=params)
        if r.status_code >= 400:
            raise TicketingError(f"seats.io GET {path} failed: {r.status_code} {r.text[:200]}")
        return r.json()

    def _post(self, path: str, body: dict | None = None, **params) -> dict:
        r = self.client.post(path, json=body or {}, params=params)
        if r.status_code >= 400:
            raise TicketingError(f"seats.io POST {path} failed: {r.status_code} {r.text[:200]}")
        return r.json() if r.content else {}

    def _category_key(self, label_or_key) -> str:
        """Map a seats.io category (label or numeric key) to our catalog category key."""
        cats = self.event["categories"]
        s = str(label_or_key or "").lower()
        for c in cats:
            if s in (c["key"].lower(), c["label"].lower()):
                return c["key"]
        try:
            return cats[int(s) - 1]["key"]  # seats.io numeric keys 1, 2, 3 -> catalog order
        except (ValueError, IndexError):
            return cats[-1]["key"]

    def _geometry(self) -> list[dict]:
        cached = self._geometry_cache.get(self.key)
        if cached and time.time() - cached[0] < 300:
            return [dict(s) for s in cached[1]]
        chart_key = self._get(f"/events/{self.key}")["chartKey"]
        drawing = self._get(f"/charts/{chart_key}/version/published")
        cat_labels = {str(c.get("key")): c.get("label") for c in drawing.get("categories", {}).get("list", [])}
        seats: list[dict] = []

        def walk(node, section: str | None, ox: float, oy: float):
            if isinstance(node, dict):
                # Sections carry their own sub-chart, offset by the section's position.
                if "subChart" in node and node is not drawing:
                    pos = node.get("topLeft") or node.get("center") or {}
                    walk(node["subChart"], node.get("label") or section, ox + float(pos.get("x", 0) or 0),
                         oy + float(pos.get("y", 0) or 0))
                    return
                if isinstance(node.get("seats"), list):
                    row = str(node.get("label", ""))
                    for seat in node["seats"]:
                        label = str(seat.get("label", ""))
                        cat = seat.get("categoryLabel") or node.get("categoryLabel") or \
                            cat_labels.get(str(seat.get("categoryKey", node.get("categoryKey"))))
                        parts = [p for p in (section, row, label) if p]
                        seats.append({"id": "-".join(parts), "section": section or "", "row": row, "seat": label,
                                      "x": ox + float(seat.get("x", 0)), "y": oy + float(seat.get("y", 0)),
                                      "category": self._category_key(cat)})
                    return
                for k, v in node.items():
                    if k != "categories":
                        walk(v, section, ox, oy)
            elif isinstance(node, list):
                for v in node:
                    walk(v, section, ox, oy)

        walk(drawing.get("subChart", drawing), None, 0.0, 0.0)
        if not seats:
            raise TicketingError("The seats.io chart has no seats yet. Draw rows in the designer and publish it.")
        self._geometry_cache[self.key] = (time.time(), seats)
        return [dict(s) for s in seats]

    def _statuses(self, ids: list[str]) -> dict[str, str]:
        out: dict[str, str] = {}
        for i in range(0, len(ids), 50):
            chunk = ids[i:i + 50]
            r = self.client.get(f"/events/{self.key}/objects", params=[("label", x) for x in chunk])
            if r.status_code >= 400:
                raise TicketingError(f"seats.io status lookup failed: {r.status_code} {r.text[:200]}")
            for label, info in r.json().items():
                out[label] = str(info.get("status", "free"))
        return out

    def seats(self) -> list[dict]:
        seats = self._geometry()
        statuses = self._statuses([s["id"] for s in seats])
        price = {c["key"]: c["price"] for c in self.event["categories"]}
        for s in seats:
            raw = statuses.get(s["id"], "free").lower()
            s["status"] = "free" if raw == "free" else "booked" if raw == "booked" else "held"
            s["price"] = price[s["category"]]
        return seats

    def hold(self, seat_ids: list[str]) -> str:
        token = self._post("/hold-tokens", {"expiresInMinutes": HOLD_MINUTES})["holdToken"]
        self._post("/events/groups/actions/change-object-status",
                   {"type": "CHANGE_STATUS_TO", "status": "reservedByToken", "events": [self.key],
                    "objects": [{"objectId": s} for s in seat_ids], "holdToken": token}, expand="objects")
        self._holds[token] = seat_ids
        return token

    def book(self, hold_token: str) -> list[str]:
        seat_ids = self._holds.get(hold_token)
        if not seat_ids:
            raise TicketingError("Your hold expired. Pick your seats again.")
        self._post("/events/groups/actions/change-object-status",
                   {"type": "CHANGE_STATUS_TO", "status": "booked", "events": [self.key],
                    "objects": [{"objectId": s} for s in seat_ids], "holdToken": hold_token}, expand="objects")
        self._holds.pop(hold_token, None)
        return seat_ids
