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

# Ultra-Modern Palette
ACCENT = "#60A5FA"      
ACCENT_HOVER = "#3B82F6"
SUCCESS = "#10B981"     
DANGER = "#F43F5E"      
BG_SIDEBAR = "#0F172A"  
BG_CONTENT = "#020617"  
BG_CARD = "#1E293B"     

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

class NavButton(ctk.CTkButton):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, height=45, corner_radius=10, fg_color="transparent", 
                         text_color="#94A3B8", hover_color="#334155", anchor="w",
                         font=("Segoe UI", 13, "bold"), **kwargs)

class HistoryItem:
    """A sleek card for previously downloaded items"""
    def __init__(self, parent, data, app):
        self.frame = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=12, border_width=1, border_color="#334155")
        self.frame.pack(fill="x", pady=6, padx=10)
        
        # Info
        info_frame = ctk.CTkFrame(self.frame, fg_color="transparent")
        info_frame.pack(side="left", fill="both", expand=True, padx=15, pady=10)
        
        title = data.get("title", "Unknown Title")
        ctk.CTkLabel(info_frame, text=title[:70] + "..." if len(title) > 70 else title, 
                     font=("Segoe UI", 13, "bold"), anchor="w").pack(fill="x")
        
        ctk.CTkLabel(info_frame, text=f"Downloaded on: {data.get('date', 'N/A')}", 
                     font=("Segoe UI", 11), text_color="#64748B", anchor="w").pack(fill="x")

        # Redo Button
        self.redo_btn = ctk.CTkButton(self.frame, text="↺ Redownload", width=110, height=32,
                                     corner_radius=8, fg_color="#334155", hover_color=ACCENT,
                                     font=("Segoe UI", 12, "bold"),
                                     command=lambda: app.add_to_queue(data.get("url")))
        self.redo_btn.pack(side="right", padx=15)

class QueueItem:
    def __init__(self, parent, url, title, app):
        self.url, self.app, self.title, self.state = url, app, title, "waiting"
        self.frame = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=15, border_width=1, border_color="#334155")
        self.frame.pack(fill="x", pady=8, padx=15)
        
        top = ctk.CTkFrame(self.frame, fg_color="transparent")
        top.pack(fill="x", padx=15, pady=(12, 5))

        self.label = ctk.CTkLabel(top, text=self.title, font=("Segoe UI", 13, "bold"), anchor="w")
        self.label.pack(side="left", fill="x", expand=True)

        self.btn_frame = ctk.CTkFrame(top, fg_color="transparent")
        self.btn_frame.pack(side="right")
        
        for icon, cmd, color in [("↑", self.move_up, "#334155"), ("↓", self.move_down, "#334155"), ("✕", self.remove, "#452a2a")]:
            ctk.CTkButton(self.btn_frame, text=icon, width=28, height=28, corner_radius=8,
                          fg_color=color, hover_color=ACCENT, command=cmd).pack(side="left", padx=3)

        self.progress = ctk.CTkProgressBar(self.frame, height=10, progress_color=ACCENT, fg_color="#0F172A")
        self.progress.pack(fill="x", pady=(8, 12), padx=15)
        self.progress.set(0)

        self.status = ctk.CTkLabel(self.frame, text="Ready", font=("Segoe UI", 11), text_color="#64748B")
        self.status.pack(side="left", padx=15, pady=(0, 12))

    def remove(self): self.app.remove_item(self)
    def move_up(self): self.app.move_item(self, -1)
    def move_down(self): self.app.move_item(self, 1)

