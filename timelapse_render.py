"""Headless rendering pipeline shared by the desktop GUI (jadiv-timelapse_plus.py) and the
command-line tool (jadiv-timelapse_cli.py): reads the photos in a folder in the chosen order,
letterboxes them onto the target resolution, appends the closing watermark and encodes the
video with FFmpeg (H.264).

Nothing in here depends on a GUI toolkit - progress is reported through a callback and
cancellation is polled through a callable.
"""
import os
import shutil
import subprocess
import tempfile
import threading

import cv2
import numpy as np

from timelapse_core import (
    compute_letterbox_layout,
    compute_target_resolution,
    find_images,
    sort_image_paths,
)

GITHUB_REPO = "jan-tdy/jadiv-timelapse"

OUTRO_DURATION_SECONDS = 4
OUTRO_LINE1 = "Made by Jadiv-Timelapse"
OUTRO_LINE2 = "Simple timelapse creation - no command-line needed"
OUTRO_LINE3 = f"If you like this, star us on GitHub: github.com/{GITHUB_REPO}"

# (text, font_scale multiplier, thickness multiplier, color) - font_scale/thickness are
# scaled to the target resolution (reference 720p); sizes are 3x the original watermark
OUTRO_LINES = (
    (OUTRO_LINE1, 3.3, 6, (255, 255, 255)),
    (OUTRO_LINE2, 1.5, 3, (220, 220, 220)),
    (OUTRO_LINE3, 1.2, 2, (170, 170, 170)),
)


class TimelapseError(Exception):
    """Rendering failed. The message is meant to be shown to the user as-is."""


class TimelapseCancelled(Exception):
    """Rendering was cancelled by the caller before the video was finished."""


def build_outro_frame(width, height):
    """A black frame with the watermark, appended to the end of the video (project promo)."""
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    scale = height / 720
    font = cv2.FONT_HERSHEY_SIMPLEX
    gap = int(round(20 * scale))
    max_text_width = int(width * 0.92)

    rendered = []
    for text, font_scale_mult, thickness_mult, color in OUTRO_LINES:
        font_scale = max(font_scale_mult * scale, font_scale_mult * 0.25)
        thickness = max(int(round(thickness_mult * scale)), 1)
        (text_w, text_h), baseline = cv2.getTextSize(text, font, font_scale, thickness)

        # At low resolutions (e.g. 240p) the longer line might not fit the width -
        # in that case shrink the font further so the text isn't shown cropped
        if text_w > max_text_width:
            shrink = max_text_width / text_w
            font_scale = max(font_scale * shrink, 0.3)
            thickness = max(int(round(thickness * shrink)), 1)
            (text_w, text_h), baseline = cv2.getTextSize(text, font, font_scale, thickness)

        rendered.append((text, font_scale, thickness, color, text_w, text_h + baseline))

    total_height = sum(r[5] for r in rendered) + gap * (len(rendered) - 1)
    y = int(height / 2 - total_height / 2)
    for text, font_scale, thickness, color, text_w, line_height in rendered:
        y += line_height
        x = max((width - text_w) // 2, 0)
        cv2.putText(frame, text, (x, y), font, font_scale, color, thickness, cv2.LINE_AA)
        y += gap
    return frame


def imread_unicode(path):
    """cv2.imread() fails (returns None) on Windows if the path contains accented characters;
    the workaround is np.fromfile + cv2.imdecode, which open the path in a unicode-safe way."""
    try:
        data = np.fromfile(path, dtype=np.uint8)
    except OSError:
        return None
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def letterbox_resize(img, target_width, target_height):
    """Scales a photo down while preserving its aspect ratio so it fits entirely within the
    target resolution, and pads the rest of the canvas with black bars (letterbox/pillarbox).

    The target resolution is computed from the aspect ratio of the first photo in the
    folder - without this, other photos with a different aspect ratio (e.g. a folder mixing
    portrait/landscape shots) would be stretched/distorted by a direct cv2.resize() to those
    dimensions instead of being framed.
    """
    src_height, src_width = img.shape[:2]
    new_width, new_height, x_offset, y_offset = compute_letterbox_layout(
        src_width, src_height, target_width, target_height
    )
    resized = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((target_height, target_width, 3), dtype=np.uint8)
    canvas[y_offset:y_offset + new_height, x_offset:x_offset + new_width] = resized
    return canvas


class FfmpegVideoWriter:
    """
    Writes the video via the system's FFmpeg using the H.264 codec.
    OpenCV's pip package can't encode H.264 (only MPEG-4 "mp4v"), whose output mobile apps
    and e.g. Instagram won't play/accept - so instead of cv2.VideoWriter, the actual video
    encoding uses FFmpeg, which frames are streamed to over a pipe.
    """

    def __init__(self, output_file, fps, size):
        width, height = size
        ffmpeg_exe = shutil.which("ffmpeg")
        if ffmpeg_exe is None:
            raise FileNotFoundError(
                "FFmpeg was not found in PATH. Install it (e.g. 'sudo apt install ffmpeg' "
                "on Debian/Ubuntu, 'sudo dnf install ffmpeg' on Fedora, or 'brew install ffmpeg' "
                "on macOS) and try again."
            )
        cmd = [
            ffmpeg_exe, "-y",
            "-loglevel", "error",
            "-f", "rawvideo", "-vcodec", "rawvideo",
            "-pix_fmt", "bgr24",
            "-s", f"{width}x{height}",
            "-r", str(fps),
            "-i", "-",
            "-an",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            output_file,
        ]
        self._process = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )
        # FFmpeg's stderr must be drained continuously in the background: if it fills the
        # OS pipe buffer (e.g. many warnings) while we're only reading it after all frames
        # are written, FFmpeg blocks on its stderr write and we block on stdin.write() -
        # a deadlock where each side waits on the other forever.
        self._stderr_chunks = []
        self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        self._stderr_thread.start()

    def _drain_stderr(self):
        try:
            for chunk in iter(lambda: self._process.stderr.read(4096), b""):
                self._stderr_chunks.append(chunk)
        except (ValueError, OSError):
            pass

    def write(self, frame):
        self._process.stdin.write(frame.tobytes())

    def release(self):
        try:
            self._process.stdin.close()
        except OSError:
            pass
        self._process.wait()
        self._stderr_thread.join()
        self.error_output = b"".join(self._stderr_chunks).decode("utf-8", errors="replace")

    def terminate(self):
        self._process.terminate()
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait()
        self._stderr_thread.join(timeout=5)

    @property
    def returncode(self):
        return self._process.returncode


