import sys
import re
import json
import urllib.request
import urllib.error
import webbrowser
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QComboBox,
                             QSpinBox, QProgressBar, QFileDialog, QMessageBox,
                             QCheckBox)
from PyQt5.QtCore import QThread, pyqtSignal, Qt

from timelapse_core import SORT_NAME, SORT_EXIF, SORT_MTIME
from timelapse_render import TimelapseCancelled, TimelapseError, render_timelapse

APP_VERSION = "1.13.0"
GITHUB_REPO = "jan-tdy/jadiv-timelapse"
GITHUB_LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

# --nomark sets the default state of the watermark toggle in the UI to off (it can still
# be switched back on in the window - --nomark only changes the default value at startup)
SKIP_WATERMARK = "--nomark" in sys.argv


def _version_tuple(version):
    """Converts e.g. 'v1.10' into (1, 10) so versions can be compared numerically, not as text."""
    parts = re.findall(r'\d+', version)
    return tuple(int(p) for p in parts) if parts else (0,)


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
    The rendering itself lives in timelapse_render.render_timelapse().
    """
    progress_update = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str)
    cancelled = pyqtSignal(str)

    def __init__(self, input_folder, output_file, fps, resolution_choice, add_watermark=True, sort_mode=SORT_NAME):
        super().__init__()
        self.input_folder = input_folder
        self.output_file = output_file
        self.fps = fps
        self.resolution_choice = resolution_choice
        self.add_watermark = add_watermark
        self.sort_mode = sort_mode
        self._cancel_requested = False

    def cancel(self):
        self._cancel_requested = True

    def run(self):
        try:
            render_timelapse(
                self.input_folder, self.output_file, self.fps, self.resolution_choice,
                add_watermark=self.add_watermark,
                sort_mode=self.sort_mode,
                on_progress=self.progress_update.emit,
                is_cancelled=lambda: self._cancel_requested,
            )
        except TimelapseCancelled as e:
            self.cancelled.emit(str(e))
            return
        except TimelapseError as e:
            self.finished.emit(False, str(e))
            return
        except Exception as e:
            self.finished.emit(False, f"An error occurred during generation:\n{str(e)}")
            return
        self.finished.emit(True, "The video was created and saved successfully!")


class TimelapseApp(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.check_for_updates()

    def initUI(self):
        self.setWindowTitle("Jadiv-Timelapse Plus")
        self.resize(650, 440)

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

        # Frame order: file name (default), EXIF capture time, or file modification time
        sort_layout = QHBoxLayout()
        sort_label = QLabel("Sort photos by:")
        sort_label.setFixedWidth(140)
        self.sort_combo = QComboBox()
        self.sort_combo.addItem("File name (default)", SORT_NAME)
        self.sort_combo.addItem("EXIF capture date (DateTimeOriginal)", SORT_EXIF)
        self.sort_combo.addItem("File modification date", SORT_MTIME)
        sort_layout.addWidget(sort_label)
        sort_layout.addWidget(self.sort_combo, 1)
        main_layout.addLayout(sort_layout)

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
        self.sort_combo.setEnabled(False)
        self.watermark_checkbox.setEnabled(False)

        self.progress_bar.setValue(0)
        self.status_label.setText("Processing... Please wait.")
        self.status_label.setStyleSheet("color: #0d6efd;")

        # Start the thread
        fps = self.fps_spinbox.value()
        resolution = self.resolution_combo.currentText()
        add_watermark = self.watermark_checkbox.isChecked()
        sort_mode = self.sort_combo.currentData()

        self.worker = VideoWorker(in_folder, out_file, fps, resolution, add_watermark, sort_mode)
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
        self.sort_combo.setEnabled(True)
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
