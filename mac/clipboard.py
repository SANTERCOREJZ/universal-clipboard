"""
Thin wrapper around macOS NSPasteboard (the system clipboard).

NSPasteboard is the native macOS clipboard API, accessed here via pyobjc —
a Python bridge that lets us call Objective-C / macOS frameworks directly.

Usage:
    clipboard.set_image(path)   # image file → clipboard (Cmd+V pastes it)
    clipboard.set_text("hello") # plain text  → clipboard
"""

from pathlib import Path
from AppKit import NSPasteboard, NSPasteboardTypeString, NSImage


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
    return True


def set_text(text: str) -> None:
    """Write plain text to the macOS clipboard."""
    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setString_forType_(text, NSPasteboardTypeString)
