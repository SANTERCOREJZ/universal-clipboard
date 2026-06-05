"""
Generate AppIcon.icns from icons.dock_image() so the bundled .app has a proper
Finder/Launchpad/Dock icon. Run once (or whenever the icon design changes):

    ../.venv/bin/python make_icon.py

build_app.sh runs this automatically before packaging.
"""

import os
import shutil
import subprocess

import icons


def main() -> None:
    iconset = "AppIcon.iconset"
    if os.path.exists(iconset):
        shutil.rmtree(iconset)
    os.makedirs(iconset)

    # (base point size, scale) → Apple's required iconset entries.
    for base, scale in [(16, 1), (16, 2), (32, 1), (32, 2), (128, 1), (128, 2),
                        (256, 1), (256, 2), (512, 1), (512, 2)]:
        suffix = "" if scale == 1 else "@2x"
        icons.write_png(os.path.join(iconset, f"icon_{base}x{base}{suffix}.png"), base * scale)

    subprocess.run(["iconutil", "-c", "icns", "-o", "AppIcon.icns", iconset], check=True)
    shutil.rmtree(iconset)
    print("wrote AppIcon.icns")


if __name__ == "__main__":
    main()
