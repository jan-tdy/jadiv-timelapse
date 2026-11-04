import os
import shutil

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")
pytest.importorskip("PIL.Image")

from timelapse_core import SORT_MTIME, SORT_NAME  # noqa: E402
from timelapse_render import TimelapseError, render_timelapse  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _solid(path, bgr):
    cv2.imwrite(str(path), np.full((64, 96, 3), bgr, dtype=np.uint8))


def _first_frame_mean(video_path):
    cap = cv2.VideoCapture(str(video_path))
    ok, frame = cap.read()
    cap.release()
    assert ok
    return frame.reshape(-1, 3).mean(axis=0)


def test_render_orders_frames_by_mtime(tmp_path):
    photos = tmp_path / "photos"
    photos.mkdir()
    # Name order would start with the blue frame; modification time starts with the green one.
    _solid(photos / "a_blue.png", (255, 0, 0))
    _solid(photos / "b_green.png", (0, 255, 0))
    os.utime(photos / "a_blue.png", (2_000_000_000, 2_000_000_000))
    os.utime(photos / "b_green.png", (1_000_000_000, 1_000_000_000))

    out_by_name = tmp_path / "by_name.mp4"
    out_by_mtime = tmp_path / "by_mtime.mp4"
    render_timelapse(str(photos), str(out_by_name), 5, "original", add_watermark=False, sort_mode=SORT_NAME)
    render_timelapse(str(photos), str(out_by_mtime), 5, "original", add_watermark=False, sort_mode=SORT_MTIME)

    assert _first_frame_mean(out_by_name)[0] > 150   # blue (BGR) first
    assert _first_frame_mean(out_by_mtime)[1] > 150  # green first


def test_render_without_images_reports_user_message(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(TimelapseError, match="No images were found"):
        render_timelapse(str(empty), str(tmp_path / "out.mp4"), 5, "original")
    assert not (tmp_path / "out.mp4").exists()
