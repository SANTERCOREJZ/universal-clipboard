"""
App icons drawn at runtime so the menu-bar and Dock match the Android app.

The arrows come from the system SF Symbol "arrow.up.arrow.down" (same up/down
sync motif as the Android launcher icon), so there are no PNG assets to ship for
the menu bar. The Dock / .app icon is the same arrows in white on the brand-indigo
rounded square.
"""

from AppKit import (
    NSBezierPath,
    NSBitmapImageFileTypePNG,
    NSBitmapImageRep,
    NSColor,
    NSCompositingOperationSourceAtop,
    NSCompositingOperationSourceOver,
    NSDeviceRGBColorSpace,
    NSGraphicsContext,
    NSImage,
    NSRectFillUsingOperation,
)
from Foundation import NSMakeRect, NSZeroRect

_SYMBOL = "arrow.up.arrow.down"
_INDIGO = (0x3B / 255.0, 0x49 / 255.0, 0xDF / 255.0)


def _arrows(size: float):
    """The SF Symbol arrows as a square NSImage of the given point size."""
    img = NSImage.imageWithSystemSymbolName_accessibilityDescription_(_SYMBOL, None)
    if img is None:  # extremely old macOS fallback
        img = NSImage.alloc().initWithSize_((size, size))
    img = img.copy()
    img.setSize_((size, size))
    return img


def menubar_image():
    """Template image for the status-bar item (macOS tints it for light/dark)."""
    img = _arrows(18.0)
    img.setTemplate_(True)
    return img


def _tinted(image, color):
    """Return a copy of an (alpha) image recolored with `color`."""
    img = image.copy()
    img.setTemplate_(False)
    img.lockFocus()
    color.set()
    NSRectFillUsingOperation(
        NSMakeRect(0, 0, img.size().width, img.size().height),
        NSCompositingOperationSourceAtop,
    )
    img.unlockFocus()
    return img


def dock_image(S: float = 512.0):
    """Brand-indigo rounded square with white arrows — the Dock / Finder icon."""
    arrows = _tinted(_arrows(S * 0.6), NSColor.whiteColor())

    img = NSImage.alloc().initWithSize_((S, S))
    img.lockFocus()

    NSColor.colorWithSRGBRed_green_blue_alpha_(_INDIGO[0], _INDIGO[1], _INDIGO[2], 1.0).set()
    inset = S * 0.10
    NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        NSMakeRect(inset, inset, S - 2 * inset, S - 2 * inset), S * 0.22, S * 0.22
    ).fill()

    aw, ah = arrows.size()
    target = S * 0.5
    scale = target / max(aw, ah)
    dw, dh = aw * scale, ah * scale
    arrows.drawInRect_fromRect_operation_fraction_(
        NSMakeRect((S - dw) / 2, (S - dh) / 2, dw, dh),
        NSZeroRect, NSCompositingOperationSourceOver, 1.0,
    )

    img.unlockFocus()
    return img


def write_png(path: str, px: int):
    """
    Render the Dock icon at EXACTLY `px` pixels and write it as PNG (used for .icns).

    We draw into an explicit px-sized bitmap rep instead of NSImage.lockFocus(), because
    on a Retina display lockFocus uses a 2× backing store and would silently double the
    pixel dimensions — which breaks the strict size names iconutil expects.
    """
    src = dock_image(float(px))
    rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, px, px, 8, 4, True, False, NSDeviceRGBColorSpace, 0, 0
    )
    rep.setSize_((px, px))

    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.setCurrentContext_(
        NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
    )
    src.drawInRect_fromRect_operation_fraction_(
        NSMakeRect(0, 0, px, px), NSZeroRect, NSCompositingOperationSourceOver, 1.0
    )
    NSGraphicsContext.restoreGraphicsState()

    png = rep.representationUsingType_properties_(NSBitmapImageFileTypePNG, {})
    png.writeToFile_atomically_(path, True)
