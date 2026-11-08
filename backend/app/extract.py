"""Screenshot -> FrameObservation, using a local vision model (Ollama) or Claude.

Local-first: raw pixels only go to the cloud when LENS_EXTRACTOR=claude or when
LENS_CLOUD_FALLBACK is on and the local model fails. Every call is written to the
routing log so the app can show where each step ran.
"""

import base64
import io
import time

import anthropic
import httpx
from PIL import Image

from .config import settings
from .db import DB
from .schemas import FrameObservation

PROMPT = """You are looking at a screenshot of the user's phone screen. The user has
asked you to keep a private log of what they read and watch so they can ask about it later.

Extract the content items the user is looking at: posts, videos, articles, search queries,
profiles. Rules:
- Only include items that are mostly visible and readable. Skip ads, navigation chrome, and
  "trending" sidebars unless the user is clearly focused on them.
- title: the video title, headline, search query, or the first line of the post (max ~120 chars).
- author: the handle, channel or byline exactly as shown, or null.
- url: only if a URL is literally visible on screen (e.g. the address bar), otherwise null.
- topics: 1-4 short lowercase tags that someone would search for later.
- If the screen shows banking, passwords, private messages, health records, or anything
  similarly private, set sensitive=true and return an empty items list.
- If nothing meaningful is on screen (home screen, settings, loading), return an empty items list.
Return JSON only."""

_claude: anthropic.Anthropic | None = None


def _claude_client() -> anthropic.Anthropic:
    global _claude
    if _claude is None:
        _claude = anthropic.Anthropic()
    return _claude


def prepare_image(jpeg: bytes, max_side: int = 1024) -> bytes:
    """Downscale so vision models stay fast; phones send ~720p already, this is a safety net."""
    img = Image.open(io.BytesIO(jpeg)).convert("RGB")
    img.thumbnail((max_side, max_side))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=80)
    return out.getvalue()


def dhash(jpeg: bytes, size: int = 8) -> str:
    """64-bit difference hash: robust to compression noise, changes when the screen content changes."""
    img = Image.open(io.BytesIO(jpeg)).convert("L").resize((size + 1, size), Image.LANCZOS)
    px = img.tobytes()  # one byte per pixel in "L" mode
    bits = 0
    for row in range(size):
        for col in range(size):
            left = px[row * (size + 1) + col]
            right = px[row * (size + 1) + col + 1]
            bits = (bits << 1) | (left > right)
    return f"{bits:016x}"


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def extract_ollama(jpeg: bytes) -> FrameObservation:
    resp = httpx.post(
        f"{settings.ollama_url}/api/chat",
        json={
            "model": settings.ollama_vision_model,
            "messages": [{"role": "user", "content": PROMPT, "images": [base64.b64encode(jpeg).decode()]}],
            "format": FrameObservation.model_json_schema(),
            "stream": False,
            "options": {"temperature": 0},
        },
        timeout=180,
    )
    resp.raise_for_status()
    return FrameObservation.model_validate_json(resp.json()["message"]["content"])


def extract_claude(jpeg: bytes) -> FrameObservation:
    response = _claude_client().messages.parse(
        model=settings.claude_model,
        max_tokens=4000,
        output_config={"effort": "low"},
        # Server-side fallback: if the model declines, the API reroutes by refusal category.
        extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"},
        extra_body={"fallbacks": "default"},
        output_format=FrameObservation,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(jpeg).decode()},
                    },
                    {"type": "text", "text": PROMPT},
                ],
            }
        ],
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise RuntimeError(f"cloud extraction returned no output (stop_reason={response.stop_reason})")
    return response.parsed_output


def extract(db: DB, jpeg: bytes) -> tuple[FrameObservation, str]:
    """Returns (observation, extractor label). Raises if every allowed route fails."""
    if settings.fake_mode:
        # Rehearse ingestion without pretending to understand uploaded pixels.
        db.log_route("extract", "local", "fake-demo", 0, True,
                     "SIMULATED: frame ignored; no vision model or network call")
        return FrameObservation(app="Demo", screen_kind="other", sensitive=False, items=[]), "local:fake-demo"
    jpeg = prepare_image(jpeg)
    routes: list[tuple[str, str, callable]] = []
    if settings.extractor == "claude":
        routes.append(("cloud", settings.claude_model, extract_claude))
    else:
        routes.append(("local", settings.ollama_vision_model, extract_ollama))
        if settings.cloud_fallback:
            routes.append(("cloud", settings.claude_model, extract_claude))

    last_error: Exception | None = None
    for location, model, fn in routes:
        start = time.perf_counter()
        try:
            obs = fn(jpeg)
            ms = int((time.perf_counter() - start) * 1000)
            db.log_route("extract", location, model, ms, True, f"{obs.app}: {len(obs.items)} items")
            return obs, f"{location}:{model}"
        except Exception as e:  # noqa: BLE001 - any failure moves to the next route
            ms = int((time.perf_counter() - start) * 1000)
            db.log_route("extract", location, model, ms, False, repr(e))
            last_error = e
    raise RuntimeError(f"all extraction routes failed: {last_error!r}")
