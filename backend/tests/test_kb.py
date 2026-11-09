import io

from PIL import Image, ImageDraw

from app import kb
from app.config import settings
from app.db import DB
from app.extract import dhash, hamming
from app.schemas import FrameObservation, VisibleItem


def _obs(app="X", title="Agents are eating software", author="@karpathy", topics=("ai agents",), sensitive=False):
    return FrameObservation(
        app=app, screen_kind="feed", sensitive=sensitive,
        items=[VisibleItem(kind="post", title=title, author=author, url=None, topics=list(topics), summary="s")],
    )


def test_consecutive_frames_merge_into_one_impression_with_dwell():
    db = DB(":memory:")
    kb.record_observation(db, _obs(), 1000.0)
    kb.record_observation(db, _obs(app="Twitter"), 1003.0)  # alias normalizes to same app
    rows = db.query("SELECT * FROM impressions")
    assert len(rows) == 1
    assert rows[0]["frame_count"] == 2
    assert rows[0]["dwell_s"] == 3.0 + settings.frame_interval_s  # span + one frame interval


def test_gap_starts_new_impression():
    db = DB(":memory:")
    kb.record_observation(db, _obs(), 1000.0)
    kb.record_observation(db, _obs(), 2000.0)
    assert len(db.query("SELECT * FROM impressions")) == 2


def test_sensitive_frames_are_not_recorded():
    db = DB(":memory:")
    assert kb.record_observation(db, _obs(sensitive=True), 1000.0) == []
    assert db.query("SELECT * FROM impressions") == []


def test_search_and_interests():
    db = DB(":memory:")
    kb.record_observation(db, _obs(), 1000.0)
    kb.record_observation(db, _obs(app="YouTube", title="F1 Las Vegas highlights", author="FORMULA 1",
                                   topics=("f1", "motorsport")), 1010.0)
    kb.extend_dwell(db, [2], 1100.0)
    hits = kb.search(db, "what have I watched about motorsport")
    assert hits[0]["title"] == "F1 Las Vegas highlights"
    top = kb.interests(db, "topic", now=1100.0)
    assert top[0]["name"] in {"f1", "motorsport"}


def test_links_fall_back_to_search_urls():
    assert kb.link_for("YouTube", "video", "F1 highlights", None, None).startswith("https://www.youtube.com/results")
    assert kb.link_for("X", "profile", "Andrej", "@karpathy", None) == "https://x.com/karpathy"
    assert kb.link_for("Safari", "article", "x", None, "example.com/a") == "https://example.com/a"


def _jpeg(text: str) -> bytes:
    img = Image.new("RGB", (390, 844), "white")
    ImageDraw.Draw(img).rectangle((20, 100 + 10 * len(text), 370, 400), fill="black")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_dhash_detects_same_vs_different_screens():
    a, b = _jpeg("aaaa"), _jpeg("aaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    assert hamming(dhash(a), dhash(a)) == 0
    assert hamming(dhash(a), dhash(b)) > 5


def test_own_app_and_junk_titles_are_not_indexed():
    db = DB(":memory:")
    assert kb.record_observation(db, _obs(app="Lens", title="Where is my Tesla"), 1000.0) == []
    assert kb.record_observation(db, _obs(app="YouTube", title="0:40"), 1000.0) == []
    assert kb.record_observation(db, _obs(app="YouTube", title="1.2M views"), 1000.0) == []
    assert len(kb.record_observation(db, _obs(app="YouTube", title="2026 Midterms, explained."), 1000.0)) == 1


def test_question_naming_an_app_retrieves_that_apps_items():
    db = DB(":memory:")
    kb.record_observation(db, _obs(app="youtube", title="Ramayana: Jai Jai Ram", author="T-Series",
                                   topics=("music",)), 1000.0)
    for i in range(30):
        kb.record_observation(db, _obs(app="X", title=f"activity post number {i}", author=f"@u{i}"), 2000.0 + i)
    hits = kb.search(db, "Ok tell me about my YouTube activity")
    assert any(h["app"] == "YouTube" for h in hits)


def test_sources_allowlist(tmp_path, monkeypatch):
    from app import sources
    monkeypatch.setattr(sources, "_state", None)
    monkeypatch.setattr(sources, "_path", lambda: tmp_path / "sources.json")
    assert sources.source_for("Twitter") == "x" and sources.source_for("X") == "x"
    assert sources.source_for("Instagram") == "instagram" and sources.source_for("Facebook") == "facebook"
    assert sources.source_for("iMessage") == "messages" and sources.source_for("Calculator") == "other"
    assert kb.blocked_reason("Instagram") is None
    assert "Messages" in kb.blocked_reason("iMessage")
    db = DB(":memory:")
    assert kb.record_observation(db, _obs(app="iMessage", title="see you at 7"), 1000.0) == []
    sources.set_sources({"messages": True})
    assert len(kb.record_observation(db, _obs(app="iMessage", title="see you at 7"), 1000.0)) == 1
    sources.set_sources({"instagram": False})
    assert kb.blocked_reason("Instagram") is not None
