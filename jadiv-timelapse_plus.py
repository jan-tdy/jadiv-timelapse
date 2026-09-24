import sys
import os
import glob
import re
import json
import shutil
import subprocess
import urllib.request
import urllib.error
import webbrowser
import cv2
import numpy as np
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QComboBox,
                             QSpinBox, QProgressBar, QFileDialog, QMessageBox,
                             QCheckBox)
from PyQt5.QtCore import QThread, pyqtSignal, Qt

from timelapse_core import natural_sort_key, compute_target_resolution, compute_letterbox_layout

APP_VERSION = "1.11.0"
GITHUB_REPO = "jan-tdy/jadiv-timelapse"
GITHUB_LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

# --nomark sets the default state of the watermark toggle in the UI to off (it can still
# be switched back on in the window - --nomark only changes the default value at startup)
SKIP_WATERMARK = "--nomark" in sys.argv

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


def _version_tuple(version):
    """Converts e.g. 'v1.10' into (1, 10) so versions can be compared numerically, not as text."""
    parts = re.findall(r'\d+', version)
    return tuple(int(p) for p in parts) if parts else (0,)


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

    def write(self, frame):
        self._process.stdin.write(frame.tobytes())

    def release(self):
        try:
            self._process.stdin.close()
        except OSError:
            pass
        self.error_output = self._process.stderr.read().decode("utf-8", errors="replace")
        self._process.wait()

    def terminate(self):
        self._process.terminate()
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()

    @property
    def returncode(self):
        return self._process.returncode


class UpdateChecker(QThread):
    """Checks GitHub for the latest release in the background (so the UI doesn't freeze) and compares it to the current version."""
    update_available = pyqtSignal(str, str)

    def run(self):
        try:
            request = urllib.request.Request(
                GITHUB_LATEST_RELEASE_API,
                headers={"Accept": "application/vnd.github+json"}
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))

            latest_tag = data.get("tag_name", "")
            release_url = data.get("html_url", f"https://github.com/{GITHUB_REPO}/releases/latest")

            if latest_tag and _version_tuple(latest_tag) > _version_tuple(APP_VERSION):
                self.update_available.emit(latest_tag, release_url)
        except (urllib.error.URLError, ValueError, OSError):
            # No internet, GitHub unreachable, or API rate limit - the check is simply skipped
            pass


