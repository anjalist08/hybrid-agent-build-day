import time

import httpx
import pytest

from app import kb, router
from app.db import DB
from app.schemas import Action, FrameObservation, LensAnswer, UIScreen, VisibleItem


def _seed(db: DB, now: float) -> None:
    def obs(app, kind, title, author, topics):
        return FrameObservation(app=app, screen_kind="feed", sensitive=False, items=[
            VisibleItem(kind=kind, title=title, author=author, url=None, topics=list(topics), summary="s")])

    kb.record_observation(db, obs("X", "post", "Agents are eating software", "@karpathy", ["ai agents"]), now - 600)
    kb.extend_dwell(db, [1], now - 540)
    kb.record_observation(db, obs("YouTube", "video", "Building AI agents with tools", "AI Explained",
                                  ["ai agents", "llms"]), now - 300)
    kb.extend_dwell(db, [2], now - 120)
    kb.record_observation(db, obs("YouTube", "video", "F1 Las Vegas highlights", "FORMULA 1", ["f1"]), now - 60)


@pytest.fixture(autouse=True)
def reset_mode():
    saved = dict(router.mode)
    router.mode.update({"router": "auto", "offline": False})
    yield
    router.mode.clear()
    router.mode.update(saved)


@pytest.fixture
def db():
    d = DB(":memory:")
    _seed(d, time.time())
    return d


def _fake_cloud_answer(db, question):
    ans = LensAnswer(speech="cloud", ui=UIScreen(title="t", components=[]), action=Action(kind="none"))
    return ans, {"impressions_sent": 3, "images_sent": 0, "chars_sent": 1234}


def _no_cloud(db, question):
    raise AssertionError("the cloud must not be called")


@pytest.mark.parametrize("question,intent", [
    ("How much time did I spend on YouTube today?", "time_by_app"),
    ("Who have I been reading the most?", "top_people"),
    ("What topics am I into lately?", "top_topics"),
    ("Open the last video I watched", "last_item"),
    ("What have I been watching about AI agents?", "recall"),
    ("Summarize what I learned about AI agents", None),
    ("Recommend something to watch tonight", None),
    ("Is there a pattern in what I read?", None),
])
def test_classify(question, intent):
    assert router.classify(question)[0] == intent


def test_simple_lookup_stays_local_and_sends_nothing(db, monkeypatch):
    monkeypatch.setattr(router, "answer_cloud", _no_cloud)
    ans, route = router.answer_question(db, "How much time did I spend on YouTube today?")
    assert route["location"] == "local" and route["engine"] == "rules"
    assert route["chars_sent"] == 0 and route["impressions_sent"] == 0
    assert "YouTube" in ans.speech
    assert ans.ui.components[1].type == "bar_chart"


def test_recall_finds_matching_items(db, monkeypatch):
    monkeypatch.setattr(router, "answer_cloud", _no_cloud)
    ans, _ = router.answer_question(db, "What have I been watching about AI agents?")
    titles = [i.title for i in ans.ui.components[0].items]
    assert "Building AI agents with tools" in titles and "F1 Las Vegas highlights" not in titles


def test_open_last_video_sets_action(db, monkeypatch):
    monkeypatch.setattr(router, "answer_cloud", _no_cloud)
    ans, _ = router.answer_question(db, "Open the last video I watched")
    assert ans.action.kind == "open_url" and "youtube.com" in ans.action.url
    assert "F1 Las Vegas highlights" in ans.speech


def test_top_people_builds_person_card(db, monkeypatch):
    monkeypatch.setattr(router, "answer_cloud", _no_cloud)
    ans, _ = router.answer_question(db, "Who have I been reading the most?")
    assert ans.ui.components[0].type == "person"


def test_open_ended_goes_to_cloud(db, monkeypatch):
    monkeypatch.setattr(router, "answer_cloud", _fake_cloud_answer)
    ans, route = router.answer_question(db, "Summarize what I learned about AI agents")
    assert ans.speech == "cloud"
    assert route["location"] == "cloud" and route["chars_sent"] == 1234


def test_cloud_failure_falls_back_to_local_model(db, monkeypatch):
    def down(db, question):
        raise httpx.ConnectError("network unreachable")

    local = LensAnswer(speech="local llm", ui=UIScreen(title="t", components=[]), action=Action(kind="none"))
    monkeypatch.setattr(router, "answer_cloud", down)
    monkeypatch.setattr(router, "answer_local_llm", lambda db, q: local)
    ans, route = router.answer_question(db, "Summarize what I learned about AI agents")
    assert ans.speech == "local llm"
    assert route["location"] == "local" and route["engine"] == "ollama" and route["fallback_from"] == "cloud"


def test_offline_mode_never_calls_cloud_and_survives_local_model_failure(db, monkeypatch):
    def ollama_down(db, question):
        raise httpx.ConnectError("ollama not running")

    router.set_mode(offline=True)
    monkeypatch.setattr(router, "answer_cloud", _no_cloud)
    monkeypatch.setattr(router, "answer_local_llm", ollama_down)
    ans, route = router.answer_question(db, "Recommend something to watch tonight")
    assert route["location"] == "local" and route["engine"] == "rules" and route["offline"] is True
    assert "can't reach the cloud" in ans.speech
    assert ans.ui.components[1].type == "timeline"


def test_cloud_router_mode_sends_lookups_to_cloud(db, monkeypatch):
    router.set_mode(router="cloud")
    monkeypatch.setattr(router, "answer_cloud", _fake_cloud_answer)
    _, route = router.answer_question(db, "How much time did I spend on YouTube today?")
    assert route["location"] == "cloud"


def test_empty_history_answers_honestly(monkeypatch):
    monkeypatch.setattr(router, "answer_cloud", _no_cloud)
    ans, route = router.answer_question(DB(":memory:"), "Who have I been reading the most?")
    assert "haven't seen" in ans.speech and route["location"] == "local"


def test_set_mode_rejects_unknown_router():
    with pytest.raises(ValueError):
        router.set_mode(router="sometimes")
