"""
AndroidDrop — macOS menu bar app.

Entry point. Run with:
    python app.py

What happens:
1. rumps takes over the main thread and shows a menu bar icon.
2. The FastAPI server starts in a background daemon thread.
3. Menu items let you open the received folder or see recent files.

rumps is a Python library that wraps macOS AppKit to create menu bar apps.
daemon=True on the server thread means it dies automatically when the app quits.
"""

import subprocess
import threading

import rumps
import uvicorn

import config
import discovery
import server
from server import app as fastapi_app, _local_ip


# ── Server thread ─────────────────────────────────────────────────────────────

def _run_server() -> None:
    """Run the FastAPI/uvicorn server. Called in a background thread."""
    uv_config = uvicorn.Config(
        fastapi_app,
        host=config.HOST,
        port=config.PORT,
        log_level="warning",  # quieter console output
    )
    uvicorn.Server(uv_config).run()


# ── Menu bar app ──────────────────────────────────────────────────────────────

class AndroidDropApp(rumps.App):
    def __init__(self):
        # "⬇" is a temporary text icon; replace with a real .png later.
        # rumps.App(title, icon=path) — icon must be a 22×22 px template image.
        super().__init__("AndroidDrop", title="⬇", quit_button=None)

        # Toggle for the Mac → Android direction. Checked = the Mac pushes every
        # new copy to connected phones. Starts on, matching server._watch_enabled.
        self.send_item = rumps.MenuItem("Send clipboard to Android", callback=self.toggle_send)
        self.send_item.state = 1

        self.menu = [
            rumps.MenuItem("Open Received Folder", callback=self.open_folder),
            rumps.MenuItem("Recent Items",         callback=self.show_recent),
            None,  # separator
            self.send_item,
            None,
            rumps.MenuItem(f"Listening on  {_local_ip()}:{config.PORT}"),  # informational, no callback
            None,
            rumps.MenuItem("Quit", callback=self.quit_app),
        ]

        # Start the HTTP server in the background before the menu bar appears.
        t = threading.Thread(target=_run_server, daemon=True)
        t.start()

        # Advertise ourselves via mDNS so Android can find us automatically,
        # even after the Mac's IP changes.
        discovery.start()

    # ── Menu callbacks ────────────────────────────────────────────────────────

    def open_folder(self, _):
        """Open ~/Downloads/AndroidDrop in Finder."""
        subprocess.run(["open", str(config.SAVE_DIR)], check=False)

    def show_recent(self, _):
        """Show the 5 most recently received files in an alert dialog."""
        files = sorted(
            config.SAVE_DIR.glob("*"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:5]

        if files:
            body = "\n".join(f.name for f in files)
        else:
            body = "No files received yet.\n\nWaiting for Android to send something…"

        rumps.alert(title="Recent Items", message=body, ok="Close")

    def toggle_send(self, sender):
        """Enable/disable pushing the Mac clipboard to Android."""
        sender.state = not sender.state
        server.set_watch_enabled(bool(sender.state))

    def quit_app(self, _):
        discovery.stop()
        rumps.quit_application()


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    AndroidDropApp().run()
