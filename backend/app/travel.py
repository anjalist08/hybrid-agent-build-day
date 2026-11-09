"""Trip booking on Duffel (test mode): flights with seat selection, stays, cars, one payment step.

Tools here are called by the generated OpenUI screen (Query/Mutation via POST /tools/{name}).
Every search returns options in one normalized shape so a single native picker renders them:
  {id, kind, title, subtitle, detail, price, currency, badge, image}

Flights always use Duffel when DUFFEL_ACCESS_TOKEN is set. Stays and Cars are access-gated
products on Duffel; if the account can't use them, a clearly labelled simulated catalog is used
so the demo flow still completes (`source` says which).
"""

import logging
import os
import random
import re
import secrets
import threading
from datetime import date, datetime, timedelta

import httpx

log = logging.getLogger("lens.travel")

API = "https://api.duffel.com"


class TravelError(Exception):
    pass


# ---------------------------------------------------------------- Duffel client


def _token() -> str | None:
    t = os.environ.get("DUFFEL_ACCESS_TOKEN", "").strip()
    return t or None


_client_lock = threading.Lock()
_client: httpx.Client | None = None


def _http() -> httpx.Client:
    global _client
    with _client_lock:
        if _client is None:
            _client = httpx.Client(
                base_url=API,
                headers={"Authorization": f"Bearer {_token()}", "Duffel-Version": "v2",
                         "Accept": "application/json", "Content-Type": "application/json",
                         "Accept-Encoding": "gzip"},
                # Order creation can take up to ~120 s per Duffel docs.
                timeout=httpx.Timeout(130.0, connect=10.0),
            )
        return _client


def _duffel(method: str, path: str, body: dict | None = None, **params) -> dict:
    r = _http().request(method, path, json={"data": body} if body is not None else None, params=params or None)
    if r.status_code >= 400:
        try:
            err = r.json()["errors"][0]
            msg = f"{err.get('title') or err.get('code')}: {err.get('message')}"
        except Exception:  # noqa: BLE001
            msg = r.text[:300]
        log.warning("Duffel %s %s -> %s %s (request %s)", method, path, r.status_code, msg,
                    r.headers.get("x-request-id"))
        raise TravelError(msg)
    return r.json().get("data", {})


# ---------------------------------------------------------------- state

# Everything the user picked lives here between Query and Mutation calls (keyed by option id).
_offers: dict[str, dict] = {}          # flight offer id -> raw Duffel offer
_offer_passengers: dict[str, list] = {}  # offer id -> passenger ids
_seat_services: dict[str, dict] = {}   # offer id -> {designator: {passenger_id: (service_id, amount)}}
_stays: dict[str, dict] = {}           # rate id -> normalized option (+ raw)
_cars: dict[str, dict] = {}            # rate id -> normalized option (+ raw)
_trips: dict[str, dict] = {}           # booking id -> confirmation


def _money(x) -> float:
    try:
        return round(float(x), 2)
    except (TypeError, ValueError):
        return 0.0


