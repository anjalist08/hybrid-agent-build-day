"""Which apps screen memory is allowed to remember.

The phone sends every screen while capture runs; this allowlist decides what gets indexed.
Socials, video and reading are on by default; private apps (messages) and anything
unrecognised are off. Changed from the app's Settings (GET/POST /settings/sources) and saved
next to the knowledge base, so the choice survives restarts.
"""

import json
import re
import threading

from .config import settings

# key, label, group, default, aliases (lowercase, as a vision model might name the app or site)
SOURCES: list[tuple[str, str, str, bool, tuple[str, ...]]] = [
    ("x", "X / Twitter", "Socials", True, ("x", "twitter", "x (twitter)", "x.com", "twitter.com")),
    ("instagram", "Instagram", "Socials", True, ("instagram", "insta", "instagram.com")),
    ("facebook", "Facebook", "Socials", True, ("facebook", "fb", "facebook.com", "messenger feed")),
    ("tiktok", "TikTok", "Socials", True, ("tiktok", "tik tok", "tiktok.com")),
    ("reddit", "Reddit", "Socials", True, ("reddit", "reddit.com")),
    ("linkedin", "LinkedIn", "Socials", True, ("linkedin", "linkedin.com")),
    ("threads", "Threads", "Socials", True, ("threads", "threads.net")),
    ("youtube", "YouTube", "Video & reading", True, ("youtube", "youtube.com", "yt")),
    ("web", "Web & articles", "Video & reading", True,
     ("safari", "chrome", "google chrome", "google", "firefox", "medium", "substack", "news", "apple news",
      "web", "browser", "edge", "brave")),
    ("messages", "Messages & WhatsApp", "Private", False,
     ("imessage", "messages", "whatsapp", "messenger", "telegram", "signal", "sms")),
    ("other", "Other apps", "Private", False, ()),
]

_ALIAS = {alias: key for key, _, _, _, aliases in SOURCES for alias in aliases}
_lock = threading.Lock()
_state: dict[str, bool] | None = None


def _path():
    return settings.data_dir / "sources.json"


def _load() -> dict[str, bool]:
    global _state
    if _state is None:
        defaults = {key: default for key, _, _, default, _ in SOURCES}
        try:
            saved = json.loads(_path().read_text())
            defaults.update({k: bool(v) for k, v in saved.items() if k in defaults})
        except (OSError, ValueError):
            pass
        _state = defaults
    return _state


def source_for(app: str) -> str:
    name = re.sub(r"\s+", " ", (app or "").strip().lower())
    if name in _ALIAS:
        return _ALIAS[name]
    # "YouTube app", "Safari - Medium", "X feed"...
    for alias, key in _ALIAS.items():
        if len(alias) > 2 and alias in name:
            return key
    return "other"


def blocked_reason(app: str) -> str | None:
    """None if screen memory may index this app, else a human-readable reason."""
    key = source_for(app)
    with _lock:
        allowed = _load().get(key, False)
    if allowed:
        return None
    label = next(label for k, label, *_ in SOURCES if k == key)
    return f"'{app}' counts as {label}, which is off in Settings"


def get_sources() -> list[dict]:
    with _lock:
        state = dict(_load())
    return [{"key": key, "label": label, "group": group, "enabled": state[key]}
            for key, label, group, _, _ in SOURCES]


def set_sources(changes: dict[str, bool]) -> list[dict]:
    with _lock:
        state = _load()
        for k, v in changes.items():
            if k in state:
                state[k] = bool(v)
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        _path().write_text(json.dumps(state, indent=2))
    return get_sources()
