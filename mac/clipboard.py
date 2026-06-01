"""
Thin wrapper around macOS NSPasteboard (the system clipboard).

NSPasteboard is the native macOS clipboard API, accessed here via pyobjc —
a Python bridge that lets us call Objective-C / macOS frameworks directly.

Two directions:
    Android → Mac:  set_image(path) / set_text(text)   — write into the clipboard
    Mac → Android:  read_outgoing()                     — read what the user copied,
                                                          so we can push it to the phone

`change_count()` is NSPasteboard's monotonically increasing counter; it ticks every
time *anything* writes to the clipboard. The Mac→Android watcher polls it to notice
new copies. To avoid a feedback loop (we write something that came FROM Android, the
watcher sees the change and sends it back), set_image/set_text record the change count
they caused in `last_self_change()`, and the watcher skips that one.
"""

from pathlib import Path

from AppKit import (
    NSBitmapImageFileTypePNG,
    NSBitmapImageRep,
    NSImage,
    NSPasteboard,
    NSPasteboardTypePNG,
    NSPasteboardTypeString,
    NSPasteboardTypeTIFF,
)

_last_self_change = -1


# ── Writing (Android → Mac) ─────────────────────────────────────────────────

def set_image(path: Path) -> bool:
    """
    Write an image file to the macOS clipboard.

    NSImage can load PNG, JPEG, GIF, TIFF, and most other common formats.
    writeObjects_() lets the image pick its own pasteboard types (TIFF + PNG),
    which is what apps like Preview and Finder expect.

    Returns True on success, False if the file couldn't be loaded as an image.
    """
    image = NSImage.alloc().initWithContentsOfFile_(str(path))
    if not image:
        return False

    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.writeObjects_([image])
    _note_self(pb)
    return True


def set_text(text: str) -> None:
    """Write plain text to the macOS clipboard."""
    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setString_forType_(text, NSPasteboardTypeString)
    _note_self(pb)


# ── Reading (Mac → Android) ─────────────────────────────────────────────────

def change_count() -> int:
    """NSPasteboard's change counter — ticks on every clipboard write."""
    return NSPasteboard.generalPasteboard().changeCount()


def last_self_change() -> int:
    """The change count of the most recent write WE caused (to skip echoes)."""
    return _last_self_change


def read_outgoing():
    """
    Read the current clipboard for sending to Android.

    Returns one of:
        ("text",  "the string")
        ("image", (png_bytes, "clipboard.png", "image/png"))
        (None, None)   if the clipboard holds nothing we can send
    Images are always normalised to PNG.
    """
    pb = NSPasteboard.generalPasteboard()
    types = [str(t) for t in (pb.types() or [])]

    if str(NSPasteboardTypePNG) in types:
        data = pb.dataForType_(NSPasteboardTypePNG)
        if data:
            return ("image", (bytes(data), "clipboard.png", "image/png"))

    if str(NSPasteboardTypeTIFF) in types:
        tiff = pb.dataForType_(NSPasteboardTypeTIFF)
        if tiff:
            rep = NSBitmapImageRep.imageRepWithData_(tiff)
            png = rep.representationUsingType_properties_(NSBitmapImageFileTypePNG, {})
            if png:
                return ("image", (bytes(png), "clipboard.png", "image/png"))

    if str(NSPasteboardTypeString) in types:
        s = pb.stringForType_(NSPasteboardTypeString)
        if s:
            return ("text", str(s))

    return (None, None)


def _note_self(pb) -> None:
    """Remember the change count we just produced, so the watcher won't echo it."""
    global _last_self_change
    _last_self_change = pb.changeCount()
