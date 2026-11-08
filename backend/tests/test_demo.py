"""Fake-mode contract: deterministic local responses, with no outbound AI calls."""

import importlib
import json
import os
from dataclasses import replace
from pathlib import Path
import subprocess
import sys

import anthropic
import httpx
import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException

from app import config, extract, query
from app.db import DB
from app.schemas import LensAnswer, QueryResponse


@pytest.fixture(autouse=True)
def no_outbound(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Fake mode attempted an outbound request")

    # TestClient uses an in-process ASGI transport; intercept real transports only.
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)
    monkeypatch.setattr(httpx, "post", forbidden)
    monkeypatch.setattr(anthropic, "Anthropic", forbidden)
    monkeypatch.setattr(query, "_claude", forbidden)
    monkeypatch.setattr(extract, "_claude_client", forbidden)
    monkeypatch.setattr(extract, "extract_ollama", forbidden)
    monkeypatch.setattr(extract, "extract_claude", forbidden)


@pytest.fixture
def fake_settings(monkeypatch, tmp_path):
    value = replace(config.settings, fake_mode=True, data_dir=tmp_path)
    for module in (config, query, extract):
        monkeypatch.setattr(module, "settings", value)
    return value


@pytest.fixture
def db():
    value = DB(":memory:")
    yield value
    value.conn.close()


def test_fake_env_has_isolated_default_database():
    env = dict(os.environ, LENS_FAKE_MODE="true")
    env.pop("LENS_DATA_DIR", None)
    # Fresh interpreter exercises environment defaults without reloading shared modules.
    result = subprocess.run(
        [sys.executable, "-c", "from app.config import settings; "
         "print(settings.fake_mode); print(settings.db_path)"],
        cwd=Path(__file__).resolve().parents[1], env=env,
        capture_output=True, text=True, check=True,
    )
    enabled, path = result.stdout.strip().splitlines()
    assert enabled == "True"
    assert Path(path) == Path("data-demo/lens.db")


def test_seed_is_idempotent_and_populates_searchable_fixtures(db):
    from app.demo import seed_demo

    seed_demo(db, now=1_800_000_000.0)
    before = db.query("SELECT * FROM impressions ORDER BY id")
    assert len(before) == 4
    assert sorted(row["app"] for row in before) == ["Medium", "X", "YouTube", "YouTube"]
    assert any(row["author"] == "@demo_alex" for row in before)
    assert any("f1" in json.loads(row["topics"]) for row in before)
    assert any("ai agents" in json.loads(row["topics"]) for row in before)
    seed_demo(db, now=1_800_000_100.0)
    assert db.query("SELECT * FROM impressions ORDER BY id") == before
    assert db.query("SELECT * FROM impressions_fts")


@pytest.mark.parametrize("question,kind", [
    ("What did I watch about AI agents?", "timeline"),
    ("How much time did I spend in each app?", "bar_chart"),
    ("Who posted about AI agents?", "person"),
])
def test_fake_answers_match_generative_ui_contract(db, fake_settings, question, kind):
    from app.demo import seed_demo

    seed_demo(db)
    answer, route = query.answer(db, question)
    assert isinstance(answer, LensAnswer)
    assert answer.speech
    assert kind in [component.type for component in answer.ui.components]
    assert answer.action.kind == "none"
    assert route["location"] == "local"
    assert route["model"] == "fake-demo"
    assert route["simulated"] is True
    assert route["images_sent"] == route["impressions_sent"] == 0


@pytest.mark.parametrize("question", ["Open the AI agents video", "Play that F1 video"])
def test_fake_open_requests_never_trigger_external_action(db, fake_settings, question):
    from app.demo import seed_demo

    seed_demo(db)
    answer, _ = query.answer(db, question)
    assert answer.action.kind == "none"
    assert answer.action.url is None
    assert any(component.type == "card" for component in answer.ui.components)


def test_fake_extractor_does_not_analyze_image_or_invent_impressions(db, fake_settings):
    # Invalid image bytes prove fake extraction bypasses real image preparation too.
    observation, label = extract.extract(db, b"not an image")
    assert observation.app == "Demo"
    assert observation.items == []
    assert observation.sensitive is False
    assert "fake-demo" in label
    assert db.query("SELECT * FROM impressions") == []
    routes = db.query("SELECT * FROM route_log WHERE op='extract'")
    assert routes and routes[-1]["location"] == "local"
    assert routes[-1]["model"] == "fake-demo"


def test_fake_api_lifespan_seeds_once_and_delete_stays_empty(monkeypatch, fake_settings):
    # Import after replacing config so the module-level DB is temporary.
    main = importlib.import_module("app.main")
    monkeypatch.setattr(main, "settings", fake_settings)
    test_db = DB(fake_settings.db_path)
    monkeypatch.setattr(main, "db", test_db)
    try:
        with TestClient(main.app) as client:
            health = client.get("/health")
            assert health.status_code == 200
            assert health.json()["fake_mode"] is True
            page = client.get("/demo")
            assert page.status_code == 200
            assert client.get("/demo/assets/concert.png").status_code == 200
            assert "Friday sounds good." in page.text
            assert "A little help" in page.text
            import re
            assert not re.search(r"[\u4e00-\u9fff]", page.text)
            assert len(client.get("/impressions").json()) == 4
            for source in ("typed", "device-stt", "siri"):
                response = client.post("/query", json={"text": "What did I watch?", "source": source})
                assert response.status_code == 200
                parsed = QueryResponse.model_validate(response.json())
                assert parsed.route["transcript_source"] == source
                assert parsed.route["simulated"] is True
                assert parsed.route["location"] == "local"
            assert client.post("/query", json={"text": "   "}).status_code == 400
            assert client.delete("/data").json() == {"ok": True}
            assert client.get("/impressions").json() == []
            empty = client.post("/query", json={"text": "What did I watch?"})
            assert empty.status_code == 200
            assert QueryResponse.model_validate(empty.json()).answer.action.kind == "none"
            assert client.get("/impressions").json() == []
    finally:
        test_db.conn.close()


