"""Shared, testable logic used by both desktop GUI variants
(jadiv-timelapse.py and jadiv-timelapse_plus.py), the headless CLI
(jadiv-timelapse_cli.py) and the rendering module (timelapse_render.py):
finding photos, sorting them (by name, EXIF capture time or file modification
time), and computing the target video resolution while preserving aspect ratio.

This module must stay free of GUI and OpenCV/FFmpeg dependencies so it can be
tested anywhere. Pillow is imported lazily, only when EXIF sorting is requested.
"""
import glob
import os
import re
from datetime import datetime

SORT_NAME = "name"
SORT_EXIF = "exif"
SORT_MTIME = "mtime"
SORT_MODES = (SORT_NAME, SORT_EXIF, SORT_MTIME)

IMAGE_PATTERNS = ('/*.jpg', '/*.jpeg', '/*.png', '/*.JPG', '/*.JPEG', '/*.PNG')

# EXIF tag ids (see the EXIF 2.3 spec); DateTimeOriginal lives in the Exif sub-IFD
_EXIF_IFD_POINTER = 0x8769
_TAG_DATETIME_ORIGINAL = 0x9003
_TAG_SUBSEC_TIME_ORIGINAL = 0x9291
_EXIF_DATETIME_FORMAT = "%Y:%m:%d %H:%M:%S"


def natural_sort_key(path):
    """Splits a path into text/number chunks so photos sort numerically (e.g. 2 before 10), not purely alphabetically."""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r'(\d+)', path)]


def find_images(folder):
    """Returns the paths of all .jpg/.jpeg/.png photos in `folder` (unsorted, no duplicates).

    The set() also removes duplicates: on Windows/macOS "*.jpg" and "*.JPG" would otherwise
    match the same files twice.
    """
    images = set()
    for pattern in IMAGE_PATTERNS:
        images.update(glob.glob(glob.escape(folder) + pattern))
    return list(images)


def read_exif_datetime(path):
    """Returns the EXIF DateTimeOriginal (capture time) of a photo as a naive local datetime,
    including sub-second precision from SubSecTimeOriginal when the camera wrote it.

    Returns None if the file has no usable capture time (e.g. PNG, stripped metadata, unreadable
    file). Raises ImportError if Pillow is not installed.
    """
    from PIL import Image  # ImportError propagates: EXIF sorting needs Pillow

    try:
        with Image.open(path) as img:
            exif = img.getexif()
            exif_ifd = exif.get_ifd(_EXIF_IFD_POINTER)
            raw = exif_ifd.get(_TAG_DATETIME_ORIGINAL)
            subsec = exif_ifd.get(_TAG_SUBSEC_TIME_ORIGINAL)
    except Exception:
        return None

    if not raw:
        return None
    try:
        captured = datetime.strptime(str(raw).strip(), _EXIF_DATETIME_FORMAT)
    except ValueError:
        # e.g. the camera's "0000:00:00 00:00:00" placeholder
        return None

    digits = str(subsec or "").strip()
    if digits.isdigit():
        # SubSecTimeOriginal holds the fraction as digits, e.g. "25" means 0.25 s
        captured = captured.replace(microsecond=int((digits + "000000")[:6]))
    return captured


def _file_mtime(path):
    return datetime.fromtimestamp(os.path.getmtime(path))


def sort_image_paths(paths, sort_mode=SORT_NAME):
    """Returns `paths` in frame order for the given `sort_mode`:

    - SORT_NAME: natural sort of the full path (frame2 before frame10).
    - SORT_EXIF: EXIF DateTimeOriginal (capture time). Photos without one fall back to their
      file modification time, so mixed folders still get a sensible order.
    - SORT_MTIME: file modification time.

    Ties (e.g. a burst of shots within the same second) are broken by natural name order,
    so the result is deterministic.
    """
    if sort_mode == SORT_NAME:
        return sorted(paths, key=natural_sort_key)
    if sort_mode == SORT_EXIF:
        def time_of(path):
            return read_exif_datetime(path) or _file_mtime(path)
    elif sort_mode == SORT_MTIME:
        time_of = _file_mtime
    else:
        raise ValueError(f"Unknown sort mode: {sort_mode!r} (expected one of {', '.join(SORT_MODES)})")
    return sorted(paths, key=lambda path: (time_of(path), natural_sort_key(path)))


def compute_target_resolution(width, height, resolution_choice):
    """Computes the target video resolution from the UI selection (`resolution_choice`),
    preserving aspect ratio, and rounds the result to even numbers (required by video codecs).

    "Full HD"/"4K" denote the longer (horizontal) side of the video. For a portrait photo,
    they're therefore applied to the height instead of the width - otherwise you'd get an
    absurdly tall video instead of a sensible vertical format. "720p"/"480p"/"240p" denote
    the number of rows (height) and this applies regardless of photo orientation. If the
    selection doesn't match any of these labels (e.g. "Original"), the original resolution
    is returned (rounded to even numbers).
    """
    target_width = width
    target_height = height
    is_portrait = height > width

    if "Full HD" in resolution_choice:
        long_side = 1920
        if is_portrait:
            target_height = long_side
            target_width = int((long_side / height) * width)
        else:
            target_width = long_side
            target_height = int((long_side / width) * height)
    elif "4K" in resolution_choice:
        long_side = 3840
        if is_portrait:
            target_height = long_side
            target_width = int((long_side / height) * width)
        else:
            target_width = long_side
            target_height = int((long_side / width) * height)
    elif "720p" in resolution_choice:
        target_height = 720
        target_width = int((720 / height) * width)
    elif "480p" in resolution_choice:
        target_height = 480
        target_width = int((480 / height) * width)
    elif "240p" in resolution_choice:
        target_height = 240
        target_width = int((240 / height) * width)

    # MP4 codecs require both width and height to be even numbers, otherwise they fail
    target_width -= target_width % 2
    target_height -= target_height % 2

    return target_width, target_height


def compute_letterbox_layout(src_width, src_height, target_width, target_height):
    """Computes the size and offset needed to place a photo (src_width x src_height)
    onto a canvas with the target resolution (target_width x target_height) while
    preserving its original aspect ratio ("letterbox"/"pillarbox").

    The target resolution is derived from the first photo in the folder (see
    `compute_target_resolution`), so other photos with a different aspect ratio would be
    stretched/distorted if resized directly to those dimensions. Instead, the photo is
    scaled down so it fits entirely within the canvas, and the remaining space (black bars)
    is split evenly on both sides to keep it centered.

    Returns (new_width, new_height, x_offset, y_offset): new_width/new_height are the
    dimensions of the scaled photo, x_offset/y_offset is its position (offset from the
    canvas edge).
    """
    scale = min(target_width / src_width, target_height / src_height)
    new_width = min(max(round(src_width * scale), 1), target_width)
    new_height = min(max(round(src_height * scale), 1), target_height)
    x_offset = (target_width - new_width) // 2
    y_offset = (target_height - new_height) // 2

    return new_width, new_height, x_offset, y_offset