def render_timelapse(input_folder, output_file, fps, resolution_choice, *,
                     add_watermark=True, sort_mode="name", on_progress=None, is_cancelled=None):
    """Renders the photos in `input_folder` into the video `output_file`.

    - `resolution_choice`: a resolution label, e.g. "Full HD (Smooth playback)" (see
      `compute_target_resolution`).
    - `sort_mode`: frame order, one of the modes in `timelapse_core.SORT_MODES`.
    - `on_progress(percent, text)`: optional, called after each processed frame.
    - `is_cancelled()`: optional, polled before each frame; returning True aborts rendering.

    The video is written beside `output_file` and only moved into place once it is complete,
    so a failed or cancelled render never truncates an existing video.

    Raises TimelapseError (message is user-facing), TimelapseCancelled, or OSError/ImportError
    for unexpected failures.
    """
    def report(percent, text):
        if on_progress is not None:
            on_progress(percent, text)

    images = sort_image_paths(find_images(input_folder), sort_mode)
    if not images:
        raise TimelapseError("Error: No images were found in the selected folder.")

    # Determine video dimensions from the first image
    first_frame = imread_unicode(images[0])
    if first_frame is None:
        raise TimelapseError("Error: The first image is corrupted and could not be loaded.")

    # shape[:2] works for both color and grayscale images
    height, width = first_frame.shape[:2]

    # Compute the new resolution (preserving aspect ratio, even numbers for codecs)
    target_width, target_height = compute_target_resolution(width, height, resolution_choice)

    output_dir = os.path.dirname(os.path.abspath(output_file))
    fd, tmp_output_file = tempfile.mkstemp(
        prefix=".timelapse-", suffix=os.path.splitext(output_file)[1] or ".mp4",
        dir=output_dir,
    )
    os.close(fd)

    try:
        try:
            video = FfmpegVideoWriter(tmp_output_file, fps, (target_width, target_height))
        except OSError as e:
            raise TimelapseError(f"Error: Failed to start FFmpeg to create the video.\n{e}") from e

        was_cancelled = False
        write_failed = False
        try:
            total_images = len(images)
            for i, image_path in enumerate(images):
                if is_cancelled is not None and is_cancelled():
                    was_cancelled = True
                    break

                img = imread_unicode(image_path)
                if img is None:
                    continue

                # Scale down while preserving aspect ratio and framing (INTER_AREA is
                # best for downscaling quality)
                if img.shape[:2] != (target_height, target_width):
                    img = letterbox_resize(img, target_width, target_height)

                try:
                    video.write(img)
                except (BrokenPipeError, OSError):
                    write_failed = True
                    break

                progress_percent = int(((i + 1) / total_images) * 100)
                report(progress_percent, f"Processed: {i + 1} / {total_images}")

            # Watermark at the end of the video (project promo) - only if processing
            # completed successfully, not on cancellation or a write failure
            if not was_cancelled and not write_failed and add_watermark:
                report(100, "Adding closing watermark...")
                outro_frame = build_outro_frame(target_width, target_height)
                outro_frame_count = max(round(fps * OUTRO_DURATION_SECONDS), 1)
                for _ in range(outro_frame_count):
                    try:
                        video.write(outro_frame)
                    except (BrokenPipeError, OSError):
                        write_failed = True
                        break
        except BaseException:
            # Unexpected error or Ctrl+C: stop FFmpeg right away instead of waiting for it
            video.terminate()
            raise

        if was_cancelled:
            video.terminate()
            raise TimelapseCancelled("Processing was cancelled.")

        video.release()
        if write_failed or video.returncode != 0:
            raise TimelapseError(f"Error: FFmpeg failed while creating the video.\n{video.error_output}")

        # Publish only a complete video, preserving any previous output on failure.
        os.replace(tmp_output_file, output_file)
        tmp_output_file = None
    finally:
        if tmp_output_file and os.path.exists(tmp_output_file):
            try:
                os.remove(tmp_output_file)
            except OSError:
                pass
