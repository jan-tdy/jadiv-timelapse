import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import cv2
import glob
import threading
import os

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

        # 6. Riadok: Tlačidlo ŠTART
        self.start_btn = ttk.Button(frame, text="VYTVORIŤ TIMELAPSE", command=self.start_processing)
        self.start_btn.grid(row=7, column=0, columnspan=3, pady=(15, 0), ipadx=20, ipady=5)

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
        in_folder = self.input_folder.get()
        out_file = self.output_file.get()

        if not in_folder or not out_file:
            messagebox.showwarning("Upozornenie", "Prosím, vyber vstupný priečinok aj výstupný súbor.")
            return

        # Zablokujeme tlačidlo počas práce
        self.start_btn.config(state=tk.DISABLED)
        self.progress_var.set(0)
        self.status_label.config(text="Spracovávam...", foreground="blue")

        # Spustíme spracovanie v novom vlákne (aby nezamrzlo UI okno)
        thread = threading.Thread(target=self.process_video, args=(in_folder, out_file, self.fps.get(), self.resolution.get()))
        thread.daemon = True
        thread.start()

    def process_video(self, input_folder, output_file, fps, resolution_choice):
        try:
            # Hľadáme aj veľké JPG z Nikonu
            extensions = ('/*.jpg', '/*.jpeg', '/*.png', '/*.JPG', '/*.JPEG', '/*.PNG')
            images = []
            for ext in extensions:
                images.extend(glob.glob(glob.escape(input_folder) + ext))
            
            # Zoradenie podľa abecedy/čísel
            images = sorted(images)

            if not images:
                self.root.after(0, self.finish_processing, "Chyba: Nenašli sa žiadne obrázky.", False)
                return

            # Zistenie rozmerov videa podľa prvého obrázka
            first_frame = cv2.imread(images[0])
            if first_frame is None:
                self.root.after(0, self.finish_processing, "Chyba: Prvý obrázok je poškodený.", False)
                return
                
            height, width, _ = first_frame.shape

            # Výpočet nového rozlíšenia podľa výberu (so zachovaním pomeru strán)
            target_width = width
            target_height = height
            
            if "Full HD" in resolution_choice:
                target_width = 1920
                target_height = int((1920 / width) * height)
            elif "4K" in resolution_choice:
                target_width = 3840
                target_height = int((3840 / width) * height)
            elif "720p" in resolution_choice:
                target_height = 720
                target_width = int((720 / height) * width)
            elif "480p" in resolution_choice:
                target_height = 480
                target_width = int((480 / height) * width)
            elif "240p" in resolution_choice:
                target_height = 240
                target_width = int((240 / height) * width)
                
            # Kodeky MP4 vyžadujú, aby šírka aj výška boli párne čísla, inak zlyhajú
            target_width = target_width - (target_width % 2)
            target_height = target_height - (target_height % 2)

            # Inicializácia VideoWriter - TOTO V TVOJOM KÓDE CHÝBALO
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            video = cv2.VideoWriter(output_file, fourcc, fps, (target_width, target_height))

            try:
                total_images = len(images)
                for i, image_path in enumerate(images):
                    img = cv2.imread(image_path)
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

            # Úspešné dokončenie
            self.root.after(0, self.finish_processing, "Video bolo úspešne vytvorené!", True)

        except Exception as e:
            self.root.after(0, self.finish_processing, f"Nastala chyba:\n{str(e)}", False)

    def update_progress(self, val, text):
        self.progress_var.set(val)
        self.status_label.config(text=text)

    def finish_processing(self, message, success):
        self.start_btn.config(state=tk.NORMAL)
        if success:
            self.status_label.config(text="Hotovo!", foreground="green")
            messagebox.showinfo("Úspech", message)
        else:
            self.status_label.config(text="Chyba", foreground="red")
            messagebox.showerror("Chyba", message)
        self.progress_var.set(0)

if __name__ == "__main__":
    root = tk.Tk()
    app = TimelapseApp(root)
    root.mainloop()
