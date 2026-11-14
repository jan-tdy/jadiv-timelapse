import os
import shutil
import stat

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")
pytest.importorskip("PIL.Image")

from timelapse_core import SORT_MTIME, SORT_NAME  # noqa: E402
from timelapse_render import RenderResult, TimelapseError, render_timelapse, skipped_frames_message  # noqa: E402

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


def _frame_count(video_path):
    cap = cv2.VideoCapture(str(video_path))
    count = 0
    while cap.read()[0]:
        count += 1
    cap.release()
    return count


def test_unreadable_photos_are_skipped_reported_and_progress_completes(tmp_path):
    photos = tmp_path / "photos"
    photos.mkdir()
    (photos / "f0.png").write_bytes(b"")                  # zero-byte file, first in frame order
    _solid(photos / "f1.png", (255, 0, 0))
    _solid(photos / "f2.png", (0, 255, 0))
    (photos / "f3.png").write_bytes(b"\x89PNG truncated")  # corrupt data
    out = tmp_path / "out.mp4"

    progress = []
    result = render_timelapse(
        str(photos), str(out), 5, "original", add_watermark=False,
        on_progress=lambda percent, text: progress.append(percent),
    )

    assert isinstance(result, RenderResult)
    assert result.frames_written == 2
    assert [os.path.basename(p) for p in result.skipped_images] == ["f0.png", "f3.png"]
    # Progress is reported for skipped photos too, so the bar still reaches 100 %
    assert progress == [25, 50, 75, 100]
    assert _frame_count(out) == 2
    assert _first_frame_mean(out)[0] > 150  # starts with the first readable photo (blue)
    assert "2 of 4 photos could not be read" in skipped_frames_message(result)


def test_no_readable_photos_fails_and_keeps_existing_output(tmp_path):
    photos = tmp_path / "photos"
    photos.mkdir()
    (photos / "a.jpg").write_bytes(b"not an image")
    (photos / "b.jpg").write_bytes(b"")
    out = tmp_path / "out.mp4"
    out.write_bytes(b"previous video")

    with pytest.raises(TimelapseError, match="None of the 2 photos could be read"):
        render_timelapse(str(photos), str(out), 5, "original", add_watermark=False)

    assert out.read_bytes() == b"previous video"
    assert [p.name for p in tmp_path.iterdir()] == sorted(["photos", "out.mp4"])


class _FailingFfmpegWriter:
    """Stands in for FFmpeg: leaves a partial file behind and then reports a failure."""

    def __init__(self, output_file, fps, size):
        with open(output_file, "wb") as f:
            f.write(b"partial")
        self.returncode = 1
        self.error_output = "No space left on device"

    def write(self, frame):
        pass

    def release(self):
        pass

    def terminate(self):
        pass


def test_ffmpeg_failure_keeps_existing_output_and_removes_partial_file(tmp_path, monkeypatch):
    photos = tmp_path / "photos"
    photos.mkdir()
    _solid(photos / "a.png", (255, 0, 0))
    out = tmp_path / "out.mp4"
    out.write_bytes(b"previous video")
    os.chmod(out, 0o640)
    monkeypatch.setattr("timelapse_render.FfmpegVideoWriter", _FailingFfmpegWriter)

    with pytest.raises(TimelapseError, match="FFmpeg failed"):
        render_timelapse(str(photos), str(out), 5, "original", add_watermark=False)

    assert out.read_bytes() == b"previous video"
    assert stat.S_IMODE(out.stat().st_mode) == 0o640
    assert [p.name for p in tmp_path.iterdir()] == sorted(["photos", "out.mp4"])


class _StubFfmpegWriter:
    """Writes a stand-in file and reports success, so mode checks do not encode video."""

    def __init__(self, output_file, fps, size):
        with open(output_file, "wb") as handle:
            handle.write(b"video-bytes")
        self.returncode = 0
        self.error_output = ""

    def write(self, frame):
        pass

    def release(self):
        pass

    def terminate(self):
        pass


def test_new_output_uses_umask_mode(tmp_path, monkeypatch):
    photos = tmp_path / "photos"
    photos.mkdir()
    _solid(photos / "a.png", (255, 0, 0))
    out = tmp_path / "out.mp4"
    monkeypatch.setattr("timelapse_render.FfmpegVideoWriter", _StubFfmpegWriter)

    # Pin the umask. A process umask of 0077 would make 0600 look correct.
    previous = os.umask(0o022)
    try:
        render_timelapse(str(photos), str(out), 5, "original", add_watermark=False)
    finally:
        os.umask(previous)

    assert stat.S_IMODE(out.stat().st_mode) == 0o644
    assert out.read_bytes() == b"video-bytes"


def test_replaced_output_keeps_existing_mode(tmp_path, monkeypatch):
    photos = tmp_path / "photos"
    photos.mkdir()
    _solid(photos / "a.png", (0, 255, 0))
    out = tmp_path / "out.mp4"
    out.write_bytes(b"previous video")
    os.chmod(out, 0o640)
    monkeypatch.setattr("timelapse_render.FfmpegVideoWriter", _StubFfmpegWriter)

    render_timelapse(str(photos), str(out), 5, "original", add_watermark=False)

    assert stat.S_IMODE(out.stat().st_mode) == 0o640
    assert out.read_bytes() == b"video-bytes"


def test_skipped_frames_message_lists_names_and_counts_the_rest():
    result = RenderResult(frames_written=3, skipped_images=tuple(f"/x/bad{i}.jpg" for i in range(7)))
    message = skipped_frames_message(result)
    assert message.startswith("7 of 10 photos could not be read and were left out of the video: bad0.jpg")
    assert message.endswith("and 2 more.")
    assert skipped_frames_message(RenderResult(frames_written=3, skipped_images=())) == ""
