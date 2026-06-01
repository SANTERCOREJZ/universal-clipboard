from pathlib import Path

# ── Network ──────────────────────────────────────────────────────────────────
PORT = 8765
HOST = "0.0.0.0"  # listen on all network interfaces

# Shared secret sent by Android in the x-token header.
# Change this to something private before first use.
TOKEN = "changeme"

# ── Storage ───────────────────────────────────────────────────────────────────
SAVE_DIR = Path.home() / "Downloads" / "AndroidDrop"
SAVE_DIR.mkdir(parents=True, exist_ok=True)

# ── App identity ──────────────────────────────────────────────────────────────
APP_NAME = "AndroidDrop"
VERSION = "0.1.0"
