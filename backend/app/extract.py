"""Screenshot -> FrameObservation, using a local vision model (Ollama) or Claude.

Local-first: raw pixels only go to the cloud when LENS_EXTRACTOR=claude, when
LENS_CLOUD_FALLBACK is on and the local model fails, or when the cloud burst is enabled
and the local model has fallen behind. Every call is written to the routing log.
"""

import base64
import io
import time
from dataclasses import dataclass

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
- At most 6 items, the most prominent first. Only items that are mostly visible and readable.
  Skip ads, navigation chrome, and "trending" sidebars unless the user is clearly focused on them.
- app: the app or website name (e.g. "YouTube", "X", "Safari", "Medium").
- title: the video title, headline, search query, or the first line of the post (max ~120 chars).
  Never a duration, view count, or timestamp on its own.
- author: the handle, channel or byline exactly as shown, or null.
- url: only if a URL is literally visible on screen (e.g. the address bar), otherwise null.
- topics: 1-4 short lowercase tags that someone would search for later.
- summary: one short sentence (max 15 words).
- If the screen shows banking, passwords, private messages, health records, or anything
  similarly private, set sensitive=true and return an empty items list.
- If nothing meaningful is on screen (home screen, settings, loading), return an empty items list.
Return compact JSON only."""


@dataclass
class ExtractResult:
    obs: FrameObservation | None
    location: str  # local | cloud
    model: str
    ms: int
    raw: str = ""  # model output as text (kept for debugging failures)
    error: str | None = None

    @property
    def label(self) -> str:
        return f"{self.location}:{self.model}"


_claude: anthropic.Anthropic | None = None


def _claude_client() -> anthropic.Anthropic:
    global _claude
    if _claude is None:
        _claude = anthropic.Anthropic()
    return _claude


def prepare_image(jpeg: bytes, max_side: int = 1024) -> bytes:
    """Downscale so vision models stay fast; phones send ~1280px, this is a safety net."""
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


def extract_ollama(jpeg: bytes, model: str | None = None) -> tuple[FrameObservation, str]:
    resp = httpx.post(
        f"{settings.ollama_url}/api/chat",
        json={
            "model": model or settings.ollama_vision_model,
            "messages": [{"role": "user", "content": PROMPT, "images": [base64.b64encode(jpeg).decode()]}],
            "format": FrameObservation.model_json_schema(),
            "stream": False,
            "keep_alive": "60m",
            # num_predict stops the occasional runaway repetition (seen: 88s, 12k chars, invalid JSON).
            "options": {"temperature": 0, "num_predict": settings.local_max_tokens},
        },
        timeout=180,
    )
    resp.raise_for_status()
    raw = resp.json()["message"]["content"]
    try:
        return FrameObservation.model_validate_json(raw), raw
    except ValueError as e:
        raise ExtractionError(str(e), raw) from e


def extract_claude(jpeg: bytes, model: str | None = None) -> tuple[FrameObservation, str]:
    model = model or settings.claude_extract_model
    response = _claude_client().messages.parse(
        model=model,
        max_tokens=4000,
        output_config={"effort": "low"},
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
    raw = "".join(b.text for b in response.content if b.type == "text")
    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise ExtractionError(f"cloud extraction returned no output (stop_reason={response.stop_reason})", raw)
    return response.parsed_output, raw


class ExtractionError(Exception):
    def __init__(self, message: str, raw: str = ""):
        super().__init__(message)
        self.raw = raw


def extract(db: DB, jpeg: bytes, behind_s: float = 0.0) -> ExtractResult:
    """Run the routing policy. Never raises: failures come back with obs=None and the error."""
    jpeg = prepare_image(jpeg)
    local = ("local", settings.ollama_vision_model, extract_ollama)
    cloud = ("cloud", settings.claude_extract_model, extract_claude)

    burst = settings.cloud_burst_lag_s > 0 and behind_s > settings.cloud_burst_lag_s
    if settings.extractor == "claude" or burst:
        routes = [cloud]
    else:
        routes = [local] + ([cloud] if settings.cloud_fallback else [])

    result: ExtractResult | None = None
    for location, model, fn in routes:
        start = time.perf_counter()
        try:
            obs, raw = fn(jpeg)
            ms = int((time.perf_counter() - start) * 1000)
            note = f"{obs.app}: {len(obs.items)} items" + (f" (burst, {behind_s:.0f}s behind)" if burst else "")
            db.log_route("extract", location, model, ms, True, note)
            return ExtractResult(obs, location, model, ms, raw)
        except Exception as e:  # noqa: BLE001 - any failure moves to the next route
            ms = int((time.perf_counter() - start) * 1000)
            db.log_route("extract", location, model, ms, False, repr(e))
            result = ExtractResult(None, location, model, ms, getattr(e, "raw", ""), repr(e))
    assert result is not None
    return result
