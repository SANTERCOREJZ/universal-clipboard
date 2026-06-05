#!/usr/bin/env bash
#
# Build AndroidDrop.app — a standalone Mac app you can launch by double-click,
# no Python or terminal needed afterwards.
#
#   ./build_app.sh
#
# Result:  mac/dist/AndroidDrop.app
#   → drag it into /Applications, then open it from Launchpad/Finder.
#
set -euo pipefail

cd "$(dirname "$0")"          # run from the mac/ directory
PY="../.venv/bin/python"

if [ ! -x "$PY" ]; then
  echo "Virtualenv not found at ../.venv"
  echo "Create it and install dependencies first:"
  echo "  python3 -m venv ../.venv"
  echo "  ../.venv/bin/pip install -r requirements.txt"
  exit 1
fi

if ! "$PY" -c "import py2app" 2>/dev/null; then
  echo "py2app is missing — installing it…"
  "$PY" -m pip install py2app
fi

echo "Generating app icon (AppIcon.icns)…"
"$PY" make_icon.py

echo "Cleaning previous build…"
# A mounted AndroidDrop.dmg makes Finder recreate .DS_Store mid-delete ("Directory
# not empty"); detach it first so the clean succeeds.
hdiutil detach "/Volumes/AndroidDrop" >/dev/null 2>&1 || true
rm -rf build dist
rm -rf build dist 2>/dev/null || true   # second pass in case Finder raced us

echo "Building AndroidDrop.app (this takes a minute)…"
"$PY" setup.py py2app

echo
echo "✓ Done:  mac/dist/AndroidDrop.app"
echo "  Drag it into /Applications, then launch it from Launchpad."
echo "  The icon appears in the menu bar (top-right) — there is no Dock icon."