class App(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self.title("YT-DLP Pro Edition")
        self.geometry("1150x800")
        self.configure(bg=BG_CONTENT)

        self.queue_items, self.is_downloading, self.cancel_flag = [], False, False

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.setup_sidebar()
        self.setup_main_area()
        self.show_frame("downloader")
        
        self.drop_target_register(DND_FILES)
        self.dnd_bind('<<Drop>>', self.handle_drop)

    def setup_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=240, corner_radius=0, fg_color=BG_SIDEBAR)
        self.sidebar.grid(row=0, column=0, sticky="ns")
        
        title_f = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        title_f.pack(pady=40, padx=20, fill="x")
        ctk.CTkLabel(title_f, text="YT-DLP", font=("Segoe UI", 32, "bold"), text_color=ACCENT).pack(anchor="w")
        ctk.CTkLabel(title_f, text="PRO ENGINE", font=("Segoe UI", 11, "bold"), text_color="#475569").pack(anchor="w", padx=2)

        self.nav_btns = {}
        for text, key in [("📥  Downloads", "downloader"), ("📂  Playlists", "playlist"), ("🕒  History", "history"), ("⚙️  Settings", "settings")]:
            btn = NavButton(self.sidebar, text=text, command=lambda k=key: self.show_frame(k))
            btn.pack(fill="x", padx=15, pady=4)
            self.nav_btns[key] = btn

        self.status_badge = ctk.CTkFrame(self.sidebar, fg_color="#1E293B", corner_radius=12)
        self.status_badge.pack(side="bottom", fill="x", padx=20, pady=20)
        ffmpeg_stat = "FFmpeg: OK" if os.path.exists("ffmpeg.exe") else "FFmpeg: Missing"
        ctk.CTkLabel(self.status_badge, text=ffmpeg_stat, font=("Segoe UI", 12, "bold"), 
                     text_color=SUCCESS if "OK" in ffmpeg_stat else DANGER).pack(pady=10)

    def setup_main_area(self):
        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.grid(row=0, column=1, sticky="nsew", padx=40, pady=30)
        self.container.grid_columnconfigure(0, weight=1)
        self.container.grid_rowconfigure(0, weight=1)

        self.frames = {k: getattr(self, f"create_{k}_tab")() for k in ["downloader", "playlist", "history", "settings"]}

    def show_frame(self, key):
        for k, btn in self.nav_btns.items():
            btn.configure(fg_color="#2563EB" if k == key else "transparent", text_color="white" if k == key else "#94A3B8")
        self.frames[key].tkraise()
        if key == "history": self.refresh_history()

    def create_downloader_tab(self):
        f = ctk.CTkFrame(self.container, fg_color="transparent")
        f.grid(row=0, column=0, sticky="nsew")
        input_card = ctk.CTkFrame(f, fg_color=BG_CARD, corner_radius=20, border_width=1, border_color="#334155")
        input_card.pack(fill="x", pady=(0, 20))
        self.url_entry = ctk.CTkEntry(input_card, placeholder_text="Enter Video Link...", height=55, border_width=0, fg_color="transparent", font=("Segoe UI", 15))
        self.url_entry.pack(fill="x", padx=20, pady=(15, 5))
        ctrls = ctk.CTkFrame(input_card, fg_color="transparent")
        ctrls.pack(fill="x", padx=20, pady=(0, 15))
        self.format_box = ctk.CTkComboBox(ctrls, values=["mp4", "mkv", "mp3", "wav"], width=110, corner_radius=10, fg_color="#0F172A")
        self.format_box.set(settings["format"]); self.format_box.pack(side="left")
        ctk.CTkButton(ctrls, text="+ Add to Queue", width=140, height=35, corner_radius=10, fg_color=ACCENT, command=lambda: self.add_to_queue()).pack(side="right")
        self.queue_container = ctk.CTkScrollableFrame(f, fg_color="#020617", corner_radius=15, border_width=1, border_color="#1E293B")
        self.queue_container.pack(fill="both", expand=True, pady=10)
        actions = ctk.CTkFrame(f, fg_color="transparent")
        actions.pack(fill="x", pady=(15, 0))
        self.start_btn = ctk.CTkButton(actions, text="INITIALIZE DOWNLOAD ENGINE", font=("Segoe UI", 15, "bold"), height=55, corner_radius=15, fg_color=SUCCESS, command=self.start_queue)
        self.start_btn.pack(side="left", fill="x", expand=True, padx=(0, 10))
        ctk.CTkButton(actions, text="Cancel All", width=120, height=55, corner_radius=15, fg_color="#334155", command=self.cancel_download).pack(side="right")
        return f

    def create_playlist_tab(self):
        f = ctk.CTkFrame(self.container, fg_color="transparent")
        f.grid(row=0, column=0, sticky="nsew")
        ctk.CTkLabel(f, text="Playlist Engine", font=("Segoe UI", 28, "bold")).pack(anchor="w", pady=(0, 20))
        self.play_entry = ctk.CTkEntry(f, placeholder_text="Paste Playlist Link...", height=55, corner_radius=15)
        self.play_entry.pack(fill="x", pady=10)
        self.play_status = ctk.CTkLabel(f, text="Ready", text_color="#64748B")
        self.play_status.pack(pady=10)
        ctk.CTkButton(f, text="Start Playlist Processing", height=55, corner_radius=15, fg_color=ACCENT, command=self.start_playlist_dl).pack(fill="x", pady=10)
        return f

    def create_history_tab(self):
        f = ctk.CTkFrame(self.container, fg_color="transparent")
        f.grid(row=0, column=0, sticky="nsew")
        
        header = ctk.CTkFrame(f, fg_color="transparent")
        header.pack(fill="x", pady=(0, 20))
        ctk.CTkLabel(header, text="Recent Downloads", font=("Segoe UI", 28, "bold")).pack(side="left")
        ctk.CTkButton(header, text="Clear All", width=100, fg_color="transparent", text_color=DANGER, hover_color="#2a1a1a", command=self.clear_history).pack(side="right", pady=5)
        
        self.history_container = ctk.CTkScrollableFrame(f, fg_color="#020617", corner_radius=15, border_width=1, border_color="#1E293B")
        self.history_container.pack(fill="both", expand=True)
        return f

    def create_settings_tab(self):
        f = ctk.CTkFrame(self.container, fg_color="transparent")
        f.grid(row=0, column=0, sticky="nsew")
        ctk.CTkLabel(f, text="Preferences", font=("Segoe UI", 28, "bold")).pack(anchor="w", pady=(0, 20))
        card = ctk.CTkFrame(f, fg_color=BG_CARD, corner_radius=20)
        card.pack(fill="x")
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", padx=30, pady=30)
        ctk.CTkLabel(inner, text="Target Directory", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        loc_f = ctk.CTkFrame(inner, fg_color="transparent")
        loc_f.pack(fill="x", pady=15)
        self.default_out = ctk.CTkEntry(loc_f, height=45, corner_radius=10, fg_color="#0F172A")
        self.default_out.insert(0, settings["default_output"]); self.default_out.pack(side="left", fill="x", expand=True, padx=(0, 10))
        ctk.CTkButton(loc_f, text="Change Folder", width=120, height=45, corner_radius=10, fg_color="#334155", command=self.browse_out).pack(side="right")
        ctk.CTkButton(f, text="Apply & Save Settings", height=50, width=250, corner_radius=15, fg_color=ACCENT, command=self.save_settings).pack(pady=30)
        return f

    # --- Logic ---

    def handle_drop(self, event):
        data = event.data.strip()
        if data.startswith('{') and data.endswith('}'): data = data[1:-1]
        self.url_entry.delete(0, "end"); self.url_entry.insert(0, data)

    def add_to_queue(self, url=None):
        target_url = url if url else self.url_entry.get().strip()
        if not target_url: return
        self.show_frame("downloader")
        item = QueueItem(self.queue_container, target_url, "Analyzing...", self)
        self.queue_items.append(item)
        if not url: self.url_entry.delete(0, "end")
        threading.Thread(target=self._fetch_title, args=(target_url, item), daemon=True).start()

    def _fetch_title(self, url, item):
        try:
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                title = info.get('title', url)
                self.after(0, lambda: item.label.configure(text=title[:80]))
                item.title = title
        except: self.after(0, lambda: item.label.configure(text="Video Loaded"))

    def start_queue(self):
        if not self.is_downloading:
            self.start_btn.configure(state="disabled", text="PROCESSING...")
            threading.Thread(target=self.worker, daemon=True).start()

    def worker(self):
        self.is_downloading, self.cancel_flag = True, False
        for item in self.queue_items:
            if item.state != "waiting" or self.cancel_flag: continue
            try:
                def hook(d):
                    if self.cancel_flag: raise Exception("Stop")
                    if d['status'] == 'downloading':
                        total = d.get('total_bytes') or d.get('total_bytes_estimate', 1)
                        p = d.get('downloaded_bytes', 0) / total
                        self.after(0, lambda: self._update_ui(item, p, d.get('speed', 0)))
                
                fmt = self.format_box.get()
                opts = {'format': 'bestvideo+bestaudio/best' if fmt in ['mp4', 'mkv'] else 'bestaudio/best',
                        'outtmpl': os.path.join(settings["default_output"], '%(title)s.%(ext)s'),
                        'progress_hooks': [hook], 'noplaylist': True}
                if fmt in ['mp3', 'wav']: opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': fmt}]

                with yt_dlp.YoutubeDL(opts) as ydl: ydl.download([item.url])
                item.state = "finished"
                self.after(0, lambda: item.status.configure(text="✔ Success", text_color=SUCCESS))
                self.log_history(item.title, item.url)
            except Exception:
                item.state = "error"
                self.after(0, lambda: item.status.configure(text="✖ Stopped", text_color=DANGER))
        self.is_downloading = False
        self.after(0, lambda: self.start_btn.configure(state="normal", text="INITIALIZE DOWNLOAD ENGINE"))

    def _update_ui(self, item, p, speed):
        item.progress.set(p)
        mb = speed/1024/1024 if speed else 0
        item.status.configure(text=f"{mb:.2f} MB/s | {int(p*100)}%", text_color=ACCENT)

    def log_history(self, title, url):
        history["items"].insert(0, {"title": title, "url": url, "date": datetime.now().strftime("%d %b, %H:%M")})
        save_json(HISTORY_FILE, history)

    def refresh_history(self):
        for widget in self.history_container.winfo_children(): widget.destroy()
        for i in history["items"]: HistoryItem(self.history_container, i, self)

    def clear_history(self):
        history["items"] = []
        save_json(HISTORY_FILE, history)
        self.refresh_history()

    def browse_out(self):
        folder = filedialog.askdirectory()
        if folder: self.default_out.delete(0, "end"); self.default_out.insert(0, folder)

    def save_settings(self):
        settings.update({"default_output": self.default_out.get(), "format": self.format_box.get()})
        save_json(SETTINGS_FILE, settings)

    def start_playlist_dl(self):
        url = self.play_entry.get().strip()
        if not url: return
        threading.Thread(target=self._playlist_worker, args=(url,), daemon=True).start()

    def _playlist_worker(self, url):
        self.after(0, lambda: self.play_status.configure(text="Gathering playlist..."))
        try:
            opts = {'outtmpl': os.path.join(settings["default_output"], '%(playlist_title)s/%(title)s.%(ext)s'), 'quiet': True}
            with yt_dlp.YoutubeDL(opts) as ydl: ydl.download([url])
            self.after(0, lambda: self.play_status.configure(text="✔ Playlist Complete!", text_color=SUCCESS))
        except: self.after(0, lambda: self.play_status.configure(text="✖ Error", text_color=DANGER))

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
            for i in self.queue_items: i.frame.pack(fill="x", pady=8, padx=15)

if __name__ == "__main__":
    App().mainloop()
