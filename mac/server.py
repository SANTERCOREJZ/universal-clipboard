"""
FastAPI HTTP server — the Mac side of AndroidDrop.

Endpoints
---------
GET  /health          → health check (Android uses this to verify the IP)
POST /push            → receive a file or image from Android
POST /text            → receive plain text from Android

All write requests require the header:  x-token: <TOKEN from config.py>
"""

import datetime
import socket
import subprocess
from pathlib import Path

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile

import clipboard
import config

app = FastAPI(title="AndroidDrop", version=config.VERSION)


# ── Auth ──────────────────────────────────────────────────────────────────────

def _require_token(x_token: str) -> None:
    """Raise 401 if the request token doesn't match config.TOKEN."""
    if x_token != config.TOKEN:
        raise HTTPException(status_code=401, detail="unauthorized")


# ── Notifications ─────────────────────────────────────────────────────────────

def _notify(message: str, title: str = config.APP_NAME) -> None:
    """
    Show a macOS notification via osascript.
    Works from any thread without any special entitlements.
    """
    script = f'display notification "{message}" with title "{title}"'
    subprocess.run(["osascript", "-e", script], check=False, capture_output=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _unique_path(directory: Path, filename: str) -> Path:
    """
    Return a path that doesn't collide with existing files.
    If 'image.png' exists, returns 'image_143022.png' (with HH:MM:SS suffix).
    """
    target = directory / filename
    if not target.exists():
        return target

    stem, suffix = Path(filename).stem, Path(filename).suffix
    ts = datetime.datetime.now().strftime("%H%M%S")
    return directory / f"{stem}_{ts}{suffix}"


def _local_ip() -> str:
    """Best-effort: return this machine's LAN IP address."""
    try:
        # Connect to a public address without actually sending data,
        # so the OS picks the right outgoing interface.
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Android calls this first to verify the IP and token are correct."""
    return {
        "status": "ok",
        "name": config.APP_NAME,
        "version": config.VERSION,
        "ip": _local_ip(),
        "port": config.PORT,
    }


@app.post("/push")
async def push_file(
    file: UploadFile = File(...),
    filename: str = Form(...),
    mime_type: str = Form(...),
    x_token: str = Header(...),
):
    """
    Receive a file from Android.

    Android sends:
        multipart/form-data with fields: file, filename, mime_type
        header: x-token

    Mac saves the file and, if it's an image, puts it on the clipboard.
    """
    _require_token(x_token)

    save_path = _unique_path(config.SAVE_DIR, filename)
    data = await file.read()
    save_path.write_bytes(data)

    if mime_type.startswith("image/"):
        clipboard.set_image(save_path)
        _notify(f"Image saved & copied to clipboard: {save_path.name}")
    else:
        _notify(f"File saved: {save_path.name}")

    return {"ok": True, "saved_as": save_path.name}


@app.post("/text")
async def push_text(request: Request, x_token: str = Header(...)):
    """
    Receive plain text from Android.

    Android sends:
        Content-Type: application/json
        {"text": "...", "source": "android"}
    """
    _require_token(x_token)

    body = await request.json()
    text = body.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="text field is empty")

    clipboard.set_text(text)
    preview = text[:60] + ("…" if len(text) > 60 else "")
    _notify(f"Text copied to clipboard: {preview}")

    return {"ok": True}
