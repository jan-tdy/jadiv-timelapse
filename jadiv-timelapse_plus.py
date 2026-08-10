import sys
import os
import glob
import cv2
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QLineEdit, QPushButton, QComboBox, 
                             QSpinBox, QProgressBar, QFileDialog, QMessageBox)
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QFont, QIcon

class VideoWorker(QThread):
    """
    Pracovné vlákno pre spracovanie videa, aby nezamrzlo hlavné okno (GUI).
    """
    progress_update = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str)
    cancelled = pyqtSignal(str)

    def __init__(self, input_folder, output_file, fps, resolution_choice):
        super().__init__()
        self.input_folder = input_folder
        self.output_file = output_file
        self.fps = fps
        self.resolution_choice = resolution_choice
        self._cancel_requested = False

    def cancel(self):
        self._cancel_requested = True

    def run(self):
        try:
            # Hľadáme aj veľké JPG z Nikonu
            extensions = ('/*.jpg', '/*.jpeg', '/*.png', '/*.JPG', '/*.JPEG', '/*.PNG')
            images = []
            for ext in extensions:
                images.extend(glob.glob(glob.escape(self.input_folder) + ext))
            
            # Zoradenie podľa abecedy/čísel
            images = sorted(images)

            if not images:
                self.finished.emit(False, "Chyba: Nenašli sa žiadne obrázky v danom priečinku.")
                return

            # Zistenie rozmerov videa podľa prvého obrázka
            first_frame = cv2.imread(images[0])
            if first_frame is None:
                self.finished.emit(False, "Chyba: Prvý obrázok je poškodený a nedá sa načítať.")
                return

            # shape[:2] funguje pre farebné aj čiernobiele obrázky
            height, width = first_frame.shape[:2]

            # Výpočet nového rozlíšenia
            target_width = width
            target_height = height
            
            if "Full HD" in self.resolution_choice:
                target_width = 1920
                target_height = int((1920 / width) * height)
            elif "4K" in self.resolution_choice:
                target_width = 3840
                target_height = int((3840 / width) * height)
            elif "720p" in self.resolution_choice:
                target_height = 720
                target_width = int((720 / height) * width)
            elif "480p" in self.resolution_choice:
                target_height = 480
                target_width = int((480 / height) * width)
            elif "240p" in self.resolution_choice:
                target_height = 240
                target_width = int((240 / height) * width)
                
            # Kodeky MP4 vyžadujú párne čísla
            target_width = target_width - (target_width % 2)
            target_height = target_height - (target_height % 2)

            # Inicializácia VideoWriter
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            video = cv2.VideoWriter(self.output_file, fourcc, self.fps, (target_width, target_height))

            if not video.isOpened():
                self.finished.emit(False, "Chyba: Video sa nepodarilo vytvoriť. Skontroluj, či cieľový priečinok "
                                           "existuje a či máš práva na zápis.")
                return

            was_cancelled = False
            try:
                total_images = len(images)
                for i, image_path in enumerate(images):
                    if self._cancel_requested:
                        was_cancelled = True
                        break

                    img = cv2.imread(image_path)
                    if img is None:
                        continue

                    # Zmenšenie (INTER_AREA je najlepšie pre zmenšovanie kvality)
                    if img.shape[:2] != (target_height, target_width):
                        img = cv2.resize(img, (target_width, target_height), interpolation=cv2.INTER_AREA)

                    video.write(img)

                    # Aktualizácia progress baru a textu
                    progress_percent = int(((i + 1) / total_images) * 100)
                    status_text = f"Spracované: {i + 1} / {total_images}"
                    self.progress_update.emit(progress_percent, status_text)
            finally:
                video.release()

            if was_cancelled:
                if os.path.exists(self.output_file):
                    try:
                        os.remove(self.output_file)
                    except OSError:
                        pass
                self.cancelled.emit("Spracovanie bolo zrušené.")
                return

            # Úspešné dokončenie
            self.finished.emit(True, "Video bolo úspešne vytvorené a uložené!")

        except Exception as e:
            self.finished.emit(False, f"Nastala chyba pri generovaní:\n{str(e)}")


class TimelapseApp(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        
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

        self.setLayout(main_layout)

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

        self.progress_bar.setValue(0)
        self.status_label.setText("Spracovávam... Prosím čakajte.")
        self.status_label.setStyleSheet("color: #0d6efd;")

        # Spustenie vlákna
        fps = self.fps_spinbox.value()
        resolution = self.resolution_combo.currentText()

        self.worker = VideoWorker(in_folder, out_file, fps, resolution)
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


if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Pre zaistenie pekného vzhľadu na rôznych systémoch
    app.setStyle("Fusion")
    
    window = TimelapseApp()
    window.show()
    sys.exit(app.exec_())