class VideoWorker(QThread):
    """
    Worker thread for video processing, so the main window (GUI) doesn't freeze.
    """
    progress_update = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str)
    cancelled = pyqtSignal(str)

    def __init__(self, input_folder, output_file, fps, resolution_choice, add_watermark=True):
        super().__init__()
        self.input_folder = input_folder
        self.output_file = output_file
        self.fps = fps
        self.resolution_choice = resolution_choice
        self.add_watermark = add_watermark
        self._cancel_requested = False

    def cancel(self):
        self._cancel_requested = True

    def run(self):
        try:
            # Also look for large JPGs from Nikon cameras
            extensions = ('/*.jpg', '/*.jpeg', '/*.png', '/*.JPG', '/*.JPEG', '/*.PNG')
            images = set()
            for ext in extensions:
                images.update(glob.glob(glob.escape(self.input_folder) + ext))

            # Sort by the numbers in the file name (e.g. 2 before 10), not purely alphabetically;
            # the set() above also removes duplicates (on Windows/macOS "*.jpg" and "*.JPG" would
            # otherwise match the same files twice)
            images = sorted(images, key=natural_sort_key)

            if not images:
                self.finished.emit(False, "Error: No images were found in the selected folder.")
                return

            # Determine video dimensions from the first image
            first_frame = imread_unicode(images[0])
            if first_frame is None:
                self.finished.emit(False, "Error: The first image is corrupted and could not be loaded.")
                return

            # shape[:2] works for both color and grayscale images
            height, width = first_frame.shape[:2]

            # Compute the new resolution (preserving aspect ratio, even numbers for codecs)
            target_width, target_height = compute_target_resolution(width, height, self.resolution_choice)

            # Initialize the video writer (FFmpeg / H.264)
            try:
                video = FfmpegVideoWriter(self.output_file, self.fps, (target_width, target_height))
            except OSError as e:
                self.finished.emit(False, f"Error: Failed to start FFmpeg to create the video.\n{e}")
                return

            was_cancelled = False
            write_failed = False
            try:
                total_images = len(images)
                for i, image_path in enumerate(images):
                    if self._cancel_requested:
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

                    # Update the progress bar and status text
                    progress_percent = int(((i + 1) / total_images) * 100)
                    status_text = f"Processed: {i + 1} / {total_images}"
                    self.progress_update.emit(progress_percent, status_text)

                # Watermark at the end of the video (project promo) - only if processing
                # completed successfully, not on cancellation or a write failure
                if not was_cancelled and not write_failed and self.add_watermark:
                    self.progress_update.emit(100, "Adding closing watermark...")
                    outro_frame = build_outro_frame(target_width, target_height)
                    outro_frame_count = max(round(self.fps * OUTRO_DURATION_SECONDS), 1)
                    for _ in range(outro_frame_count):
                        try:
                            video.write(outro_frame)
                        except (BrokenPipeError, OSError):
                            write_failed = True
                            break
            finally:
                if was_cancelled:
                    video.terminate()
                else:
                    video.release()

            if was_cancelled:
                if os.path.exists(self.output_file):
                    try:
                        os.remove(self.output_file)
                    except OSError:
                        pass
                self.cancelled.emit("Processing was cancelled.")
                return

            if write_failed or video.returncode != 0:
                self.finished.emit(False, f"Error: FFmpeg failed while creating the video.\n{video.error_output}")
                return

            # Successful completion
            self.finished.emit(True, "The video was created and saved successfully!")

        except Exception as e:
            self.finished.emit(False, f"An error occurred during generation:\n{str(e)}")