def _hm(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%-I:%M %p")
    except ValueError:
        return iso


def _dur(iso: str | None) -> str:
    m = re.match(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?", iso or "")
    if not m:
        return ""
    d, h, mi = (int(g) if g else 0 for g in m.groups())
    h += d * 24
    return f"{h}h {mi:02d}m" if h else f"{mi}m"


# ---------------------------------------------------------------- flights


def search_flights(origin: str, destination: str, depart_date: str, return_date: str | None = None,
                   passengers: int = 1, cabin_class: str = "economy") -> dict:
    origin, destination = origin.strip().upper(), destination.strip().upper()
    passengers = max(1, min(int(passengers or 1), 6))
    if not _token():
        return _sim_flights(origin, destination, depart_date, return_date, passengers)
    slices = [{"origin": origin, "destination": destination, "departure_date": depart_date}]
    if return_date:
        slices.append({"origin": destination, "destination": origin, "departure_date": return_date})
    data = _duffel("POST", "/air/offer_requests",
                   {"slices": slices, "passengers": [{"type": "adult"}] * passengers,
                    "cabin_class": cabin_class, "max_connections": 1},
                   return_offers="true", supplier_timeout=15000)
    offers = sorted(data.get("offers", []), key=lambda o: _money(o.get("total_amount")))
    # Prefer a mix: cheapest few, always including the test airline (it supports seat maps).
    picked = offers[:6]
    zz = [o for o in offers if o.get("owner", {}).get("iata_code") == "ZZ" and o not in picked][:2]
    picked = (zz + picked)[:7]
    options = []
    for o in picked:
        _offers[o["id"]] = o
        _offer_passengers[o["id"]] = [p["id"] for p in o.get("passengers", [])]
        out = o["slices"][0]
        segs = out["segments"]
        stops = len(segs) - 1
        title = f"{o['owner']['name']} · {_hm(segs[0]['departing_at'])} → {_hm(segs[-1]['arriving_at'])}"
        subtitle = f"{out['origin']['iata_code']}→{out['destination']['iata_code']} · {_dur(out.get('duration'))} · " \
                   f"{'nonstop' if stops == 0 else f'{stops} stop'}"
        if len(o["slices"]) > 1:
            back = o["slices"][1]["segments"]
            subtitle += f" · return {_hm(back[0]['departing_at'])}"
        options.append({"id": o["id"], "kind": "flight", "title": title, "subtitle": subtitle,
                        "detail": f"{segs[0]['marketing_carrier']['iata_code']}{segs[0]['marketing_carrier_flight_number']}"
                                  f" · {o.get('total_emissions_kg') or '?'} kg CO₂",
                        "price": _money(o["total_amount"]), "currency": o["total_currency"],
                        "badge": "",
                        "image": o["owner"].get("logo_symbol_url") or ""})
    return {"kind": "flight", "source": "duffel", "count": len(options), "options": options,
            "summary": f"{origin} ⇄ {destination}" if return_date else f"{origin} → {destination}"}


def get_seat_map(offer_id: str) -> dict:
    """First outbound segment's cabin, simplified for the native seat map component."""
    empty = {"offer_id": offer_id, "available": False, "rows": [], "aisles": 1, "columns": [], "message": ""}
    if not offer_id:
        return {**empty, "message": "Pick a flight to choose seats."}
    if offer_id not in _offers:
        return {**empty, "message": "That flight offer expired. Search again."}
    if offer_id.startswith("sim_"):
        return _sim_seat_map(offer_id)
    maps = _duffel("GET", "/air/seat_maps", offer_id=offer_id)
    if not maps:
        return {**empty, "message": "This airline doesn't offer seat selection — seats are assigned at check-in."}
    cabin = maps[0]["cabins"][0]
    services: dict[str, dict] = {}
    rows = []
    columns: list[str] = []
    for row in cabin.get("rows", []):
        sections = []
        for section in row.get("sections", []):
            cells = []
            for el in section.get("elements", []):
                if el.get("type") == "seat":
                    svc = el.get("available_services") or []
                    desig = el.get("designator", "")
                    if svc:
                        services[desig] = {s["passenger_id"]: (s["id"], _money(s["total_amount"])) for s in svc}
                    letter = re.sub(r"^\d+", "", desig)
                    if letter and letter not in columns:
                        columns.append(letter)
                    cells.append({"type": "seat", "id": desig, "available": bool(svc),
                                  "price": _money(svc[0]["total_amount"]) if svc else 0})
                else:
                    cells.append({"type": el.get("type", "empty")})
            sections.append(cells)
        if not any(c.get("type") == "seat" for sec in sections for c in sec):
            continue  # bassinet/galley-only rows
        rows.append({"label": re.sub(r"\D", "", next((c["id"] for s in sections for c in s if c.get("id")), "")),
                     "sections": sections})
    _seat_services[offer_id] = services
    return {"offer_id": offer_id, "available": True, "aisles": cabin.get("aisles", 1), "columns": sorted(columns),
            "rows": rows, "currency": _offers[offer_id]["total_currency"],
            "message": "Tap a seat for each traveler."}


# ---------------------------------------------------------------- stays and cars

_SIM_HOTELS = [
    ("The Sandpiper Inn", "Boutique · 0.4 mi to the beach", 4.6, 189),
    ("Harbor House Hotel", "Waterfront · rooftop bar", 4.4, 236),
    ("Cedar & Salt Suites", "Apartments with kitchen · sleeps 4", 4.7, 274),
    ("Pacific Crest Lodge", "Budget-friendly · free breakfast", 4.1, 142),
]
_SIM_CARS = [
    ("Toyota RAV4 or similar", "Midsize SUV · 5 seats · automatic", 64),
    ("Tesla Model 3", "Electric · 5 seats · autopilot", 89),
    ("Ford Mustang Convertible", "Convertible · 4 seats", 112),
    ("Kia Carnival", "Minivan · 7 seats · fits the whole group", 98),
]


def _nights(check_in: str, check_out: str) -> int:
    try:
        return max(1, (date.fromisoformat(check_out) - date.fromisoformat(check_in)).days)
    except ValueError:
        return 1


def search_stays(city: str, latitude: float, longitude: float, check_in: str, check_out: str,
                 guests: int = 2, rooms: int = 1) -> dict:
    guests, rooms = max(1, int(guests or 1)), max(1, int(rooms or 1))
    if _token():
        try:
            data = _duffel("POST", "/stays/search", {
                "location": {"radius": 5, "geographic_coordinates": {"latitude": latitude, "longitude": longitude}},
                "check_in_date": check_in, "check_out_date": check_out, "rooms": rooms,
                "guests": [{"type": "adult"}] * guests,
            })
            options = []
            for res in sorted(data.get("results", []), key=lambda r: _money(r.get("cheapest_rate_total_amount")))[:6]:
                acc = res["accommodation"]
                addr = (acc.get("location") or {}).get("address") or {}
                opt = {"id": res["id"], "kind": "stay", "title": acc["name"],
                       "subtitle": ", ".join(x for x in (addr.get("line_one"), addr.get("city_name")) if x),
                       "detail": f"{acc.get('rating') or '–'}★ · review {acc.get('review_score') or '–'}",
                       "price": _money(res["cheapest_rate_total_amount"]), "currency": res["cheapest_rate_currency"],
                       "badge": "", "image": (acc.get("photos") or [{}])[0].get("url", "")}
                _stays[res["id"]] = {**opt, "duffel_search_result": res["id"], "nights": _nights(check_in, check_out)}
                options.append(opt)
            if options:
                return {"kind": "stay", "source": "duffel", "count": len(options), "options": options,
                        "summary": f"{city} · {_nights(check_in, check_out)} nights"}
        except TravelError as e:
            log.info("Duffel Stays unavailable, using simulated hotels: %s", e)
    nights = _nights(check_in, check_out)
    rng = random.Random(f"{city}{check_in}")
    options = []
    for name, desc, rating, nightly in _SIM_HOTELS:
        rid = f"sim_stay_{secrets.token_hex(4)}"
        price = round(nightly * nights * max(1, rooms) * rng.uniform(0.92, 1.08), 2)
        opt = {"id": rid, "kind": "stay", "title": name, "subtitle": f"{desc} · {city}",
               "detail": f"{rating}★ · {nights} nights · {rooms} room{'s' if rooms > 1 else ''}",
               "price": price, "currency": "USD", "badge": "", "image": ""}
        _stays[rid] = {**opt, "nights": nights}
        options.append(opt)
    return {"kind": "stay", "source": "simulated", "count": len(options), "options": options,
            "summary": f"{city} · {nights} nights"}


def search_cars(city: str, latitude: float, longitude: float, pickup_date: str, dropoff_date: str) -> dict:
    if _token():
        try:
            loc = {"radius": 10, "geographic_coordinates": {"latitude": latitude, "longitude": longitude}}
            data = _duffel("POST", "/cars/search", {
                "pickup_date": pickup_date, "pickup_time": "10:00", "dropoff_date": dropoff_date, "dropoff_time": "10:00",
                "pickup_location": loc, "dropoff_location": loc, "driver": {"age": 30, "residence_country_code": "US"},
            })
            options = []
            for rate in sorted(data.get("rates", []), key=lambda r: _money(r.get("total_amount")))[:6]:
                car = rate.get("car") or {}
                opt = {"id": rate["id"], "kind": "car",
                       "title": car.get("name") or car.get("model") or "Rental car",
                       "subtitle": f"{(rate.get('supplier') or {}).get('name', '')} · {rate.get('payment_type', '')}",
                       "detail": f"Pick up {pickup_date}, return {dropoff_date}",
                       "price": _money(rate["total_amount"]), "currency": rate["total_currency"], "badge": "",
                       "image": car.get("image_url") or ""}
                _cars[rate["id"]] = {**opt, "duffel_rate": rate["id"]}
                options.append(opt)
            if options:
                return {"kind": "car", "source": "duffel", "count": len(options), "options": options, "summary": city}
        except TravelError as e:
            log.info("Duffel Cars unavailable, using simulated cars: %s", e)
    days = _nights(pickup_date, dropoff_date)
    options = []
    for name, desc, daily in _SIM_CARS:
        rid = f"sim_car_{secrets.token_hex(4)}"
        opt = {"id": rid, "kind": "car", "title": name, "subtitle": desc,
               "detail": f"{days} days · pick up {city} airport", "price": round(daily * days, 2),
               "currency": "USD", "badge": "", "image": ""}
        _cars[rid] = opt
        options.append(opt)
    return {"kind": "car", "source": "simulated", "count": len(options), "options": options, "summary": city}


# ---------------------------------------------------------------- pricing and booking


def _seat_choices(offer_id: str, seats: list[str]) -> tuple[list[dict], float]:
    """Assign chosen seat designators to the offer's passengers, in order."""
    services, total = [], 0.0
    per_seat = _seat_services.get(offer_id, {})
    for pid, desig in zip(_offer_passengers.get(offer_id, []), seats or []):
        svc = per_seat.get(desig, {}).get(pid)
        if svc:
            services.append({"id": svc[0], "quantity": 1})
            total += svc[1]
    return services, round(total, 2)


def price_trip(flight_id: str = "", stay_id: str = "", car_id: str = "", seats: list[str] | None = None) -> dict:
    lines, total, currency = [], 0.0, "USD"
    if flight_id and flight_id in _offers:
        o = _offers[flight_id]
        currency = o["total_currency"]
        lines.append({"left": f"Flights · {o['owner']['name']}", "right": f"{_money(o['total_amount']):.2f}"})
        total += _money(o["total_amount"])
        _, seat_total = _seat_choices(flight_id, seats or [])
        if seats:
            lines.append({"left": f"Seats {', '.join(seats)}", "right": f"{seat_total:.2f}"})
            total += seat_total
    if stay_id and stay_id in _stays:
        s = _stays[stay_id]
        lines.append({"left": f"Stay · {s['title']}", "right": f"{s['price']:.2f}"})
        total += s["price"]
    if car_id and car_id in _cars:
        c = _cars[car_id]
        lines.append({"left": f"Car · {c['title']}", "right": f"{c['price']:.2f}"})
        total += c["price"]
    return {"lines": lines, "total": round(total, 2), "currency": currency,
            "ready": bool(flight_id), "label": f"{currency} {total:,.2f}"}


def _split_name(full: str) -> tuple[str, str]:
    parts = re.sub(r"[^A-Za-z' -]", "", full).split()
    if len(parts) < 2:
        parts = (parts or ["Lens"]) + ["Traveler"]
    return parts[0][:20], " ".join(parts[1:])[:20]


def book_trip(flight_id: str, travelers: list[str], email: str, phone: str = "+14155550100",
              stay_id: str = "", car_id: str = "", seats: list[str] | None = None) -> dict:
    """Books the flight (instant order, paid from the Duffel balance, with seats), then stay and car."""
    if not flight_id or flight_id not in _offers:
        raise TravelError("Pick a flight first (offers expire after ~20 minutes — search again if needed).")
    if not email or "@" not in email:
        raise TravelError("Add the lead traveler's email.")
    phone = phone if re.fullmatch(r"\+\d{8,15}", phone or "") else "+14155550100"

    simulated = flight_id.startswith("sim_")
    # 1. Re-fetch the offer: prices go stale, and Duffel rejects a stale amount.
    offer = _offers[flight_id] if simulated else _duffel("GET", f"/air/offers/{flight_id}")
    services, seat_total = _seat_choices(flight_id, seats or [])
    pids = [p["id"] for p in offer.get("passengers", [])]
    names = (travelers or []) + [f"Guest Traveler{i}" for i in range(len(pids))]
    passengers = []
    for i, pid in enumerate(pids):
        given, family = _split_name(names[i])
        passengers.append({"id": pid, "given_name": given, "family_name": family, "born_on": "1994-05-0" + str(1 + i % 9),
                           "gender": "m" if i % 2 else "f", "title": "mr" if i % 2 else "ms",
                           "email": email, "phone_number": phone})
    amount = f"{_money(offer['total_amount']) + seat_total:.2f}"
    order_body = {"type": "instant", "selected_offers": [flight_id], "passengers": passengers,
                  "payments": [{"type": "balance", "amount": amount, "currency": offer["total_currency"]}]}
    if services:
        order_body["services"] = services
    order = ({"booking_reference": "LNS" + secrets.token_hex(2).upper(), "owner": offer["owner"],
              "total_amount": amount, "total_currency": offer["total_currency"]}
             if simulated else _duffel("POST", "/air/orders", order_body))

    confirmation = {
        "trip_id": "TRIP-" + secrets.token_hex(3).upper(),
        "flight": {"reference": order.get("booking_reference", ""), "airline": order.get("owner", {}).get("name", ""),
                   "amount": f"{order.get('total_currency', '')} {order.get('total_amount', '')}",
                   "seats": seats or []},
        "stay": None, "car": None,
    }
    total = _money(order.get("total_amount"))
    currency = order.get("total_currency", "USD")

    # 2. Stay
    if stay_id and stay_id in _stays:
        s = _stays[stay_id]
        ref = None
        if "duffel_search_result" in s:
            try:
                rates = _duffel("POST", f"/stays/search_results/{s['duffel_search_result']}/actions/fetch_all_rates")
                rate = min((r for room in rates["accommodation"]["rooms"] for r in room["rates"]
                            if ["balance"] in (r.get("available_payment_methods") or [["balance"]])),
                           key=lambda r: _money(r["total_amount"]))
                quote = _duffel("POST", "/stays/quotes", {"rate_id": rate["id"]})
                given, family = _split_name(names[0])
                booking = _duffel("POST", "/stays/bookings", {
                    "quote_id": quote["id"], "guests": [{"given_name": given, "family_name": family}],
                    "email": email, "phone_number": phone})
                ref = booking.get("reference")
            except (TravelError, KeyError, ValueError) as e:
                raise TravelError(f"Flight booked ({confirmation['flight']['reference']}), but the stay failed: {e}") from e
        confirmation["stay"] = {"reference": ref or "LNS" + secrets.token_hex(3).upper(), "name": s["title"],
                                "simulated": ref is None}
        total += s["price"]

    # 3. Car
    if car_id and car_id in _cars:
        c = _cars[car_id]
        ref = None
        if "duffel_rate" in c:
            try:
                quote = _duffel("POST", "/cars/quotes", {"rate_id": c["duffel_rate"]})
                given, family = _split_name(names[0])
                booking = _duffel("POST", "/cars/bookings", {
                    "quote_id": quote["id"], "driver": {"given_name": given, "family_name": family, "email": email,
                                                        "phone_number": phone, "born_on": "1994-05-01"}})
                ref = booking.get("reference")
            except (TravelError, KeyError) as e:
                raise TravelError(f"Flight booked ({confirmation['flight']['reference']}), but the car failed: {e}") from e
        confirmation["car"] = {"reference": ref or "LNS" + secrets.token_hex(3).upper(), "name": c["title"],
                               "simulated": ref is None}
        total += c["price"]

    confirmation["total"] = f"{currency} {total:,.2f}"
    confirmation["message"] = (f"Flight {confirmation['flight']['reference']}"
                               + (f" · stay {confirmation['stay']['reference']}" if confirmation["stay"] else "")
                               + (f" · car {confirmation['car']['reference']}" if confirmation["car"] else "")
                               + " · paid from Duffel test balance")
    _trips[confirmation["trip_id"]] = confirmation
    return confirmation


# ---------------------------------------------------------------- simulated flights (no token / offline demo)


def _sim_flights(origin, destination, depart_date, return_date, passengers) -> dict:
    rng = random.Random(f"{origin}{destination}{depart_date}")
    airlines = [("Duffel Airways", "ZZ"), ("Pacific Coast Air", "PC"), ("Sierra Jet", "SJ"), ("Bayline", "BL")]
    options = []
    for i, (name, code) in enumerate(airlines):
        dep = 7 + i * 3 + rng.randint(0, 1)
        mins = rng.choice([65, 75, 90, 120])
        price = round(rng.uniform(89, 240) * passengers, 2)
        oid = f"sim_off_{secrets.token_hex(4)}"
        pids = [f"sim_pas_{j}" for j in range(passengers)]
        self_offer = {"id": oid, "total_amount": f"{price:.2f}", "total_currency": "USD",
                      "owner": {"name": name, "iata_code": code}, "passengers": [{"id": p} for p in pids]}
        _offers[oid] = self_offer
        _offer_passengers[oid] = pids
        arr_h, arr_m = divmod(dep * 60 + mins, 60)
        options.append({"id": oid, "kind": "flight",
                        "title": f"{name} · {dep}:00 → {arr_h % 24}:{arr_m:02d}",
                        "subtitle": f"{origin}→{destination} · {mins // 60}h {mins % 60:02d}m · nonstop"
                                    + (" · return evening" if return_date else ""),
                        "detail": f"{code}{100 + i * 37}", "price": price, "currency": "USD",
                        "badge": "", "image": ""})
    return {"kind": "flight", "source": "simulated", "count": len(options), "options": options,
            "summary": f"{origin} ⇄ {destination}" if return_date else f"{origin} → {destination}"}


def _sim_seat_map(offer_id: str) -> dict:
    rng = random.Random(offer_id)
    pids = _offer_passengers.get(offer_id, [])
    services, rows = {}, []
    for r in range(8, 24):
        sections = []
        for letters in ("ABC", "DEF"):
            cells = []
            for letter in letters:
                desig = f"{r}{letter}"
                free = rng.random() > 0.35
                price = 0.0 if r > 14 else (35.0 if r < 11 else 18.0)
                if free:
                    services[desig] = {p: (f"sim_ase_{desig}_{p}", price) for p in pids}
                cells.append({"type": "seat", "id": desig, "available": free, "price": price})
            sections.append(cells)
        rows.append({"label": str(r), "sections": sections})
    _seat_services[offer_id] = services
    return {"offer_id": offer_id, "available": True, "aisles": 1, "columns": list("ABCDEF"), "rows": rows,
            "currency": "USD", "message": "Tap a seat for each traveler. Rows 8–14 cost extra."}


TOOLS = {
    "search_flights": search_flights,
    "get_seat_map": get_seat_map,
    "search_stays": search_stays,
    "search_cars": search_cars,
    "price_trip": price_trip,
    "book_trip": book_trip,
}
