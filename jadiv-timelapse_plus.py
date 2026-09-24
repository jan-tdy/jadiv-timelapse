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

# --nomark nastaví predvolený stav prepínača watermarku v UI na vypnutý (dá sa zapnúť späť
# priamo v okne, --nomark len mení predvolenú hodnotu pri spustení)
SKIP_WATERMARK = "--nomark" in sys.argv

OUTRO_DURATION_SECONDS = 4
OUTRO_LINE1 = "Made by Jadiv-Timelapse"
OUTRO_LINE2 = "Simple timelapse creation - no command-line needed"
OUTRO_LINE3 = f"If you like this, star us on GitHub: github.com/{GITHUB_REPO}"

# (text, font_scale multiplier, thickness multiplier, color) - font_scale/thickness sa škálujú
# podľa cieľového rozlíšenia (referencia 720p); veľkosti sú 3x pôvodného watermarku
OUTRO_LINES = (
    (OUTRO_LINE1, 3.3, 6, (255, 255, 255)),
    (OUTRO_LINE2, 1.5, 3, (220, 220, 220)),
    (OUTRO_LINE3, 1.2, 2, (170, 170, 170)),
)


def build_outro_frame(width, height):
    """Čierna snímka s watermarkom, ktorá sa pripojí na koniec videa (propagácia projektu)."""
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

        # Pri nízkych rozlíšeniach (napr. 240p) sa dlhší riadok nemusí zmestiť na šírku -
        # v takom prípade písmo dodatočne zmenšíme, aby sa text nezobrazoval orezaný
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
    """cv2.imread() zlyháva (vráti None) na Windows, ak cesta obsahuje diakritiku;
    workaround cez np.fromfile + cv2.imdecode, ktoré cestu otvárajú unicode-bezpečne."""
    try:
        data = np.fromfile(path, dtype=np.uint8)
    except OSError:
        return None
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def letterbox_resize(img, target_width, target_height):
    """Zmenší fotku so zachovaním pomeru strán tak, aby sa celá zmestila do cieľového
    rozlíšenia, a doplní čierne pruhy (letterbox/pillarbox) na zvyšok plátna.

    Cieľové rozlíšenie sa počíta z pomeru strán prvej fotky v priečinku - bez tohto by sa
    ďalšie fotky s iným pomerom strán (napr. namixované portrét/landscape) pri priamom
    cv2.resize() na tieto rozmery natiahli/skreslili namiesto toho, aby boli orámované.
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
    """Prevedie napr. 'v1.10' na (1, 10), aby sa dali verzie porovnávať číselne, nie ako text."""
    parts = re.findall(r'\d+', version)
    return tuple(int(p) for p in parts) if parts else (0,)


class FfmpegVideoWriter:
    """
    Zapisuje video cez systémový FFmpeg s kodekom H.264.
    OpenCV vo svojom pip balíčku H.264 kódovať nevie (iba MPEG-4 "mp4v"), ktorého výstup
    neprehrajú/neprijmú mobilné aplikácie ani napr. Instagram - preto sa na samotné kódovanie
    videa namiesto cv2.VideoWriter používa FFmpeg, ktorému sa snímky posielajú cez rúru (pipe).
    """

    def __init__(self, output_file, fps, size):
        width, height = size
        ffmpeg_exe = shutil.which("ffmpeg")
        if ffmpeg_exe is None:
            raise FileNotFoundError(
                "FFmpeg sa nenašiel v PATH. Nainštalujte ho (napr. 'sudo apt install ffmpeg' "
                "na Debian/Ubuntu, 'sudo dnf install ffmpeg' na Fedora, alebo 'brew install ffmpeg' "
                "na macOS) a skúste to znova."
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
    """Na pozadí (aby nezamrzlo UI) skontroluje na GitHube najnovšie vydanie a porovná ho s aktuálnou verziou."""
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
            # Bez internetu, GitHub nedostupný alebo limit API - kontrola sa jednoducho preskočí
            pass


class VideoWorker(QThread):
    """
    Pracovné vlákno pre spracovanie videa, aby nezamrzlo hlavné okno (GUI).
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
            # Hľadáme aj veľké JPG z Nikonu
            extensions = ('/*.jpg', '/*.jpeg', '/*.png', '/*.JPG', '/*.JPEG', '/*.PNG')
            images = set()
            for ext in extensions:
                images.update(glob.glob(glob.escape(self.input_folder) + ext))

            # Zoradenie podľa čísel v názve (napr. 2 pred 10), nie čisto abecedne;
            # set() vyššie zároveň odstráni duplicity (na Windows/macOS by "*.jpg" a "*.JPG" inak našli tie isté súbory dvakrát)
            images = sorted(images, key=natural_sort_key)

            if not images:
                self.finished.emit(False, "Chyba: Nenašli sa žiadne obrázky v danom priečinku.")
                return

            # Zistenie rozmerov videa podľa prvého obrázka
            first_frame = imread_unicode(images[0])
            if first_frame is None:
                self.finished.emit(False, "Chyba: Prvý obrázok je poškodený a nedá sa načítať.")
                return

            # shape[:2] funguje pre farebné aj čiernobiele obrázky
            height, width = first_frame.shape[:2]

            # Výpočet nového rozlíšenia (so zachovaním pomeru strán, párne čísla pre kodeky)
            target_width, target_height = compute_target_resolution(width, height, self.resolution_choice)

            # Inicializácia zapisovača videa (FFmpeg / H.264)
            try:
                video = FfmpegVideoWriter(self.output_file, self.fps, (target_width, target_height))
            except OSError as e:
                self.finished.emit(False, f"Chyba: Nepodarilo sa spustiť FFmpeg pre vytvorenie videa.\n{e}")
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

                    # Zmenšenie so zachovaním pomeru strán a orámovaním (INTER_AREA je
                    # najlepšie pre zmenšovanie kvality)
                    if img.shape[:2] != (target_height, target_width):
                        img = letterbox_resize(img, target_width, target_height)

                    try:
                        video.write(img)
                    except (BrokenPipeError, OSError):
                        write_failed = True
                        break

                    # Aktualizácia progress baru a textu
                    progress_percent = int(((i + 1) / total_images) * 100)
                    status_text = f"Spracované: {i + 1} / {total_images}"
                    self.progress_update.emit(progress_percent, status_text)

                # Watermark na konci videa (propagácia projektu) - iba ak spracovanie
                # prebehlo v poriadku, nie pri zrušení alebo chybe zápisu
                if not was_cancelled and not write_failed and self.add_watermark:
                    self.progress_update.emit(100, "Pridávam záverečný watermark...")
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
                self.cancelled.emit("Spracovanie bolo zrušené.")
                return

            if write_failed or video.returncode != 0:
                self.finished.emit(False, f"Chyba: FFmpeg zlyhal pri vytváraní videa.\n{video.error_output}")
                return

            # Úspešné dokončenie
            self.finished.emit(True, "Video bolo úspešne vytvorené a uložené!")

        except Exception as e:
            self.finished.emit(False, f"Nastala chyba pri generovaní:\n{str(e)}")


