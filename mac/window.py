"""
Settings window for AndroidDrop (AppKit / PyObjC).

The app normally lives only in the menu bar (Accessory: no Dock icon). Opening this
window switches the app to Regular so a Dock icon + app menu appear while it's open,
and switches back to Accessory when it's closed — so the Dock icon shows up only when
you deliberately open the window.

Same functionality as the menu, plus editable token and save-folder.
Layout uses fixed frames (origin is bottom-left) to keep it simple and predictable.
"""

import subprocess

import objc
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSApplicationActivationPolicyRegular,
    NSBackingStoreBuffered,
    NSBezelStyleRounded,
    NSButton,
    NSButtonTypeSwitch,
    NSFont,
    NSMakeRect,
    NSOpenPanel,
    NSTextField,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSObject

import clipboard
import config
import server
import settings
import tls

W, H = 440, 380


def _label(rect, text, bold=False, size=12, mono=False):
    f = NSTextField.alloc().initWithFrame_(rect)
    f.setStringValue_(text)
    f.setBezeled_(False)
    f.setDrawsBackground_(False)
    f.setEditable_(False)
    f.setSelectable_(not bold)
    if mono:
        f.setFont_(NSFont.monospacedSystemFontOfSize_weight_(11, 0))
    else:
        f.setFont_(NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size))
    return f


def _field(rect, value="", editable=True):
    f = NSTextField.alloc().initWithFrame_(rect)
    f.setStringValue_(value)
    f.setEditable_(editable)
    f.setSelectable_(True)
    f.setBezeled_(True)
    f.setDrawsBackground_(True)
    return f


class SettingsWindow(NSObject):
    def init(self):
        self = objc.super(SettingsWindow, self).init()
        if self is None:
            return None
        self._window = None
        return self

    # ── Public ──────────────────────────────────────────────────────────────
    @objc.python_method
    def show(self):
        if self._window is None:
            self._build()
        self._refresh()
        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyRegular)  # Dock icon while open
        app.activateIgnoringOtherApps_(True)
        self._window.makeKeyAndOrderFront_(None)

    # ── Build ───────────────────────────────────────────────────────────────
    @objc.python_method
    def _build(self):
        style = (
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskMiniaturizable
        )
        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, W, H), style, NSBackingStoreBuffered, False
        )
        win.setTitle_("AndroidDrop")
        win.setReleasedWhenClosed_(False)  # reuse the same window on reopen
        win.center()
        win.setDelegate_(self)
        content = win.contentView()

        self._status = _label(NSMakeRect(20, 346, W - 40, 20), "", bold=True, size=13)
        content.addSubview_(self._status)

        content.addSubview_(_label(NSMakeRect(20, 312, W - 40, 16),
                                   "Shared token (must match the Android app)"))
        self._token = _field(NSMakeRect(20, 284, 300, 24))
        content.addSubview_(self._token)
        content.addSubview_(self._button(NSMakeRect(330, 282, 90, 28), "Save", "saveToken:"))

        content.addSubview_(_label(NSMakeRect(20, 246, W - 40, 16), "Save folder (received files)"))
        self._folder = _field(NSMakeRect(20, 218, 300, 24), editable=False)
        content.addSubview_(self._folder)
        content.addSubview_(self._button(NSMakeRect(330, 216, 90, 28), "Change…", "chooseFolder:"))

        self._send = NSButton.alloc().initWithFrame_(NSMakeRect(20, 180, W - 40, 22))
        self._send.setButtonType_(NSButtonTypeSwitch)
        self._send.setTitle_("Send clipboard to Android")
        self._send.setTarget_(self)
        self._send.setAction_("toggleSend:")
        content.addSubview_(self._send)

        content.addSubview_(_label(NSMakeRect(20, 148, W - 40, 16),
                                   "Security code (phone pins this on first connect)"))
        self._pin = _field(NSMakeRect(20, 120, 300, 24), editable=False)
        self._pin.setFont_(NSFont.monospacedSystemFontOfSize_weight_(10, 0))
        content.addSubview_(self._pin)
        content.addSubview_(self._button(NSMakeRect(330, 118, 90, 28), "Copy", "copyPin:"))

        content.addSubview_(self._button(NSMakeRect(20, 78, 200, 28),
                                         "Open Received Folder", "openFolder:"))

        self._window = win

    @objc.python_method
    def _button(self, rect, title, action):
        b = NSButton.alloc().initWithFrame_(rect)
        b.setTitle_(title)
        b.setBezelStyle_(NSBezelStyleRounded)
        b.setTarget_(self)
        b.setAction_(action)
        return b

    @objc.python_method
    def _refresh(self):
        self._status.setStringValue_(f"● Listening on https://{server._local_ip()}:{config.PORT}")
        self._token.setStringValue_(settings.get("token"))
        self._folder.setStringValue_(str(settings.save_dir()))
        self._send.setState_(1 if settings.get("send_to_android") else 0)
        self._pin.setStringValue_(f"sha256/{tls.spki_pin()}")

    # ── Actions ─────────────────────────────────────────────────────────────
    def saveToken_(self, sender):
        value = self._token.stringValue().strip() or "changeme"
        settings.set("token", value)
        self._status.setStringValue_("● Token saved — update it on the phone too")

    def chooseFolder_(self, sender):
        panel = NSOpenPanel.openPanel()
        panel.setCanChooseDirectories_(True)
        panel.setCanChooseFiles_(False)
        panel.setAllowsMultipleSelection_(False)
        if panel.runModal() == 1:  # NSModalResponseOK
            path = panel.URLs()[0].path()
            settings.set("save_dir", str(path))
            self._folder.setStringValue_(str(settings.save_dir()))

    def toggleSend_(self, sender):
        server.set_watch_enabled(bool(sender.state()))

    def copyPin_(self, sender):
        # Use clipboard.set_text so the watcher treats it as our own write and does
        # NOT push the security code to the phone.
        clipboard.set_text(f"sha256/{tls.spki_pin()}")
        self._status.setStringValue_("● Security code copied to clipboard")

    def openFolder_(self, sender):
        subprocess.run(["open", str(settings.save_dir())], check=False)

    # ── Window delegate ─────────────────────────────────────────────────────
    def windowWillClose_(self, notification):
        # Back to menu-bar-only: Dock icon disappears again.
        NSApplication.sharedApplication().setActivationPolicy_(
            NSApplicationActivationPolicyAccessory
        )
