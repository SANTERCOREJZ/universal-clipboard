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
import settings
import tls
import window
from server import app as fastapi_app, _local_ip
from AppKit import NSApplication, NSApplicationActivationPolicyAccessory


# ── Server thread ─────────────────────────────────────────────────────────────

def _run_server() -> None:
    """Run the FastAPI/uvicorn server over HTTPS. Called in a background thread."""
    cert_file, key_file = tls.ensure_cert()
    uv_config = uvicorn.Config(
        fastapi_app,
        host=config.HOST,
        port=config.PORT,
        log_level="warning",       # quieter console output
        ssl_certfile=cert_file,    # self-signed → HTTPS + WSS
        ssl_keyfile=key_file,
    )
    uvicorn.Server(uv_config).run()


# ── Menu bar app ──────────────────────────────────────────────────────────────

class AndroidDropApp(rumps.App):
    def __init__(self):
        # "⬇" is a temporary text icon; replace with a real .png later.
        # rumps.App(title, icon=path) — icon must be a 22×22 px template image.
        super().__init__("AndroidDrop", title="⬇", quit_button=None)

        # Menu-bar app with no Dock icon. The Settings window switches us to a regular
        # (Dock-visible) app only while it is open.
        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        self.settings_window = window.SettingsWindow.alloc().init()

        # Toggle for the Mac → Android direction. Checked = the Mac pushes every
        # new copy to connected phones. Reflects the persisted setting.
        self.send_item = rumps.MenuItem("Send clipboard to Android", callback=self.toggle_send)
        self.send_item.state = 1 if settings.get("send_to_android") else 0

        self.menu = [
            rumps.MenuItem("Settings…",            callback=self.open_settings),
            rumps.MenuItem("Open Received Folder", callback=self.open_folder),
            rumps.MenuItem("Recent Items",         callback=self.show_recent),
            None,  # separator
            self.send_item,
            None,
            rumps.MenuItem(f"Listening on  https://{_local_ip()}:{config.PORT}"),  # informational
            rumps.MenuItem("Show Security Code", callback=self.show_pin),
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

    def open_settings(self, _):
        """Open the settings window (also makes the app appear in the Dock while open)."""
        self.settings_window.show()

    def open_folder(self, _):
        """Open the received-files folder in Finder."""
        subprocess.run(["open", str(settings.save_dir())], check=False)

    def show_recent(self, _):
        """Show the 5 most recently received files in an alert dialog."""
        files = sorted(
            settings.save_dir().glob("*"),
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

    def show_pin(self, _):
        """Show the TLS public-key pin so you can verify the phone trusts THIS Mac."""
        rumps.alert(
            title="Security Code (TLS key pin)",
            message=(
                "Your phone trusts this Mac on first connect. If the Android app ever "
                "shows a security warning, compare this code with the one on the phone:\n\n"
                f"sha256/{tls.spki_pin()}"
            ),
            ok="Close",
        )

    def quit_app(self, _):
        discovery.stop()
        rumps.quit_application()


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    AndroidDropApp().run()
