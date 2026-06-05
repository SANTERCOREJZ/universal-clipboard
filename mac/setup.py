"""
py2app build script — packages the Mac side into a standalone AndroidDrop.app
so it opens like a normal Mac app (double-click / Launchpad), no Python or
terminal needed.

Build from the mac/ directory:
    ../.venv/bin/python setup.py py2app

Result:
    mac/dist/AndroidDrop.app   ← drag into /Applications

Notes
-----
- LSUIElement=True makes it a menu-bar agent: icon in the top bar, no Dock icon.
- The heavy web stack (FastAPI/uvicorn/pydantic/zeroconf/websockets) imports a lot
  of its submodules dynamically, which py2app's import scanner can miss. Listing the
  whole packages under `packages` copies their full directories into the bundle, so
  those runtime imports resolve.
"""

from setuptools import setup

import config

APP = ["app.py"]

OPTIONS = {
    "argv_emulation": False,
    "plist": {
        "CFBundleName": config.APP_NAME,
        "CFBundleDisplayName": config.APP_NAME,
        "CFBundleIdentifier": "com.androiddrop.mac",
        "CFBundleVersion": config.VERSION,
        "CFBundleShortVersionString": config.VERSION,
        "LSUIElement": True,            # menu-bar agent: no Dock icon
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
    },
    "packages": [
        "rumps",
        "fastapi",
        "starlette",
        "uvicorn",
        "anyio",
        "h11",
        "click",
        "websockets",
        "zeroconf",
        "ifaddr",
        "pydantic",
        "pydantic_core",
        "annotated_types",
        "idna",
        "multipart",
        "cryptography",
        "cffi",
    ],
    "includes": ["config", "server", "clipboard", "discovery", "tls", "settings", "window",
                 "typing_extensions"],
}

setup(
    app=APP,
    name=config.APP_NAME,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
