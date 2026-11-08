"""Runtime settings, all overridable via environment variables."""

import os
from dataclasses import dataclass
from pathlib import Path


def _bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    fake_mode: bool = _bool("LENS_FAKE_MODE", False)
    # Keep fictional history separate from the real knowledge base by default.
    data_dir: Path = Path(os.environ.get("LENS_DATA_DIR", "data-demo" if _bool("LENS_FAKE_MODE", False) else "data"))
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

    @property
    def db_path(self) -> Path:
        return self.data_dir / "lens.db"

    @property
    def frames_dir(self) -> Path:
        return self.data_dir / "frames"


settings = Settings()
