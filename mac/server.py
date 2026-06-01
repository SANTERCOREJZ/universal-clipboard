"""
FastAPI HTTP server — the Mac side of AndroidDrop.

Endpoints
---------
GET  /health          → health check (Android uses this to verify the IP)
POST /push            → receive a file or image from Android
POST /text            → receive plain text from Android

All write requests require the header:  x-token: <TOKEN from config.py>
"""

import asyncio
import datetime
import subprocess
from pathlib import Path

from fastapi import (
    FastAPI, File, Form, Header, HTTPException, Request, Response, UploadFile,
    WebSocket, WebSocketDisconnect,
)

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
    """This machine's LAN IP address (physical interface, not a VPN tunnel)."""
    return config.local_ip()


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


# ── Mac → Android: outgoing clipboard ───────────────────────────────────────
#
# A background task watches the Mac clipboard. When the user copies something new,
# we stash it in `_outbox` and push a small event over the WebSocket to every
# connected phone. The phone then pulls the actual content from /outbox (+ /outbox/file
# for images) when the user taps the notification.

class _Outbox:
    """Holds the most recently copied item on the Mac, ready to hand to Android."""
    def __init__(self):
        self.seq = 0            # bumped on every new copy; phones use it to de-duplicate
        self.kind = None        # "text" | "image" | None
        self.text = None
        self.image = None       # PNG bytes
        self.filename = None
        self.mime = None

    def put_text(self, text):
        self.seq += 1
        self.kind, self.text, self.image = "text", text, None

    def put_image(self, data, filename, mime):
        self.seq += 1
        self.kind, self.image, self.filename, self.mime, self.text = \
            "image", data, filename, mime, None


_outbox = _Outbox()
_ws_clients: set[WebSocket] = set()

# Toggled from the menu bar ("Send clipboard to Android"). On by default.
_watch_enabled = True


def set_watch_enabled(enabled: bool) -> None:
    global _watch_enabled
    _watch_enabled = enabled


def _outbox_event() -> dict:
    """The compact JSON we push over the WebSocket (no heavy image bytes here)."""
    if _outbox.kind == "text":
        preview = (_outbox.text or "")[:80]
        return {"type": "text", "seq": _outbox.seq, "preview": preview}
    if _outbox.kind == "image":
        return {"type": "image", "seq": _outbox.seq, "preview": _outbox.filename or "Image"}
    return {"type": "empty", "seq": _outbox.seq}


async def _broadcast(message: dict) -> None:
    dead = []
    for ws in _ws_clients:
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_clients.discard(ws)


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    """Phones connect here and stay connected; we push clipboard events to them."""
    token = websocket.query_params.get("token") or websocket.headers.get("x-token")
    if token != config.TOKEN:
        await websocket.close(code=1008)  # policy violation
        return

    await websocket.accept()
    _ws_clients.add(websocket)
    try:
        # If something's already on the clipboard, let the phone know right away.
        if _outbox.kind:
            await websocket.send_json(_outbox_event())
        # We don't expect messages from the phone; this loop just keeps the socket
        # open and detects when it drops.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        _ws_clients.discard(websocket)


@app.get("/outbox")
def outbox_meta(x_token: str = Header(...)):
    """Phone pulls metadata (and the text itself, for text clips) on tap."""
    _require_token(x_token)
    if _outbox.kind == "text":
        return {"type": "text", "seq": _outbox.seq, "text": _outbox.text}
    if _outbox.kind == "image":
        return {
            "type": "image", "seq": _outbox.seq,
            "filename": _outbox.filename, "mime": _outbox.mime,
        }
    return {"type": "empty", "seq": _outbox.seq}


@app.get("/outbox/file")
def outbox_file(x_token: str = Header(...)):
    """Raw image bytes for the current outgoing clipboard image."""
    _require_token(x_token)
    if _outbox.kind != "image" or _outbox.image is None:
        raise HTTPException(status_code=404, detail="no image on clipboard")
    return Response(
        content=_outbox.image,
        media_type=_outbox.mime or "image/png",
        headers={"X-Filename": _outbox.filename or "clipboard.png"},
    )


@app.on_event("startup")
async def _start_watcher():
    asyncio.create_task(_watch_pasteboard())


async def _watch_pasteboard():
    """Poll the Mac clipboard; on a genuinely new copy, push an event to phones."""
    last_seen = clipboard.change_count()
    while True:
        await asyncio.sleep(0.75)
        try:
            cc = clipboard.change_count()
            if cc == last_seen:
                continue
            last_seen = cc

            if not _watch_enabled:
                continue
            if cc == clipboard.last_self_change():
                continue  # this write came FROM Android — don't echo it back

            kind, payload = clipboard.read_outgoing()
            if kind == "text":
                _outbox.put_text(payload)
            elif kind == "image":
                data, filename, mime = payload
                _outbox.put_image(data, filename, mime)
            else:
                continue

            await _broadcast(_outbox_event())
        except Exception:
            # Never let the watcher die — just skip this tick.
            continue
