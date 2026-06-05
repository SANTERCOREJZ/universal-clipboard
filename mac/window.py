"""
Settings window for AndroidDrop (AppKit / PyObjC).

The app normally lives only in the menu bar (Accessory: no Dock icon). Opening this
window switches the app to Regular so a Dock icon + app menu appear while it's open,
and switches back to Accessory when it's closed — so the Dock icon shows up only when
you deliberately open the window.

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
    NSBox,
    NSBoxSeparator,
    NSButton,
    NSButtonTypeSwitch,
    NSColor,
    NSFont,
    NSForegroundColorAttributeName,
    NSImageView,
    NSMakeRect,
    NSOpenPanel,
    NSTextField,
    NSView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSAttributedString, NSObject

import clipboard
import config
import icons
import server
import settings
import tls

W, H = 480, 470
M = 24                      # left/right margin
FIELD_W = 312
BTN_X = M + FIELD_W + 8     # buttons sit to the right of the fields
BTN_W = W - BTN_X - M


def _label(rect, text, bold=False, size=12, color=None):
    f = NSTextField.alloc().initWithFrame_(rect)
    f.setStringValue_(text)
    f.setBezeled_(False)
    f.setDrawsBackground_(False)
    f.setEditable_(False)
    f.setSelectable_(False)
    f.setFont_(NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size))
    if color is not None:
        f.setTextColor_(color)
    return f


def _field(rect, value="", editable=True, mono=False):
    f = NSTextField.alloc().initWithFrame_(rect)
    f.setStringValue_(value)
    f.setEditable_(editable)
    f.setSelectable_(True)
    f.setBezeled_(True)
    f.setDrawsBackground_(True)
    if mono:
        f.setFont_(NSFont.monospacedSystemFontOfSize_weight_(10, 0))
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
        app.setApplicationIconImage_(icons.dock_image())               # ← our icon, not Python's
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
        win.setReleasedWhenClosed_(False)
        win.center()
        win.setDelegate_(self)
        c = win.contentView()
        secondary = NSColor.secondaryLabelColor()

        # Header: logo + title + subtitle
        logo = NSImageView.alloc().initWithFrame_(NSMakeRect(M, H - 70, 46, 46))
        logo.setImage_(icons.dock_image(46))
        c.addSubview_(logo)
        c.addSubview_(_label(NSMakeRect(M + 60, H - 48, W - M - 60, 24), "AndroidDrop", bold=True, size=18))
        c.addSubview_(_label(NSMakeRect(M + 60, H - 68, W - M - 60, 16),
                             "Clipboard & file sync with your Mac", color=secondary))

        c.addSubview_(self._sep(H - 88))

        # Status: colored dot + text
        self._dot = NSView.alloc().initWithFrame_(NSMakeRect(M, H - 112, 10, 10))
        self._dot.setWantsLayer_(True)
        self._dot.layer().setCornerRadius_(5.0)
        c.addSubview_(self._dot)
        self._status = _label(NSMakeRect(M + 18, H - 116, W - M - 18 - M, 18), "", bold=True, size=13)
        c.addSubview_(self._status)

        # Token
        c.addSubview_(_label(NSMakeRect(M, 314, W - 2 * M, 14),
                             "Shared token (must match the Android app)", color=secondary))
        self._token = _field(NSMakeRect(M, 286, FIELD_W, 24))
        c.addSubview_(self._token)
        c.addSubview_(self._button(NSMakeRect(BTN_X, 284, BTN_W, 28), "Save", "saveToken:", accent=True))

        # Save folder
        c.addSubview_(_label(NSMakeRect(M, 252, W - 2 * M, 14),
                             "Save folder (received files)", color=secondary))
        self._folder = _field(NSMakeRect(M, 224, FIELD_W, 24), editable=False)
        c.addSubview_(self._folder)
        c.addSubview_(self._button(NSMakeRect(BTN_X, 222, BTN_W, 28), "Change…", "chooseFolder:"))

        # Toggle
        self._send = NSButton.alloc().initWithFrame_(NSMakeRect(M, 186, W - 2 * M, 22))
        self._send.setButtonType_(NSButtonTypeSwitch)
        self._send.setTitle_("  Send clipboard to Android")
        self._send.setTarget_(self)
        self._send.setAction_("toggleSend:")
        c.addSubview_(self._send)

        c.addSubview_(self._sep(168))

        # Security code
        c.addSubview_(_label(NSMakeRect(M, 142, W - 2 * M, 14),
                             "Security code (the phone pins this on first connect)", color=secondary))
        self._pin = _field(NSMakeRect(M, 114, FIELD_W, 24), editable=False, mono=True)
        c.addSubview_(self._pin)
        c.addSubview_(self._button(NSMakeRect(BTN_X, 112, BTN_W, 28), "Copy", "copyPin:"))

        c.addSubview_(self._button(NSMakeRect(M, 64, 200, 30), "Open Received Folder", "openFolder:"))

        self._window = win

    @objc.python_method
    def _sep(self, y):
        box = NSBox.alloc().initWithFrame_(NSMakeRect(M, y, W - 2 * M, 1))
        box.setBoxType_(NSBoxSeparator)
        return box

    @objc.python_method
    def _button(self, rect, title, action, accent=False):
        b = NSButton.alloc().initWithFrame_(rect)
        b.setBezelStyle_(NSBezelStyleRounded)
        b.setTarget_(self)
        b.setAction_(action)
        if accent:
            b.setBezelColor_(NSColor.colorWithSRGBRed_green_blue_alpha_(0x44 / 255, 0x56 / 255, 0xE0 / 255, 1.0))
            b.setAttributedTitle_(NSAttributedString.alloc().initWithString_attributes_(
                title, {NSForegroundColorAttributeName: NSColor.whiteColor()}))
            b.setKeyEquivalent_("\r")
        else:
            b.setTitle_(title)
        return b

    @objc.python_method
    def _refresh(self):
        connected = len(server._ws_clients)
        addr = f"https://{server._local_ip()}:{config.PORT}"
        if connected:
            self._status.setStringValue_(f"Connected · {addr}")
            self._dot.layer().setBackgroundColor_(NSColor.systemGreenColor().CGColor())
        else:
            self._status.setStringValue_(f"Listening · {addr}")
            self._dot.layer().setBackgroundColor_(NSColor.systemGrayColor().CGColor())
        self._token.setStringValue_(settings.get("token"))
        self._folder.setStringValue_(str(settings.save_dir()))
        self._send.setState_(1 if settings.get("send_to_android") else 0)
        self._pin.setStringValue_(f"sha256/{tls.spki_pin()}")

    # ── Actions ─────────────────────────────────────────────────────────────
    def saveToken_(self, sender):
        value = self._token.stringValue().strip() or "changeme"
        settings.set("token", value)
        self._status.setStringValue_("Token saved — update it on the phone too")

    def chooseFolder_(self, sender):
        panel = NSOpenPanel.openPanel()
        panel.setCanChooseDirectories_(True)
        panel.setCanChooseFiles_(False)
        panel.setAllowsMultipleSelection_(False)
        if panel.runModal() == 1:  # NSModalResponseOK
            settings.set("save_dir", str(panel.URLs()[0].path()))
            self._folder.setStringValue_(str(settings.save_dir()))

    def toggleSend_(self, sender):
        server.set_watch_enabled(bool(sender.state()))

    def copyPin_(self, sender):
        # clipboard.set_text marks it as our own write so the watcher won't push the
        # security code to the phone.
        clipboard.set_text(f"sha256/{tls.spki_pin()}")
        self._status.setStringValue_("Security code copied to clipboard")

    def openFolder_(self, sender):
        subprocess.run(["open", str(settings.save_dir())], check=False)

    # ── Window delegate ─────────────────────────────────────────────────────
    def windowWillClose_(self, notification):
        NSApplication.sharedApplication().setActivationPolicy_(
            NSApplicationActivationPolicyAccessory
        )
