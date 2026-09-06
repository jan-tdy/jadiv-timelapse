import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import cv2
import numpy as np
import glob
import threading
import os
import tempfile
import shutil

from timelapse_core import natural_sort_key, compute_target_resolution


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


class TimelapseApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Jadiv-Timelapse code by JapySoft TDY")
        self.root.geometry("600x360")
        self.root.resizable(False, False)
        
        # Nastavenie štýlu pre modernejší vzhľad
        style = ttk.Style()
        style.theme_use('clam')
        
        # Premenné pre uloženie ciest a nastavení
        self.input_folder = tk.StringVar()
        self.output_file = tk.StringVar()
        self.fps = tk.IntVar(value=24)
        self.resolution = tk.StringVar(value="Full HD (Plynulé prehrávanie)")

        # Stav spracovania (ochrana proti opätovnému spusteniu a možnosť zrušenia)
        self.is_processing = False
        self.cancel_requested = False

        self.create_widgets()
        
        # Pridanie stlačenia klávesy Enter pre spustenie
        self.root.bind('<Return>', self.start_processing)

    def create_widgets(self):
        # Hlavný kontajner
        frame = ttk.Frame(self.root, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)

        # Nadpis
        title_label = ttk.Label(frame, text="Jadiv-Timelapse", font=("Helvetica", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))

        # 1. Riadok: Vstupný priečinok
        ttk.Label(frame, text="Priečinok s fotkami:").grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Entry(frame, textvariable=self.input_folder, width=40).grid(row=1, column=1, padx=10, pady=5)
        ttk.Button(frame, text="Prehľadávať", command=self.browse_input).grid(row=1, column=2, pady=5)

        # 2. Riadok: Výstupný súbor
        ttk.Label(frame, text="Uložiť video ako:").grid(row=2, column=0, sticky=tk.W, pady=5)
        ttk.Entry(frame, textvariable=self.output_file, width=40).grid(row=2, column=1, padx=10, pady=5)
        ttk.Button(frame, text="Uložiť ako", command=self.browse_output).grid(row=2, column=2, pady=5)

        # 3. Riadok: FPS (Snímky za sekundu)
        ttk.Label(frame, text="Rýchlosť (FPS):").grid(row=3, column=0, sticky=tk.W, pady=5)
        fps_frame = ttk.Frame(frame)
        fps_frame.grid(row=3, column=1, sticky=tk.W, padx=10, pady=5)
        ttk.Spinbox(fps_frame, from_=1, to=120, textvariable=self.fps, width=10).pack(side=tk.LEFT)
        ttk.Label(fps_frame, text="snímok za sekundu").pack(side=tk.LEFT, padx=5)

        # 4. Riadok: Rozlíšenie
        ttk.Label(frame, text="Rozlíšenie videa:").grid(row=4, column=0, sticky=tk.W, pady=5)
        resolutions = [
            "4K (Vysoká kvalita)",
            "Full HD (Plynulé prehrávanie)", 
            "HD (720p)",
            "SD (480p - malé)",
            "Nízka kvalita (240p - veľmi malé)",
            "Originál (Môže sekať pc)"
        ]
        ttk.Combobox(frame, textvariable=self.resolution, values=resolutions, state="readonly", width=37).grid(row=4, column=1, padx=10, pady=5, sticky=tk.W)

        # 5. Riadok: Progress bar
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(frame, variable=self.progress_var, maximum=100)
        self.progress_bar.grid(row=5, column=0, columnspan=3, sticky=tk.EW, pady=(20, 10))
        
        self.status_label = ttk.Label(frame, text="Pripravený", foreground="gray")
        self.status_label.grid(row=6, column=0, columnspan=3)

        # 6. Riadok: Tlačidlá ŠTART a Zrušiť
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=7, column=0, columnspan=3, pady=(15, 0))

        self.start_btn = ttk.Button(btn_frame, text="VYTVORIŤ TIMELAPSE", command=self.start_processing)
        self.start_btn.pack(side=tk.LEFT, ipadx=20, ipady=5)

        self.cancel_btn = ttk.Button(btn_frame, text="Zrušiť", command=self.cancel_processing, state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.LEFT, padx=(10, 0), ipadx=10, ipady=5)

    def browse_input(self):
        folder = filedialog.askdirectory(title="Vyber priečinok s obrázkami")
        if folder:
            self.input_folder.set(folder)

    def browse_output(self):
        file = filedialog.asksaveasfilename(
            title="Uložiť video", 
            defaultextension=".mp4",
            filetypes=[("MP4 Video", "*.mp4")]
        )
        if file:
            self.output_file.set(file)

    def start_processing(self, event=None):
        # Ochrana proti opätovnému spusteniu (napr. druhým stlačením Enter počas spracovania)
        if self.is_processing:
            return

        in_folder = self.input_folder.get()
        out_file = self.output_file.get()

        if not in_folder or not out_file:
            messagebox.showwarning("Upozornenie", "Prosím, vyber vstupný priečinok aj výstupný súbor.")
            return

        # Zablokujeme tlačidlo počas práce
        self.is_processing = True
        self.cancel_requested = False
        self.start_btn.config(state=tk.DISABLED)
        self.cancel_btn.config(state=tk.NORMAL)
        self.progress_var.set(0)
        self.status_label.config(text="Spracovávam...", foreground="blue")

        # Spustíme spracovanie v novom vlákne (aby nezamrzlo UI okno)
        thread = threading.Thread(target=self.process_video, args=(in_folder, out_file, self.fps.get(), self.resolution.get()))
        thread.daemon = True
        thread.start()

    def cancel_processing(self):
        self.cancel_requested = True
        self.cancel_btn.config(state=tk.DISABLED)
        self.status_label.config(text="Rušenie...", foreground="orange")

    def process_video(self, input_folder, output_file, fps, resolution_choice):
        tmp_output_path = None
        try:
            # Hľadáme aj veľké JPG z Nikonu
            extensions = ('/*.jpg', '/*.jpeg', '/*.png', '/*.JPG', '/*.JPEG', '/*.PNG')
            images = set()
            for ext in extensions:
                images.update(glob.glob(glob.escape(input_folder) + ext))

            # Zoradenie podľa čísel v názve (napr. 2 pred 10), nie čisto abecedne;
            # set() vyššie zároveň odstráni duplicity (na Windows/macOS by "*.jpg" a "*.JPG" inak našli tie isté súbory dvakrát)
            images = sorted(images, key=natural_sort_key)

            if not images:
                self.root.after(0, self.finish_processing, "Chyba: Nenašli sa žiadne obrázky.", False)
                return

            # Zistenie rozmerov videa podľa prvého obrázka
            first_frame = imread_unicode(images[0])
            if first_frame is None:
                self.root.after(0, self.finish_processing, "Chyba: Prvý obrázok je poškodený.", False)
                return

            # shape[:2] funguje pre farebné aj čiernobiele obrázky
            height, width = first_frame.shape[:2]

            # Výpočet nového rozlíšenia (so zachovaním pomeru strán, párne čísla pre kodeky)
            target_width, target_height = compute_target_resolution(width, height, resolution_choice)

            # cv2.VideoWriter zlyháva na Windows, ak výstupná cesta obsahuje diakritiku,
            # preto sa video zapisuje do dočasného súboru v systémovom temp priečinku
            # a na konci sa hotový súbor presunie na požadované miesto (presun/premenovanie
            # súborov cez os/shutil je na rozdiel od OpenCV unicode-bezpečný).
            tmp_fd, tmp_output_path = tempfile.mkstemp(suffix=os.path.splitext(output_file)[1] or ".mp4")
            os.close(tmp_fd)

            # Inicializácia VideoWriter
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            video = cv2.VideoWriter(tmp_output_path, fourcc, fps, (target_width, target_height))

            if not video.isOpened():
                self.root.after(0, self.finish_processing,
                                 "Chyba: Video sa nepodarilo vytvoriť. Skontroluj, či cieľový priečinok existuje "
                                 "a či máš práva na zápis.", False)
                return

            cancelled = False
            try:
                total_images = len(images)
                for i, image_path in enumerate(images):
                    if self.cancel_requested:
                        cancelled = True
                        break

                    img = imread_unicode(image_path)
                    if img is None:
                        continue

                    # Zabezpečenie rozmerov a zmenšenie pomocou vysoko-kvalitného INTER_AREA algoritmu
                    if img.shape[:2] != (target_height, target_width):
                        img = cv2.resize(img, (target_width, target_height), interpolation=cv2.INTER_AREA)

                    video.write(img)

                    # Aktualizácia progress baru cez hlavné vlákno
                    progress_percent = ((i + 1) / total_images) * 100
                    self.root.after(0, self.update_progress, progress_percent, f"Spracované: {i + 1} / {total_images}")
            finally:
                video.release()

            if cancelled:
                self.root.after(0, self.finish_processing, "Spracovanie bolo zrušené.", None)
                return

            # Presun hotového videa z dočasného súboru na požadované miesto
            shutil.move(tmp_output_path, output_file)
            tmp_output_path = None

            # Úspešné dokončenie
            self.root.after(0, self.finish_processing, "Video bolo úspešne vytvorené!", True)

        except Exception as e:
            self.root.after(0, self.finish_processing, f"Nastala chyba:\n{str(e)}", False)
        finally:
            if tmp_output_path and os.path.exists(tmp_output_path):
                try:
                    os.remove(tmp_output_path)
                except OSError:
                    pass

    def update_progress(self, val, text):
        self.progress_var.set(val)
        self.status_label.config(text=text)

    def finish_processing(self, message, success):
        self.is_processing = False
        self.cancel_requested = False
        self.start_btn.config(state=tk.NORMAL)
        self.cancel_btn.config(state=tk.DISABLED)
        if success is True:
            self.status_label.config(text="Hotovo!", foreground="green")
            messagebox.showinfo("Úspech", message)
        elif success is False:
            self.status_label.config(text="Chyba", foreground="red")
            messagebox.showerror("Chyba", message)
        else:
            # success is None -> spracovanie bolo zrušené používateľom
            self.status_label.config(text="Zrušené", foreground="gray")
        self.progress_var.set(0)

if __name__ == "__main__":
    root = tk.Tk()
    app = TimelapseApp(root)
    root.mainloop()