class TimelapseApp(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.check_for_updates()

    def initUI(self):
        self.setWindowTitle("Jadiv-Timelapse Plus version(by JapySoft TDY)")
        self.resize(650, 400)
        
        # Aplikovanie moderného Dark Mode CSS štýlu
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

        # Hlavný layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(25, 25, 25, 25)
        main_layout.setSpacing(15)

        # Nadpis
        title_label = QLabel("🎬 Jadiv-Timelapse")
        title_label.setObjectName("title")
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)

        # 1. Priečinok s fotkami
        folder_layout = QHBoxLayout()
        folder_label = QLabel("Priečinok s fotkami:")
        folder_label.setFixedWidth(140)
        self.input_folder_entry = QLineEdit()
        self.input_folder_entry.setPlaceholderText("Napr. /home/dpv/Pictures/timelapse")
        folder_btn = QPushButton("Prehľadávať...")
        folder_btn.clicked.connect(self.browse_input)
        folder_layout.addWidget(folder_label)
        folder_layout.addWidget(self.input_folder_entry)
        folder_layout.addWidget(folder_btn)
        main_layout.addLayout(folder_layout)

        # 2. Výstupný súbor
        file_layout = QHBoxLayout()
        file_label = QLabel("Uložiť video ako:")
        file_label.setFixedWidth(140)
        self.output_file_entry = QLineEdit()
        self.output_file_entry.setPlaceholderText("Napr. /home/dpv/Videos/vystup.mp4")
        file_btn = QPushButton("Uložiť ako...")
        file_btn.clicked.connect(self.browse_output)
        file_layout.addWidget(file_label)
        file_layout.addWidget(self.output_file_entry)
        file_layout.addWidget(file_btn)
        main_layout.addLayout(file_layout)

        # 3. FPS a Rozlíšenie
        settings_layout = QHBoxLayout()
        
        fps_label = QLabel("Rýchlosť (FPS):")
        self.fps_spinbox = QSpinBox()
        self.fps_spinbox.setRange(1, 120)
        self.fps_spinbox.setValue(24)
        self.fps_spinbox.setFixedWidth(60)
        
        res_label = QLabel("Rozlíšenie:")
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems([
            "4K (Vysoká kvalita)",
            "Full HD (Plynulé prehrávanie)", 
            "HD (720p)",
            "SD (480p - malé)",
            "Nízka kvalita (240p - veľmi malé)",
            "Originál (Môže sekať pc)"
        ])
        self.resolution_combo.setCurrentIndex(1) # Default: Full HD

        settings_layout.addWidget(fps_label)
        settings_layout.addWidget(self.fps_spinbox)
        settings_layout.addSpacing(20)
        settings_layout.addWidget(res_label)
        settings_layout.addWidget(self.resolution_combo, 1) # roztiahne sa
        main_layout.addLayout(settings_layout)

        # Prepínač záverečného watermarku (predvolene podľa --nomark parametra pri spustení)
        self.watermark_checkbox = QCheckBox("Pridať záverečný watermark (4s, propagácia Jadiv-Timelapse)")
        self.watermark_checkbox.setChecked(not SKIP_WATERMARK)
        main_layout.addWidget(self.watermark_checkbox)

        # Medzera
        main_layout.addSpacing(10)

        # 4. Progress bar a Status
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(25)
        main_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Pripravený na prácu.")
        self.status_label.setObjectName("status")
        self.status_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.status_label)

        # Medzera
        main_layout.addSpacing(10)

        # 5. Tlačidlá ŠTART a Zrušiť
        btn_layout = QHBoxLayout()

        self.start_btn = QPushButton("VYTVORIŤ TIMELAPSE")
        self.start_btn.setObjectName("actionBtn")
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.clicked.connect(self.start_processing)
        btn_layout.addWidget(self.start_btn, 1)

        self.cancel_btn = QPushButton("Zrušiť")
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_processing)
        btn_layout.addWidget(self.cancel_btn)

        main_layout.addLayout(btn_layout)

        # Verzia aplikácie v pravom dolnom rohu
        version_label = QLabel(f"v{APP_VERSION}")
        version_label.setStyleSheet("color: #666666; font-size: 8pt;")
        version_label.setAlignment(Qt.AlignRight)
        main_layout.addWidget(version_label)

        self.setLayout(main_layout)

    def check_for_updates(self):
        # Kontrola beží na pozadí, aby neblokovala spustenie okna
        self.update_checker = UpdateChecker()
        self.update_checker.update_available.connect(self.show_update_dialog)
        self.update_checker.start()

    def show_update_dialog(self, latest_version, release_url):
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Dostupná nová verzia")
        msg_box.setIcon(QMessageBox.Information)
        msg_box.setText(
            f"Je dostupná nová verzia {latest_version} (aktuálna verzia: v{APP_VERSION})."
        )
        msg_box.setInformativeText("Chceš otvoriť stránku so stiahnutím?")
        open_btn = msg_box.addButton("Otvoriť stránku", QMessageBox.AcceptRole)
        msg_box.addButton("Neskôr", QMessageBox.RejectRole)
        msg_box.exec_()
        if msg_box.clickedButton() == open_btn:
            webbrowser.open(release_url)

    def browse_input(self):
        folder = QFileDialog.getExistingDirectory(self, "Vyber priečinok s obrázkami")
        if folder:
            self.input_folder_entry.setText(folder)

    def browse_output(self):
        file, _ = QFileDialog.getSaveFileName(self, "Uložiť video", "", "MP4 Video (*.mp4)")
        if file:
            # Vynúti pridanie .mp4 ak to používateľ nenapísal
            if not file.lower().endswith('.mp4'):
                file += '.mp4'
            self.output_file_entry.setText(file)

    def start_processing(self):
        in_folder = self.input_folder_entry.text().strip()
        out_file = self.output_file_entry.text().strip()

        if not in_folder or not out_file:
            QMessageBox.warning(self, "Upozornenie", "Prosím, vyber vstupný priečinok aj výstupný súbor.")
            return

        # Zamknutie UI
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.input_folder_entry.setEnabled(False)
        self.output_file_entry.setEnabled(False)
        self.fps_spinbox.setEnabled(False)
        self.resolution_combo.setEnabled(False)
        self.watermark_checkbox.setEnabled(False)

        self.progress_bar.setValue(0)
        self.status_label.setText("Spracovávam... Prosím čakajte.")
        self.status_label.setStyleSheet("color: #0d6efd;")

        # Spustenie vlákna
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
            self.status_label.setText("Rušenie...")
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
            self.status_label.setText("Hotovo!")
            self.status_label.setStyleSheet("color: #198754;")
            self.progress_bar.setValue(100)
            QMessageBox.information(self, "Úspech", message)
        else:
            self.status_label.setText("Vyskytla sa chyba.")
            self.status_label.setStyleSheet("color: #dc3545;")
            self.progress_bar.setValue(0)
            QMessageBox.critical(self, "Chyba", message)

    def processing_cancelled(self, message):
        self._unlock_ui()
        self.status_label.setText(message)
        self.status_label.setStyleSheet("color: #888888;")
        self.progress_bar.setValue(0)

    def keyPressEvent(self, event):
        # Ak stlačí Enter (Return), spustí sa timelapse
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            if self.start_btn.isEnabled():
                self.start_processing()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        # Zabránime zatvoreniu okna, kým beží spracovanie na pozadí — inak by sa
        # vlákno tvrdo ukončilo uprostred zápisu videa (poškodený súbor / pád Qt).
        if hasattr(self, 'worker') and self.worker.isRunning():
            QMessageBox.warning(
                self, "Spracovanie beží",
                "Video sa ešte vytvára. Najprv spracovanie zruš tlačidlom \"Zrušiť\", "
                "potom môžeš okno zavrieť."
            )
            event.ignore()
        else:
            event.accept()


if __name__ == "__main__":
    # --nomark je vlastný prepínač aplikácie, nie Qt argument - PyQt by ho inak
    # nahlásil ako neznámu voľbu
    qt_argv = [arg for arg in sys.argv if arg != "--nomark"]
    app = QApplication(qt_argv)
    
    # Pre zaistenie pekného vzhľadu na rôznych systémoch
    app.setStyle("Fusion")
    
    window = TimelapseApp()
    window.show()
    sys.exit(app.exec_())
