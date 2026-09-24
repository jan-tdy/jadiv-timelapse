"""Shared, testable logic used by both desktop GUI variants
(jadiv-timelapse.py and jadiv-timelapse_plus.py): natural sorting of files
by name and computing the target video resolution while preserving aspect ratio.
"""
import re


def natural_sort_key(path):
    """Splits a path into text/number chunks so photos sort numerically (e.g. 2 before 10), not purely alphabetically."""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r'(\d+)', path)]


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