def test_supported_demo_query_semantics(db, fake_settings):
    from app.demo import seed_demo
    seed_demo(db)
    answer, _ = query.answer(db, "How much time did I spend on YouTube?")
    chart = next(c for c in answer.ui.components if c.type == "bar_chart")
    assert [(b.label, b.value) for b in chart.bars] == [("YouTube", 21)]
    answer, _ = query.answer(db, "Who did I read on X?")
    assert next(c for c in answer.ui.components if c.type == "person").title == "@demo_alex"
    answer, _ = query.answer(db, "What AI content did I explore?")
    timeline = next(c for c in answer.ui.components if c.type == "timeline")
    assert len(timeline.items) == 3
    assert all("F1" not in item.title for item in timeline.items)


def test_fake_mode_overrides_cloud_extraction_and_fallback(db, fake_settings, monkeypatch):
    monkeypatch.setattr(extract, "settings", replace(fake_settings, extractor="claude", cloud_fallback=True))
    observation, label = extract.extract(db, b"not an image")
    assert observation.app == "Demo" and observation.items == []
    assert label == "local:fake-demo"
    route = db.query("SELECT * FROM route_log WHERE op='extract'")[-1]
    assert route["location"] == "local" and route["model"] == "fake-demo"


def test_real_mode_dispatches_query_to_model_adapter(db, fake_settings, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from app.schemas import Action, UIScreen
    monkeypatch.setattr(query, "settings", replace(fake_settings, fake_mode=False))
    expected = LensAnswer(speech="Adapter response", ui=UIScreen(title="Real route", components=[]),
                          action=Action(kind="none"))
    parse = Mock(return_value=SimpleNamespace(stop_reason="end_turn", parsed_output=expected))
    monkeypatch.setattr(query, "_claude", lambda: SimpleNamespace(messages=SimpleNamespace(parse=parse)))
    answer, route = query.answer(db, "What did I watch?")
    assert answer == expected
    parse.assert_called_once()
    assert route["location"] == "cloud"
    assert route.get("simulated") is not True


@pytest.mark.parametrize("provider,location", [("ollama", "local"), ("claude", "cloud")])
def test_real_mode_dispatches_extraction_to_model_adapter(db, fake_settings, monkeypatch, provider, location):
    from unittest.mock import Mock
    from app.schemas import FrameObservation
    monkeypatch.setattr(extract, "settings", replace(fake_settings, fake_mode=False,
                                                    extractor=provider, cloud_fallback=False))
    monkeypatch.setattr(extract, "prepare_image", lambda jpeg: jpeg)
    expected = FrameObservation(app="Test", screen_kind="other", sensitive=False, items=[])
    adapter = Mock(return_value=expected)
    monkeypatch.setattr(extract, f"extract_{provider}", adapter)
    observation, label = extract.extract(db, b"test image")
    assert observation == expected
    adapter.assert_called_once_with(b"test image")
    assert label.startswith(location + ":") and "fake-demo" not in label


def test_demo_page_is_unavailable_in_real_mode(monkeypatch, fake_settings):
    from fastapi import HTTPException
    main = importlib.import_module("app.main")
    monkeypatch.setattr(main, "settings", replace(fake_settings, fake_mode=False))
    with pytest.raises(HTTPException) as error:
        main.demo_page()
    assert error.value.status_code == 404


def test_complete_concert_journey_and_session_isolation(db):
    from app.cuj import run, CUJRequest
    def act(action, **kwargs):
        return run(db, CUJRequest(session_id="journey-one", action=action, **kwargs))
    assert act("start")["state"]["searched"] is False
    with pytest.raises(HTTPException) as unapproved:
        act("search", text="Find me tickets under $100")
    assert unapproved.value.status_code == 400
    options = act("search", text="Find me tickets under $100", online_approved=True)
    assert [t["price"] for t in options["tickets"]] == [65, 85, 95]
    act("select", option_id="standing")
    refined = act("refine", text="Only seated tickets")
    assert refined["state"]["selected"] is None
    assert [t["price"] for t in refined["tickets"]] == [85, 95]
    act("select", option_id="seated")
    assert act("invite")["state"]["invited"] is True
    assert act("invite")["state"]["invited"] is True
    assert act("calendar")["state"]["calendar"] is True
    result = act("remember", remember=True)
    assert result["state"]["remembered"] is True
    assert result["external_actions"] == 0 and result["simulated"] is True
    assert run(db, CUJRequest(session_id="journey-two", action="start"))["state"]["invited"] is False
    assert act("start")["state"]["remembered"] is True
    assert act("remember", remember=False)["state"]["remembered"] is False


def test_concert_budget_and_selection_validation(db):
    from app.cuj import run, CUJRequest
    run(db, CUJRequest(session_id="budget", action="search", text="Under $70", online_approved=True))
    with pytest.raises(HTTPException) as unavailable:
        run(db, CUJRequest(session_id="budget", action="select", option_id="seated"))
    assert unavailable.value.status_code == 400
    result = run(db, CUJRequest(session_id="budget", action="refine", text="Only seated tickets"))
    assert result["tickets"] == []
