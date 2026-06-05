# AndroidDrop — Universal Clipboard (Android ⇄ Mac)

Share your clipboard, files and screenshots between an Android phone and a Mac over
your local network — like AirDrop / Universal Clipboard, but for your own
cross‑platform devices. No cloud, no cables, no account.

- **Android → Mac:** Share something (or tap a button) on the phone → it lands on the
  Mac. Text/images go straight into the Mac clipboard; files are saved to a folder.
- **Mac → Android:** Copy on the Mac → a notification pops on the phone → one tap puts
  it in the Android clipboard. Screenshots are also saved to the gallery.
- **Zero‑config:** the phone finds the Mac automatically via mDNS, even after the Mac's
  IP changes.
- **Encrypted:** all traffic is HTTPS/WSS with public‑key pinning.

> Status: working MVP (v0.1.0). LAN only for now.

---

## Features

| | Android → Mac | Mac → Android |
|---|---|---|
| **Text** | ✅ into Mac clipboard | ✅ into Android clipboard (one tap) |
| **Images / screenshots** | ✅ clipboard + saved to `~/Downloads/AndroidDrop` | ✅ saved to gallery (`Pictures/AndroidDrop`) + clipboard |
| **Arbitrary files** | ✅ saved to the Mac folder | — |
| **Trigger** | Share Sheet, notification button, Quick‑Settings tile | automatic on copy → tap the notification |

Other niceties:

- **Auto‑discovery (mDNS):** the Mac advertises `_androiddrop._tcp`; the phone finds it
  with Android's `NsdManager`. If the Mac's IP changes, the app re‑discovers and self‑heals.
- **End‑to‑end‑ish encryption:** the Mac serves HTTPS/WSS with a self‑signed certificate;
  the phone pins the Mac's public key on first connect (trust‑on‑first‑use) and refuses a
  changed key (anti‑MITM). Pinning is by key, not IP, so address changes don't break it.
- **Shared‑secret auth:** every request carries an `x-token` header.
- **Menu‑bar app on macOS** with an optional settings window (no Dock icon unless you open it).

---

## How it works

```
 Android phone                         Mac (menu-bar app)
 ┌───────────────┐   HTTPS POST  ┌──────────────────────────┐
 │ Share / tile  │ ────────────▶ │ FastAPI server (:8765)    │
 │ /text /push   │               │  → NSPasteboard + folder  │
 ├───────────────┤   WSS push    ├──────────────────────────┤
 │ DropService   │ ◀──────────── │ clipboard watcher → /ws   │
 │ → notification│   pull /outbox│  (pushes new copies)      │
 └───────────────┘ ────────────▶ └──────────────────────────┘
        ▲  mDNS browse  ◀── _androiddrop._tcp advertise ──┘
```

- **Mac side (Python):** a FastAPI/uvicorn server wrapped in a [rumps](https://github.com/jaredks/rumps)
  menu‑bar app. It writes the system clipboard via `pyobjc`/`NSPasteboard`, watches the
  clipboard for outgoing changes, advertises itself over mDNS (`zeroconf`), and serves TLS.
- **Android side (Kotlin):** a small app that posts to the Mac (OkHttp) and keeps a
  WebSocket open via a foreground service to receive the Mac's clipboard. Writing/reading
  the Android clipboard happens in a tiny invisible activity because Android 10+ only allows
  clipboard access from a focused window.
- **Loop prevention:** content the Mac receives from the phone is not pushed back (NSPasteboard
  `changeCount` check).

---

## Requirements

- **Mac:** macOS 11+. To run from source: Python 3.11 (python.org framework build).
- **Android:** Android 8.0+ (API 26). Image *receiving* into the gallery needs Android 10+.
- Both devices on the **same local network**.

---

## Install & run

### Mac

**Option A — prebuilt app (Releases):** download `AndroidDrop.dmg`, drag `AndroidDrop.app`
into `Applications`, open it. The icon appears in the **menu bar** (top‑right), not the Dock.

> The app is not signed with an Apple Developer ID, so on first launch macOS may block it:
> right‑click the app → **Open**, or **System Settings → Privacy & Security → Open Anyway**.
> (Or remove the quarantine flag: `xattr -dr com.apple.quarantine /Applications/AndroidDrop.app`.)

**Option B — from source:**

```bash
cd mac
python3 -m venv ../.venv
../.venv/bin/pip install -r requirements.txt
../.venv/bin/python app.py
```

**Build the app/dmg yourself:**

```bash
cd mac
./build_app.sh     # → mac/dist/AndroidDrop.app
./make_dmg.sh      # → mac/dist/AndroidDrop.dmg
```

### Android

**Option A — prebuilt APK (Releases):** download `AndroidDrop.apk` and open it on the phone.
Android will ask you to allow installs from your browser/file manager — allow it. If Google
Play Protect warns about an unknown app, choose **Install anyway** (the app is sideloaded,
not from the Play Store).

**Option B — from source:** open the `android/` project in **Android Studio** and build/run
it (or `./gradlew assembleRelease` with your own signing config).

---

## Setup / pairing

1. Start **AndroidDrop** on the Mac. Open **Settings…** from the menu‑bar icon to see the
   address (`https://<ip>:8765`), the **shared token**, and the **security code**.
2. In the Android app, tap **Find Mac automatically** (mDNS) — or enter the Mac's IP manually.
3. Make sure the **token** matches on both sides (default `changeme` — change it in the Mac
   Settings window and in the Android app).
4. On the first connection the phone **pins the Mac's key** automatically. If you ever switch
   Macs or regenerate the certificate, tap **Reset pairing** in the Android settings.

---

## Usage

**Send from Android → Mac**

- **Share Sheet:** share any file/image/text → choose AndroidDrop.
- **Notification button:** the persistent "AndroidDrop" notification has a *Send Clipboard* action.
- **Quick‑Settings tile:** add the AndroidDrop tile to the quick‑settings panel and tap it.

**Send from Mac → Android**

- Just copy something on the Mac. A **"Copied on Mac"** notification appears on the phone;
  **tap it** to drop the content into the Android clipboard (screenshots are saved to the gallery).
- Toggle this off anytime via **Send clipboard to Android** in the Mac menu / Settings window.

---

## Security

- All traffic is **HTTPS/WSS**. The Mac generates a self‑signed cert + key once
  (`~/Library/Application Support/AndroidDrop/`) and reuses it.
- The phone uses **trust‑on‑first‑use public‑key pinning**: it remembers the Mac's key on the
  first connection and rejects any later key change (defends against man‑in‑the‑middle). The
  first connection is the only TOFU window — verify the **Security code** in the Mac's Settings
  window if you want to be certain.
- A **shared token** (`x-token`) authenticates every request. Change it from the default.
- LAN only today; for use outside your home network, put both devices on a
  [Tailscale](https://tailscale.com) network (WireGuard‑encrypted) — planned as a future step.

---

## Limitations & notes

- **One tap on Android** is required to paste/save what the Mac sent — Android forbids writing
  the clipboard from the background, so a brief (invisible) activity does it on tap.
- The distributed `.app`/`.dmg` is **unsigned** (ad‑hoc); see the Gatekeeper note above.
- Image *receiving* into the gallery requires **Android 10+**.

---

## Tech stack

- **Mac:** Python, FastAPI + uvicorn, websockets, zeroconf, cryptography, pyobjc, rumps,
  packaged with py2app.
- **Android:** Kotlin, OkHttp, Coroutines, Material 3, `NsdManager`, foreground service.

## License

[MIT](LICENSE) © 2026 Alex Kireev
