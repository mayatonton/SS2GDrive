# SS2GDrive

Tiny Wayland-friendly “snap & share” tools for Google Drive.
Take an interactive screenshot or record a screen region, upload to Drive, copy the share link, and (optionally) open it in your browser — all from a Flatpak-sandboxed app.

---

## Features

* **Screenshot (“Shot”)**

  * Portal-native interactive rectangle selection
  * Uploads to Drive and copies the share link
  * PNG or JPEG (quality configurable)

* **Screen Recording (“Record”)**

  * Select a region once, then **Start / Stop & Upload**
  * Encodes **VP8 + Opus** to WebM via GStreamer
  * Captures **system audio** (PulseAudio / PipeWire “monitor” source)
  * Subtle always-on overlay outlining the selected region

* **Drive integration**

  * Choose an upload folder (by ID)
  * “Anyone with the link can view” toggle
  * OAuth stored in the Flatpak config dir

* **Tray helper**

  * Quick “Snap & Upload”
  * Opens Settings

---

## Requirements

* Linux desktop with **PipeWire + xdg-desktop-portal** (Wayland recommended)
* Flatpak runtime: `org.kde.Platform//6.7` (used by the manifest)
* Google Cloud **OAuth Client (Desktop)** JSON (`client_secret.json`)
* GStreamer plugins (provided by the runtime), PulseAudio/ PipeWire for audio

> **Note:** On Wayland, the system **screen-share portal dialog will appear** when starting a capture. This is by design for security; apps cannot silently bypass it.

---

## Install (from source, Flatpak)

```bash
git clone https://github.com/mayatonton/SS2GDrive.git
cd SS2GDrive/flatpak
flatpak-builder --user --install --force-clean build-dir com.ss2gd.SS2GDrive.json
```

This builds and installs `com.ss2gd.SS2GDrive` into your user Flatpak.

---

## First-time setup

1. Launch **Settings**

   * App launcher: “SS2GDrive Settings”
   * or CLI: `flatpak run com.ss2gd.SS2GDrive settings`

2. Click **“Import client_secret.json…”** and choose your Google OAuth **Desktop** client file.

3. Click **“Sign in to Google…”** and complete the flow.

4. Optional:

   * **Drive Folder ID**: paste the folder’s ID if you want uploads to land there.
   * **Sharing**: enable “Anyone with the link can view”.
   * **Image format / JPEG quality**: for screenshots.

All settings and tokens live under:

```
~/.var/app/com.ss2gd.SS2GDrive/config/ss2gdrive/
  ├── settings.json
  ├── client_secret.json
  └── token.json
```

---

## Usage

### From the launcher

* **SS2GDrive Shot** – interactive screenshot → upload → link copied/opened
* **SS2GDrive Record** – region selector + Start / Stop & Upload window
* **SS2GDrive** – tray helper (with “Snap & Upload” and “Settings…”)

### From the CLI

```bash
# Screenshot
flatpak run com.ss2gd.SS2GDrive shot

# Recording UI (Start / Stop & Upload)
flatpak run com.ss2gd.SS2GDrive record-ui

# Legacy one-shot CLI recording (fixed duration)
flatpak run com.ss2gd.SS2GDrive record --duration=5 --fps=30

# Tray (fallback mini-window with --window)
flatpak run com.ss2gd.SS2GDrive tray [--window]

# Settings dialog
flatpak run com.ss2gd.SS2GDrive settings

# Manual auth
flatpak run com.ss2gd.SS2GDrive auth
```

### Where files go

* **Recordings** are saved before upload to: `~/Videos/SS2GDrive/REC_YYYYmmdd_HHMMSS.webm`
* **Screenshots** are taken via the portal and uploaded; local temp files are ephemeral.

---

## Audio capture (system audio)

By default, the recorder tries to use your **default sink’s monitor** (e.g. `…hdmi-stereo.monitor`).
If your recording is silent, pick a device explicitly:

* **Quick test inside the sandbox**

  ```bash
  flatpak run --command=sh com.ss2gd.SS2GDrive -c \
    'pactl list short sources | awk "{print \$2}" | grep monitor'
  ```

* **Force a device (temporary, per launch)**

  ```bash
  SS2GD_AUDIO_MONITOR=alsa_output.pci-0000_01_00.1.hdmi-stereo.monitor \
  flatpak run com.ss2gd.SS2GDrive record-ui
  ```

If you package your own build, ensure the manifest has:

```
--socket=pulseaudio
```

in `finish-args`.

---

## How it works (brief)

* **Screenshot**: calls the `org.freedesktop.portal.Screenshot` method via **dbus-next**.
* **Screencast**: uses `org.freedesktop.portal.ScreenCast` → PipeWire fd → **GStreamer**:

  ```
  pipewiresrc (path=<node>) ! videoconvert ! videoscale ! videorate !
  video/x-raw,format=I420,framerate=30/1 ! videocrop(top/left/right/bottom) !
  vp8enc ! webmmux
  +
  pulsesrc (device=<monitor>) ! audioconvert ! audioresample ! opusenc ! webmmux
  ```
* **Drive upload**: **google-api-python-client** to create file and (optionally) set a public read permission. Link is copied to clipboard and opened.

---

## Troubleshooting

* **“client_secret.json not found”**
  Open **Settings → Import client_secret.json…**, then **Sign in** again.

* **Portal dialog appears every time**
  That’s expected on many desktops; the portal controls consent.

* **No audio in the recording**
  Set `SS2GD_AUDIO_MONITOR=<your monitor device>`. Verify with the `pactl` query above.

* **Recording fails with GStreamer errors**
  Ensure PipeWire/portal are running. The app requests node IDs from the portal and uses `path=` on `pipewiresrc`. VP8/Opus/WebM plugins must be available (they are in the KDE 6.7 runtime).

* **Link not opening**
  The link is still copied to the clipboard. Browser launch can be blocked by the sandbox; open manually if needed.

---

## Development

Project layout (key bits):

```
app/ss2gd/
  cli.py                  # entrypoints: shot, record-ui, tray, etc.
  screenshot_portal.py    # xdg-desktop-portal: Screenshot
  screencast_portal.py    # xdg-desktop-portal: ScreenCast
  recorder.py             # start/stop GStreamer pipeline, upload
  region_select.py        # Qt overlay rectangle selector
  ui/
    record.py             # Start / Stop & Upload window
    settings.py           # settings dialog
    tray.py               # tray helper
  drive_uploader.py       # Google Drive API wrapper
  config.py               # paths & settings helpers
  notify.py, clipboard.py # niceties
flatpak/com.ss2gd.SS2GDrive.json
assets/*.desktop, *.svg
```

Build & run hot-loop:

```bash
# Rebuild the Flatpak
cd flatpak
flatpak-builder --user --install --force-clean build-dir com.ss2gd.SS2GDrive.json

# Run a command
flatpak run com.ss2gd.SS2GDrive record-ui
```

---

## License

MIT

---

## Acknowledgements

* PipeWire, xdg-desktop-portal, GStreamer, PySide6
* Google Drive API client for Python

---

If you hit a snag, run with `SS2GD_DEBUG=1` and paste the log when filing an issue.
