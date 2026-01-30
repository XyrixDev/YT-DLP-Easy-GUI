import customtkinter as ctk
from tkinter import filedialog
from tkinterdnd2 import TkinterDnD, DND_FILES
import yt_dlp
import threading
import json
import os
from datetime import datetime

# --- Theme Configuration ---
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Colors
ACCENT = "#3B82F6"      # Modern Blue
SUCCESS = "#22C55E"     # Emerald Green
DANGER = "#EF4444"      # Rose Red
BG_MAIN = "#0F172A"     # Slate 900
BG_SIDE = "#020617"     # Slate 950
BG_CARD = "#1E293B"     # Slate 800

SETTINGS_FILE = "settings.json"
HISTORY_FILE = "history.json"

def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return {**default, **json.load(f)}
        except: pass
    return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=4)

settings = load_json(SETTINGS_FILE, {"default_output": os.path.expanduser("~/Downloads"), "format": "mp4"})
history = load_json(HISTORY_FILE, {"items": []})

class AnimatedButton(ctk.CTkButton):
    """Button that highlights on hover"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # RENAMED methods to avoid conflict with internal CTk methods
        self.bind("<Enter>", self.anim_hover_in)
        self.bind("<Leave>", self.anim_hover_out)

    def anim_hover_in(self, e):
        self.configure(border_width=2, border_color="#ffffff")

    def anim_hover_out(self, e):
        self.configure(border_width=0)

class QueueItem:
    def __init__(self, parent, url, title, app):
        self.url = url
        self.app = app
        self.title = title
        self.state = "waiting"

        self.frame = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=10)
        self.frame.pack(fill="x", pady=5, padx=10)
        
        # Info Row
        top = ctk.CTkFrame(self.frame, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(10, 5))

        # Title Label
        self.label = ctk.CTkLabel(top, text=self.title, font=("Segoe UI", 12, "bold"), anchor="w")
        self.label.pack(side="left", fill="x", expand=True)

        # Buttons
        self.btn_frame = ctk.CTkFrame(top, fg_color="transparent")
        self.btn_frame.pack(side="right")
        
        for icon, cmd in [("↑", self.move_up), ("↓", self.move_down), ("✕", self.remove)]:
            btn = ctk.CTkButton(self.btn_frame, text=icon, width=30, height=30, 
                               fg_color="#334155", hover_color=ACCENT, command=cmd)
            btn.pack(side="left", padx=2)

        # Progress Bar
        self.progress = ctk.CTkProgressBar(self.frame, height=8, progress_color=ACCENT)
        self.progress.pack(fill="x", pady=(5, 10), padx=10)
        self.progress.set(0)

        # Status Label
        self.status = ctk.CTkLabel(self.frame, text="Ready", font=("Segoe UI", 11), text_color="#94a3b8")
        self.status.pack(side="left", padx=10, pady=(0, 10))

    def remove(self): self.app.remove_item(self)
    def move_up(self): self.app.move_item(self, -1)
    def move_down(self): self.app.move_item(self, 1)

class App(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self.title("YT-DLP GUI Pro")
        self.geometry("1100x750")
        
        # Main Window Background
        self.configure(bg=BG_MAIN)

        self.queue_items = []
        self.is_downloading = False
        self.cancel_flag = False

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.setup_sidebar()
        self.setup_main_area()
        self.show_frame("downloader")
        
        # Drag and Drop Support
        self.drop_target_register(DND_FILES)
        self.dnd_bind('<<Drop>>', self.handle_drop)

    def setup_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color=BG_SIDE)
        self.sidebar.grid(row=0, column=0, sticky="ns")
        self.sidebar.grid_rowconfigure(5, weight=1)

        ctk.CTkLabel(self.sidebar, text="YT-DLP", font=("Segoe UI", 26, "bold"), text_color=ACCENT).pack(pady=(30, 5))
        ctk.CTkLabel(self.sidebar, text="PROFESSIONAL", font=("Segoe UI", 10, "bold"), text_color="#64748b").pack(pady=(0, 30))

        self.nav_btns = {}
        nav_items = [
            ("Downloader", "downloader"),
            ("Playlist", "playlist"),
            ("History", "history"),
            ("Settings", "settings")
        ]

        for text, key in nav_items:
            btn = ctk.CTkButton(self.sidebar, text=text, height=45, fg_color="transparent", 
                               anchor="w", corner_radius=8, font=("Segoe UI", 14),
                               text_color="#cbd5e1", hover_color="#1e293b",
                               command=lambda k=key: self.show_frame(k))
            btn.pack(fill="x", padx=15, pady=5)
            self.nav_btns[key] = btn

    def setup_main_area(self):
        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.container.grid_columnconfigure(0, weight=1)
        self.container.grid_rowconfigure(0, weight=1)

        self.frames = {
            "downloader": self.create_downloader_tab(),
            "playlist": self.create_playlist_tab(),
            "history": self.create_history_tab(),
            "settings": self.create_settings_tab()
        }

    def show_frame(self, key):
        for k, btn in self.nav_btns.items():
            if k == key:
                btn.configure(fg_color=ACCENT, text_color="white")
            else:
                btn.configure(fg_color="transparent", text_color="#cbd5e1")
        self.frames[key].tkraise()

    def create_downloader_tab(self):
        f = ctk.CTkFrame(self.container, fg_color="transparent")
        f.grid(row=0, column=0, sticky="nsew")

        # Input Area
        input_frame = ctk.CTkFrame(f, fg_color=BG_CARD, corner_radius=15)
        input_frame.pack(fill="x", pady=(0, 20))
        
        self.url_entry = ctk.CTkEntry(input_frame, placeholder_text="Paste Link Here...", 
                                     height=50, border_width=0, fg_color="transparent", 
                                     font=("Segoe UI", 14))
        self.url_entry.pack(fill="x", padx=15, pady=(15, 5))

        controls = ctk.CTkFrame(input_frame, fg_color="transparent")
        controls.pack(fill="x", padx=15, pady=(0, 15))
        
        self.format_box = ctk.CTkComboBox(controls, values=["mp4", "mkv", "mp3", "wav"], width=100)
        self.format_box.set(settings["format"])
        self.format_box.pack(side="left", padx=5)

        ctk.CTkButton(controls, text="Add to Queue", width=120, fg_color=ACCENT, 
                      command=self.add_to_queue).pack(side="right", padx=5)

        # Queue Area
        self.queue_container = ctk.CTkScrollableFrame(f, fg_color="#111", corner_radius=10)
        self.queue_container.pack(fill="both", expand=True, pady=10)

        # Action Buttons
        actions = ctk.CTkFrame(f, fg_color="transparent")
        actions.pack(fill="x", pady=10)
        
        self.start_btn = AnimatedButton(actions, text="START DOWNLOADS", font=("Segoe UI", 14, "bold"), 
                                       height=50, fg_color=SUCCESS, hover_color="#16a34a",
                                       command=self.start_queue)
        self.start_btn.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        ctk.CTkButton(actions, text="Cancel", width=100, height=50, fg_color=DANGER, 
                      hover_color="#dc2626", command=self.cancel_download).pack(side="right")
        return f

    def create_playlist_tab(self):
        f = ctk.CTkFrame(self.container, fg_color="transparent")
        f.grid(row=0, column=0, sticky="nsew")
        
        ctk.CTkLabel(f, text="Playlist Downloader", font=("Segoe UI", 24, "bold")).pack(anchor="w", pady=(0, 20))
        
        self.play_entry = ctk.CTkEntry(f, placeholder_text="Paste Playlist URL...", height=50)
        self.play_entry.pack(fill="x", pady=10)
        
        self.play_status = ctk.CTkLabel(f, text="Ready", text_color="gray")
        self.play_status.pack(pady=10)

        ctk.CTkButton(f, text="Download Playlist", height=50, fg_color=ACCENT, 
                      command=self.start_playlist_dl).pack(fill="x", pady=10)
        return f

    def create_history_tab(self):
        f = ctk.CTkFrame(self.container, fg_color="transparent")
        f.grid(row=0, column=0, sticky="nsew")
        self.history_box = ctk.CTkTextbox(f, fg_color=BG_CARD, font=("Consolas", 12))
        self.history_box.pack(expand=True, fill="both")
        self.refresh_history()
        return f

    def create_settings_tab(self):
        f = ctk.CTkFrame(self.container, fg_color="transparent")
        f.grid(row=0, column=0, sticky="nsew")
        
        ctk.CTkLabel(f, text="Settings", font=("Segoe UI", 24, "bold")).pack(anchor="w", pady=20)
        
        card = ctk.CTkFrame(f, fg_color=BG_CARD, corner_radius=10)
        card.pack(fill="x")
        
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", padx=20, pady=20)
        
        ctk.CTkLabel(inner, text="Download Location:", font=("Segoe UI", 14)).pack(anchor="w")
        
        loc_frame = ctk.CTkFrame(inner, fg_color="transparent")
        loc_frame.pack(fill="x", pady=10)
        
        self.default_out = ctk.CTkEntry(loc_frame, height=40)
        self.default_out.insert(0, settings["default_output"])
        self.default_out.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        ctk.CTkButton(loc_frame, text="Browse", width=100, command=self.browse_out).pack(side="right")
        
        ctk.CTkButton(f, text="Save Settings", height=40, fg_color=ACCENT, 
                      command=self.save_settings).pack(pady=20)
        return f

    # --- Logic ---

    def handle_drop(self, event):
        data = event.data.strip()
        if data.startswith('{') and data.endswith('}'):
            data = data[1:-1]
        self.url_entry.delete(0, "end")
        self.url_entry.insert(0, data)

    def add_to_queue(self):
        url = self.url_entry.get().strip()
        if not url: return
        
        item = QueueItem(self.queue_container, url, "Processing...", self)
        self.queue_items.append(item)
        self.url_entry.delete(0, "end")
        
        threading.Thread(target=self._fetch_title, args=(url, item), daemon=True).start()

    def _fetch_title(self, url, item):
        try:
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                title = info.get('title', url)
                self.after(0, lambda: item.label.configure(text=title))
                item.title = title
        except:
            self.after(0, lambda: item.label.configure(text="Unknown Video"))

    def start_queue(self):
        if not self.is_downloading:
            self.start_btn.configure(state="disabled", text="Running...")
            threading.Thread(target=self.worker, daemon=True).start()

    def worker(self):
        self.is_downloading = True
        self.cancel_flag = False
        
        for item in self.queue_items:
            if item.state != "waiting" or self.cancel_flag: continue
            
            try:
                def hook(d):
                    if self.cancel_flag: raise Exception("Cancelled")
                    if d['status'] == 'downloading':
                        total = d.get('total_bytes') or d.get('total_bytes_estimate', 1)
                        p = d.get('downloaded_bytes', 0) / total
                        self.after(0, lambda: self._update_ui(item, p, d.get('speed', 0)))

                opts = {
                    'format': 'bestvideo+bestaudio/best' if self.format_box.get() in ['mp4', 'mkv'] else 'bestaudio/best',
                    'outtmpl': os.path.join(settings["default_output"], '%(title)s.%(ext)s'),
                    'progress_hooks': [hook],
                    'noplaylist': True
                }
                if self.format_box.get() in ['mp3', 'wav']:
                    opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': self.format_box.get()}]

                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([item.url])
                
                item.state = "finished"
                self.after(0, lambda: item.status.configure(text="Completed", text_color=SUCCESS))
                self.log_history(item.title)
            except Exception as e:
                item.state = "error"
                self.after(0, lambda: item.status.configure(text="Failed", text_color=DANGER))

        self.is_downloading = False
        self.after(0, lambda: self.start_btn.configure(state="normal", text="START DOWNLOADS"))

    def start_playlist_dl(self):
        url = self.play_entry.get().strip()
        if not url: return
        threading.Thread(target=self._playlist_worker, args=(url,), daemon=True).start()

    def _playlist_worker(self, url):
        self.after(0, lambda: self.play_status.configure(text="Downloading Playlist... check folder"))
        try:
            opts = {
                'outtmpl': os.path.join(settings["default_output"], '%(playlist_title)s/%(title)s.%(ext)s'),
                'quiet': True
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            self.after(0, lambda: self.play_status.configure(text="Playlist Downloaded!", text_color=SUCCESS))
        except Exception:
            self.after(0, lambda: self.play_status.configure(text="Error Downloading Playlist", text_color=DANGER))

    def _update_ui(self, item, p, speed):
        item.progress.set(p)
        mb = speed/1024/1024 if speed else 0
        item.status.configure(text=f"{mb:.1f} MB/s", text_color=ACCENT)

    def log_history(self, title):
        entry = f"{datetime.now().strftime('%H:%M')} - {title}"
        history["items"].insert(0, entry)
        save_json(HISTORY_FILE, history)
        self.after(0, self.refresh_history)

    def refresh_history(self):
        self.history_box.delete("1.0", "end")
        for i in history["items"]:
            self.history_box.insert("end", i + "\n")

    def browse_out(self):
        folder = filedialog.askdirectory()
        if folder:
            self.default_out.delete(0, "end")
            self.default_out.insert(0, folder)

    def save_settings(self):
        settings["default_output"] = self.default_out.get()
        settings["format"] = self.format_box.get()
        save_json(SETTINGS_FILE, settings)

    def cancel_download(self): self.cancel_flag = True
    def remove_item(self, item): 
        item.frame.destroy()
        if item in self.queue_items: self.queue_items.remove(item)
    def move_item(self, item, direction):
        idx = self.queue_items.index(item)
        new_idx = idx + direction
        if 0 <= new_idx < len(self.queue_items):
            self.queue_items[idx], self.queue_items[new_idx] = self.queue_items[new_idx], self.queue_items[idx]
            for i in self.queue_items: i.frame.pack_forget()
            for i in self.queue_items: i.frame.pack(fill="x", pady=5, padx=10)

if __name__ == "__main__":
    app = App()
    app.mainloop()
