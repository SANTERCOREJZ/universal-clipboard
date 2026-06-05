"""
Persisted user settings (token, save folder, send-toggle).

Stored as JSON in ~/Library/Application Support/AndroidDrop/settings.json so they
survive restarts and can be edited from the Settings window instead of code.
Defaults come from config.py the first time.
"""

import json
import threading
from pathlib import Path

import config

_DIR = Path.home() / "Library" / "Application Support" / "AndroidDrop"
_FILE = _DIR / "settings.json"
_lock = threading.Lock()
_cache = None

DEFAULTS = {
    "token": config.TOKEN,
    "save_dir": str(config.SAVE_DIR),
    "send_to_android": True,
}


def _load() -> dict:
    global _cache
    if _cache is None:
        try:
            _cache = {**DEFAULTS, **json.loads(_FILE.read_text())}
        except Exception:
            _cache = dict(DEFAULTS)
    return _cache


def get(key: str):
    return _load().get(key, DEFAULTS.get(key))


def set(key: str, value) -> None:
    with _lock:
        data = _load()
        data[key] = value
        try:
            _DIR.mkdir(parents=True, exist_ok=True)
            _FILE.write_text(json.dumps(data, indent=2))
        except Exception:
            pass


def save_dir() -> Path:
    """The current save folder, guaranteed to exist."""
    p = Path(get("save_dir"))
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        p = config.SAVE_DIR
        p.mkdir(parents=True, exist_ok=True)
    return p
