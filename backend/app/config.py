"""Runtime settings, all overridable via environment variables."""

import os
from dataclasses import dataclass
from pathlib import Path


def _bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path(os.environ.get("LENS_DATA_DIR", "data"))
    # "ollama" keeps screenshots on this machine; "claude" sends them to the cloud.
    extractor: str = os.environ.get("LENS_EXTRACTOR", "ollama")
    # If the local extractor fails, retry in the cloud (off = strict local-only privacy mode).
    cloud_fallback: bool = _bool("LENS_CLOUD_FALLBACK", False)
    ollama_url: str = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    ollama_vision_model: str = os.environ.get("OLLAMA_VISION_MODEL", "qwen2.5vl:7b")
    claude_model: str = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
    # Keep the JPEGs on disk for debugging. Off by default: only extracted text is stored.
    save_frames: bool = _bool("LENS_SAVE_FRAMES", False)
    # Perceptual-hash distance (0-64) below which a frame counts as "same screen".
    dedup_bits: int = int(os.environ.get("LENS_DEDUP_BITS", "5"))
    # Seconds between frames sent by the phone; used to credit dwell time.
    frame_interval_s: float = float(os.environ.get("LENS_FRAME_INTERVAL", "5"))
    # An item unseen for longer than this starts a new impression.
    impression_gap_s: float = float(os.environ.get("LENS_IMPRESSION_GAP", "30"))
    # Half-life for interest decay, in hours.
    interest_half_life_h: float = float(os.environ.get("LENS_INTEREST_HALF_LIFE_H", "72"))

    # ---- Answer routing (see app/router.py) ----
    # "auto": simple lookups stay local, open-ended questions go to the cloud.
    # "cloud": always try the cloud first.  "local": never call the cloud.
    router_mode: str = os.environ.get("LENS_ROUTER", "auto")
    # Start in offline mode (as if the network were unplugged). Can be flipped at runtime via POST /mode.
    offline: bool = _bool("LENS_OFFLINE", False)
    # Local LLM used to answer open-ended questions when the cloud is unavailable.
    # Defaults to the vision model so no extra download is needed.
    ollama_text_model: str = os.environ.get("OLLAMA_TEXT_MODEL", os.environ.get("OLLAMA_VISION_MODEL", "qwen2.5vl:7b"))
    # Give up on the cloud after this many seconds and answer locally instead.
    cloud_timeout_s: float = float(os.environ.get("LENS_CLOUD_TIMEOUT", "25"))
    local_llm_timeout_s: float = float(os.environ.get("LENS_LOCAL_LLM_TIMEOUT", "90"))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "lens.db"

    @property
    def frames_dir(self) -> Path:
        return self.data_dir / "frames"


settings = Settings()