class TimelapseApp(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.check_for_updates()

    def initUI(self):
        self.setWindowTitle("Jadiv-Timelapse Plus version(by JapySoft TDY)")
        self.resize(650, 400)

        # Apply a modern dark mode CSS style
        self.setStyleSheet("""
            QWidget {
                background-color: #2b2b2b;
                color: #e0e0e0;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 11pt;
            }
            QLabel {
                color: #e0e0e0;
            }
            QLabel#title {
                font-size: 18pt;
                font-weight: bold;
                color: #ffffff;
                margin-bottom: 10px;
            }
            QLabel#status {
                color: #888888;
                font-style: italic;
            }
            QLineEdit, QComboBox, QSpinBox {
                background-color: #3c3f41;
                border: 1px solid #555555;
                padding: 6px;
                border-radius: 4px;
                color: #ffffff;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
                border: 1px solid #0d6efd;
            }
            QPushButton {
                background-color: #444444;
                color: white;
                border: 1px solid #555;
                padding: 6px 15px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #555555;
            }
            QPushButton#actionBtn {
                background-color: #0d6efd;
                font-weight: bold;
                font-size: 12pt;
                padding: 10px 20px;
                border: none;
            }
            QPushButton#actionBtn:hover {
                background-color: #0b5ed7;
            }
            QPushButton#actionBtn:disabled {
                background-color: #3b3b3b;
                color: #777777;
            }
            QProgressBar {
                border: 1px solid #555555;
                border-radius: 4px;
                text-align: center;
                background-color: #3c3f41;
                color: white;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #198754;
                width: 10px;
            }
        """)

        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(25, 25, 25, 25)
        main_layout.setSpacing(15)

        # Title
        title_label = QLabel("🎬 Jadiv-Timelapse")
        title_label.setObjectName("title")
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)

        # 1. Photo folder
        folder_layout = QHBoxLayout()
        folder_label = QLabel("Photo folder:")
        folder_label.setFixedWidth(140)
        self.input_folder_entry = QLineEdit()
        self.input_folder_entry.setPlaceholderText("e.g. /home/dpv/Pictures/timelapse")
        folder_btn = QPushButton("Browse...")
        folder_btn.clicked.connect(self.browse_input)
        folder_layout.addWidget(folder_label)
        folder_layout.addWidget(self.input_folder_entry)
        folder_layout.addWidget(folder_btn)
        main_layout.addLayout(folder_layout)

        # 2. Output file
        file_layout = QHBoxLayout()
        file_label = QLabel("Save video as:")
        file_label.setFixedWidth(140)
        self.output_file_entry = QLineEdit()
        self.output_file_entry.setPlaceholderText("e.g. /home/dpv/Videos/output.mp4")
        file_btn = QPushButton("Save as...")
        file_btn.clicked.connect(self.browse_output)
        file_layout.addWidget(file_label)
        file_layout.addWidget(self.output_file_entry)
        file_layout.addWidget(file_btn)
        main_layout.addLayout(file_layout)

        # 3. FPS and resolution
        settings_layout = QHBoxLayout()

        fps_label = QLabel("Speed (FPS):")
        self.fps_spinbox = QSpinBox()
        self.fps_spinbox.setRange(1, 120)
        self.fps_spinbox.setValue(24)
        self.fps_spinbox.setFixedWidth(60)

        res_label = QLabel("Resolution:")
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems([
            "4K (High quality)",
            "Full HD (Smooth playback)",
            "HD (720p)",
            "SD (480p - small)",
            "Low quality (240p - very small)",
            "Original (May lag pc)"
        ])
        self.resolution_combo.setCurrentIndex(1) # Default: Full HD

        settings_layout.addWidget(fps_label)
        settings_layout.addWidget(self.fps_spinbox)
        settings_layout.addSpacing(20)
        settings_layout.addWidget(res_label)
        settings_layout.addWidget(self.resolution_combo, 1) # stretches to fill
        main_layout.addLayout(settings_layout)

        # Closing watermark toggle (default follows the --nomark startup flag)
        self.watermark_checkbox = QCheckBox("Add closing watermark (4s, Jadiv-Timelapse promo)")
        self.watermark_checkbox.setChecked(not SKIP_WATERMARK)
        main_layout.addWidget(self.watermark_checkbox)

        # Spacer
        main_layout.addSpacing(10)

        # 4. Progress bar and status
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(25)
        main_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Ready.")
        self.status_label.setObjectName("status")
        self.status_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.status_label)

        # Spacer
        main_layout.addSpacing(10)

        # 5. START and Cancel buttons
        btn_layout = QHBoxLayout()

        self.start_btn = QPushButton("CREATE TIMELAPSE")
        self.start_btn.setObjectName("actionBtn")
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.clicked.connect(self.start_processing)
        btn_layout.addWidget(self.start_btn, 1)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_processing)
        btn_layout.addWidget(self.cancel_btn)

        main_layout.addLayout(btn_layout)

        # App version in the bottom-right corner
        version_label = QLabel(f"v{APP_VERSION}")
        version_label.setStyleSheet("color: #666666; font-size: 8pt;")
        version_label.setAlignment(Qt.AlignRight)
        main_layout.addWidget(version_label)

        self.setLayout(main_layout)

    def check_for_updates(self):
        # The check runs in the background so it doesn't block the window from opening
        self.update_checker = UpdateChecker()
        self.update_checker.update_available.connect(self.show_update_dialog)
        self.update_checker.start()

    def show_update_dialog(self, latest_version, release_url):
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("New version available")
        msg_box.setIcon(QMessageBox.Information)
        msg_box.setText(
            f"Version {latest_version} is available (current version: v{APP_VERSION})."
        )
        msg_box.setInformativeText("Do you want to open the download page?")
        open_btn = msg_box.addButton("Open page", QMessageBox.AcceptRole)
        msg_box.addButton("Later", QMessageBox.RejectRole)
        msg_box.exec_()
        if msg_box.clickedButton() == open_btn:
            webbrowser.open(release_url)

    def browse_input(self):
        folder = QFileDialog.getExistingDirectory(self, "Select the folder with the images")
        if folder:
            self.input_folder_entry.setText(folder)

    def browse_output(self):
        file, _ = QFileDialog.getSaveFileName(self, "Save video", "", "MP4 Video (*.mp4)")
        if file:
            # Force-append .mp4 if the user didn't type it
            if not file.lower().endswith('.mp4'):
                file += '.mp4'
            self.output_file_entry.setText(file)

    def start_processing(self):
        in_folder = self.input_folder_entry.text().strip()
        out_file = self.output_file_entry.text().strip()

        if not in_folder or not out_file:
            QMessageBox.warning(self, "Notice", "Please select both an input folder and an output file.")
            return

        # Lock the UI
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.input_folder_entry.setEnabled(False)
        self.output_file_entry.setEnabled(False)
        self.fps_spinbox.setEnabled(False)
        self.resolution_combo.setEnabled(False)
        self.watermark_checkbox.setEnabled(False)

        self.progress_bar.setValue(0)
        self.status_label.setText("Processing... Please wait.")
        self.status_label.setStyleSheet("color: #0d6efd;")

        # Start the thread
        fps = self.fps_spinbox.value()
        resolution = self.resolution_combo.currentText()
        add_watermark = self.watermark_checkbox.isChecked()

        self.worker = VideoWorker(in_folder, out_file, fps, resolution, add_watermark)
        self.worker.progress_update.connect(self.update_progress)
        self.worker.finished.connect(self.processing_finished)
        self.worker.cancelled.connect(self.processing_cancelled)
        self.worker.start()

    def cancel_processing(self):
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.cancel()
            self.cancel_btn.setEnabled(False)
            self.status_label.setText("Cancelling...")
            self.status_label.setStyleSheet("color: #888888;")

    def update_progress(self, percent, text):
        self.progress_bar.setValue(percent)
        self.status_label.setText(text)

    def _unlock_ui(self):
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.input_folder_entry.setEnabled(True)
        self.output_file_entry.setEnabled(True)
        self.fps_spinbox.setEnabled(True)
        self.resolution_combo.setEnabled(True)
        self.watermark_checkbox.setEnabled(True)

    def processing_finished(self, success, message):
        self._unlock_ui()

        if success:
            self.status_label.setText("Done!")
            self.status_label.setStyleSheet("color: #198754;")
            self.progress_bar.setValue(100)
            QMessageBox.information(self, "Success", message)
        else:
            self.status_label.setText("An error occurred.")
            self.status_label.setStyleSheet("color: #dc3545;")
            self.progress_bar.setValue(0)
            QMessageBox.critical(self, "Error", message)

    def processing_cancelled(self, message):
        self._unlock_ui()
        self.status_label.setText(message)
        self.status_label.setStyleSheet("color: #888888;")
        self.progress_bar.setValue(0)

    def keyPressEvent(self, event):
        # Pressing Enter (Return) starts the timelapse
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            if self.start_btn.isEnabled():
                self.start_processing()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        # Prevent the window from closing while processing is running in the background -
        # otherwise the thread would be hard-killed mid-write (corrupted file / Qt crash).
        if hasattr(self, 'worker') and self.worker.isRunning():
            QMessageBox.warning(
                self, "Processing is running",
                "The video is still being created. First cancel processing with the "
                "\"Cancel\" button, then you can close the window."
            )
            event.ignore()
        else:
            event.accept()


if __name__ == "__main__":
    # --nomark is our own app flag, not a Qt argument - PyQt would otherwise
    # report it as an unknown option
    qt_argv = [arg for arg in sys.argv if arg != "--nomark"]
    app = QApplication(qt_argv)

    # To ensure a nice look on different systems
    app.setStyle("Fusion")

    window = TimelapseApp()
    window.show()
    sys.exit(app.exec_())
