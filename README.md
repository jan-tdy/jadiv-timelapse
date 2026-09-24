# Jadiv-Timelapse
**If you found this useful, please give this repo a star!** **Also check out my other repos!**

You can take a look at my issue and pr queue if you are wondering why is something stale for days [here](https://github.com/issues/assigned?q=is%3Aissue+or+is%3Apr+state%3Aopen+archived%3Afalse+user%3Ajan-tdy+sort%3Acreated-asc)

A simple tool for creating a timelapse video from a sequence of photos (e.g. from a camera on a tripod). Pick a folder of photos, set the frame rate and target resolution, and the tool assembles them into the resulting video.

You can view a demo video [here](https://jan-tdy.github.io/jadiv-timelapse/0.mp4).

<img width="675" height="497" alt="image" src="https://github.com/user-attachments/assets/e683753f-8696-4c76-9cc5-647991cb0ce2" />


The project contains three independent variants with the same functionality — pick whichever suits you:

| File | Description | Requires | Status |
|---|---|---|---|
| `jadiv-timelapse_plus.py` | More advanced desktop GUI with a dark theme (PyQt5) — **recommended version** | Python 3, OpenCV, PyQt5 | Maintained |
| `docs/index.html` | Web version — runs directly in the browser, no installation needed | Modern browser (Chrome/Edge/Firefox) | Maintained |
| `jadiv-timelapse.py` | Simple desktop GUI (Tkinter) | Python 3, OpenCV | ⚠️ Unmaintained (legacy) |

> **`jadiv-timelapse.py` (Tkinter version) is unmaintained.** It stays in the repository for people who already use it, but it is no longer developed and new bugs in it are not fixed. For new installs, use `jadiv-timelapse_plus.py` or the web version.

## Features

- Create a timelapse video from `.jpg` / `.jpeg` / `.png` photos (including large JPGs from cameras)
- Adjustable frame rate (FPS)
- Optional target resolution (4K, Full HD, HD, SD, low quality, or original resolution) with aspect ratio preserved
- Photos with a different aspect ratio than the first one (e.g. a folder mixing portrait and landscape shots) are letterboxed/pillarboxed onto the target resolution instead of being stretched/distorted (desktop `_plus` version and web version; the unmaintained legacy Tkinter version still stretches them)
- Shows processing progress and lets you cancel processing at any time
- Processing runs in the background (the GUI/page never freezes)
- On startup, the app (desktop `_plus` version and web version) checks GitHub for a newer release and shows a notification if one is available; the current version is shown in the corner of the window/page
- A short "Made by Jadiv-Timelapse" watermark with a link to this repo is appended to the last 4 seconds of the generated video; toggle it off in the UI (or run `jadiv-timelapse_plus.py` with `--nomark` to have it start unchecked)

## Requirements and installation (desktop versions)

You need Python 3.8+, a system `ffmpeg` install, and the following libraries:

```bash
pip install -r requirements.txt
```

> **Getting `error: externally-managed-environment`?** Recent Debian/Ubuntu/Fedora
> ship a system Python that blocks `pip install` outside a virtual environment
> (PEP 668). Install into a venv instead of system-wide:
> ```bash
> python3 -m venv .venv
> source .venv/bin/activate   # Windows: .venv\Scripts\activate
> pip install -r requirements.txt
> python3 jadiv-timelapse_plus.py   # run inside the same activated venv
> ```

`jadiv-timelapse_plus.py` shells out to `ffmpeg` for H.264 video encoding (OpenCV's own pip build can only encode MPEG-4, which mobile apps and Instagram reject), so `ffmpeg` must be on your `PATH`:

```bash
# Debian / Ubuntu
sudo apt install ffmpeg
# Fedora
sudo dnf install ffmpeg
# macOS
brew install ffmpeg
# Windows
winget install ffmpeg
```

`jadiv-timelapse.py` additionally uses `tkinter`, which ships with the standard Python installation on Windows and macOS. On Linux you can install it via your package manager, e.g.:

```bash
# Debian / Ubuntu
sudo apt install python3-tk
```

## Usage

### Desktop Plus version (PyQt5) — recommended

```bash
python3 jadiv-timelapse_plus.py
```

### Web version

Runs directly at **[jan-tdy.github.io/jadiv-timelapse](https://jan-tdy.github.io/jadiv-timelapse/)** (GitHub Pages) — nothing to install, just open the link in a browser.

It can also be run locally without an internet connection — download `docs/index.html` and open it in a browser (double-click, or via `File > Open`). In both cases the photos are processed locally in the browser and are never uploaded anywhere. The output is a `.webm` video.

### Desktop version (Tkinter, unmaintained)

```bash
python3 jadiv-timelapse.py
```

In both desktop versions, simply:

1. Select the folder with the photos.
2. Choose where and under what name the resulting video should be saved (`.mp4`).
3. Set the FPS and target resolution.
4. Click **CREATE TIMELAPSE** (`jadiv-timelapse_plus.py`) or **VYTVORIŤ TIMELAPSE** (the legacy, still-Slovak `jadiv-timelapse.py`) — or press Enter.

Processing can be interrupted at any time with the **Cancel** button (**Zrušiť** on the legacy version).

## Notes

- Photos are sorted by file name using natural (numeric) sorting — so `frame2.jpg` sorts before `frame10.jpg`, even without leading zeros in the number. It's still worth using a consistent naming format (e.g. `IMG_0001.jpg`, `IMG_0002.jpg`, ...).
- Corrupted or unreadable photos are skipped during processing and are not included in the video.
- MP4/WebM codecs require an even width and height for the video — the tool handles this automatically.

## Testing

The natural-sort and resolution/aspect-ratio math shared by all three variants lives in a single testable place per variant: `timelapse_core.py` (used by both `.py` GUIs) and `docs/resolution.js` (used by the web version).

```bash
# Python (both desktop variants)
pip install -r requirements-dev.txt
pytest

# Web version
node docs/test/resolution.test.js
```

## Releases

The project publishes versions via [GitHub Releases](https://github.com/jan-tdy/jadiv-timelapse/releases) — the release tag is also the version shown to users (e.g. in JapySoft Code Master, which downloads the app based on the latest release, not the latest commit on the branch).

## License

This project is available under the license found in the [LICENSE](LICENSE) file.
