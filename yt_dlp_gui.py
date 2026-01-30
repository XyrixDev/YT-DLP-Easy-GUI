import customtkinter as ctk
from tkinter import filedialog
from tkinterdnd2 import TkinterDnD, DND_FILES
from PIL import Image, ImageTk
import yt_dlp
import threading
import json
import os
import requests
from io import BytesIO
from datetime import datetime

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

SETTINGS_FILE = "settings.json"
HISTORY_FILE = "history.json"


def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                default.update(json.load(f))
        except:
            pass
    return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=4)


settings = load_json(SETTINGS_FILE, {
    "default_output": "",
    "format": "mp4",
    "resolution": "Best"
})

history = load_json(HISTORY_FILE, {"items": []})


class QueueItem:
    def __init__(self, parent, url, app):
        self.url = url
        self.app = app
        self.state = "waiting"

        self.frame = ctk.CTkFrame(parent)
        self.frame.pack(fill="x", pady=6, padx=10)

        top = ctk.CTkFrame(self.frame)
        top.pack(fill="x")

        self.label = ctk.CTkLabel(top, text=url, anchor="w")
        self.label.pack(side="left", fill="x", expand=True)

        ctk.CTkButton(top, text="↑", width=30,
                      command=self.move_up).pack(side="right", padx=2)
        ctk.CTkButton(top, text="↓", width=30,
                      command=self.move_down).pack(side="right", padx=2)
        ctk.CTkButton(top, text="✕", width=30,
                      command=self.remove).pack(side="right", padx=2)

        self.progress = ctk.CTkProgressBar(self.frame)
        self.progress.pack(fill="x", pady=4)
        self.progress.set(0)

        bottom = ctk.CTkFrame(self.frame)
        bottom.pack(fill="x")

        self.status = ctk.CTkLabel(bottom, text="Waiting...")
        self.status.pack(side="left")

        self.retry_btn = ctk.CTkButton(
            bottom, text="Retry", width=60,
            command=self.retry
        )
        self.retry_btn.pack(side="right")
        self.retry_btn.configure(state="disabled")

    def remove(self):
        self.app.remove_item(self)

    def move_up(self):
        self.app.move_item(self, -1)

    def move_down(self):
        self.app.move_item(self, 1)

    def retry(self):
        self.progress.set(0)
        self.status.configure(text="Waiting...")
        self.retry_btn.configure(state="disabled")
        self.state = "waiting"


class App(TkinterDnD.Tk):

    def __init__(self):
        super().__init__()
        self.title("yt-dlp GUI Pro")
        self.geometry("1200x760")
        self.minsize(1000, 650)

        self.queue_items = []
        self.current_ydl = None
        self.cancel_flag = False

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.create_frames()
        self.create_sidebar()
        self.show_frame(self.downloader_frame)

        self.drop_target_register(DND_FILES)
        self.dnd_bind('<<Drop>>', self.handle_drop)

    def remove_item(self, item):
        if item in self.queue_items:
            item.frame.destroy()
            self.queue_items.remove(item)

    def move_item(self, item, direction):
        idx = self.queue_items.index(item)
        new_idx = idx + direction

        if 0 <= new_idx < len(self.queue_items):
            self.queue_items[idx], self.queue_items[new_idx] = \
                self.queue_items[new_idx], self.queue_items[idx]

            for i in self.queue_items:
                i.frame.pack_forget()
                i.frame.pack(fill="x", pady=6, padx=10)

    def create_frames(self):
        self.downloader_frame = self.create_downloader_tab()
        self.playlist_frame = self.create_playlist_tab()
        self.history_frame = self.create_history_tab()
        self.settings_frame = self.create_settings_tab()

    def create_sidebar(self):
        sb = ctk.CTkFrame(self, width=220)
        sb.grid(row=0, column=0, sticky="ns")

        ctk.CTkLabel(sb, text="yt-dlp GUI Pro",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(pady=20)

        nav = [
            ("Downloader", self.downloader_frame),
            ("Playlist", self.playlist_frame),
            ("History", self.history_frame),
            ("Settings", self.settings_frame),
        ]

        for text, frame in nav:
            ctk.CTkButton(
                sb,
                text=text,
                command=lambda f=frame: self.show_frame(f)
            ).pack(fill="x", padx=12, pady=6)

    def show_frame(self, frame):
        frame.tkraise()

    def create_downloader_tab(self):
        f = ctk.CTkFrame(self)
        f.grid(row=0, column=1, sticky="nsew")
        f.grid_columnconfigure(0, weight=1)

        self.url_entry = ctk.CTkEntry(f)
        self.url_entry.pack(fill="x", padx=15, pady=15)

        ctk.CTkButton(f, text="Fetch Info",
                      command=self.fetch_info).pack()

        self.thumb_label = ctk.CTkLabel(f, text="")
        self.thumb_label.pack(pady=10)

        opts = ctk.CTkFrame(f)
        opts.pack(pady=10)

        self.format_box = ctk.CTkComboBox(opts, values=["mp4", "mkv", "mp3"])
        self.format_box.set(settings["format"])
        self.format_box.pack(side="left", padx=10)

        self.res_box = ctk.CTkComboBox(opts, values=["Best", "1080p", "720p"])
        self.res_box.set(settings["resolution"])
        self.res_box.pack(side="left", padx=10)

        ctk.CTkButton(opts, text="Add to Queue",
                      command=self.add_to_queue).pack(side="left", padx=10)

        self.queue_container = ctk.CTkScrollableFrame(f, height=300)
        self.queue_container.pack(fill="both", expand=True, padx=15, pady=10)

        btns = ctk.CTkFrame(f)
        btns.pack(pady=10)

        ctk.CTkButton(btns, text="Start",
                      command=self.start_queue).pack(side="left", padx=10)
        ctk.CTkButton(btns, text="Cancel Current",
                      command=self.cancel_download).pack(side="left", padx=10)

        return f

    def create_playlist_tab(self):
        f = ctk.CTkFrame(self)
        f.grid(row=0, column=1, sticky="nsew")
        self.playlist_entry = ctk.CTkEntry(f, width=700)
        self.playlist_entry.pack(pady=40)
        ctk.CTkButton(f, text="Download Playlist",
                      command=self.download_playlist).pack()
        return f

    def create_history_tab(self):
        f = ctk.CTkFrame(self)
        f.grid(row=0, column=1, sticky="nsew")
        self.history_box = ctk.CTkTextbox(f)
        self.history_box.pack(expand=True, fill="both", padx=20, pady=20)
        self.refresh_history()
        return f

    def create_settings_tab(self):
        f = ctk.CTkFrame(self)
        f.grid(row=0, column=1, sticky="nsew")
        self.default_out = ctk.CTkEntry(f, width=600)
        self.default_out.insert(0, settings["default_output"])
        self.default_out.pack(pady=20)
        ctk.CTkButton(f, text="Browse", command=self.browse_out).pack()
        ctk.CTkButton(f, text="Save Settings", command=self.save_settings).pack(pady=20)
        return f

    def handle_drop(self, event):
        self.url_entry.insert(0, event.data.strip())

    def add_to_queue(self):
        url = self.url_entry.get().strip()
        if url:
            item = QueueItem(self.queue_container, url, self)
            self.queue_items.append(item)
            self.url_entry.delete(0, "end")

    def ydl_opts(self, item):
        def hook(d):
            if d['status'] == 'downloading':
                item.state = "downloading"
                total = d.get('total_bytes') or d.get('total_bytes_estimate')
                done = d.get('downloaded_bytes', 0)

                if total:
                    item.progress.set(done / total)

                speed = d.get('speed', 0) or 0
                eta = d.get('eta', 0) or 0

                item.status.configure(
                    text=f"{speed/1024/1024:.2f} MB/s | ETA {eta}s"
                )

                if self.cancel_flag:
                    raise Exception("Cancelled")

            if d['status'] == 'finished':
                item.state = "finished"
                item.status.configure(text="Finished")

        out = settings["default_output"]
        opts = {
            'outtmpl': os.path.join(out, '%(title)s.%(ext)s') if out else '%(title)s.%(ext)s',
            'progress_hooks': [hook]
        }
        return opts

    def worker(self):
        self.cancel_flag = False
        for item in self.queue_items:
            try:
                with yt_dlp.YoutubeDL(self.ydl_opts(item)) as ydl:
                    self.current_ydl = ydl
                    ydl.download([item.url])

                history["items"].append(
                    f"{datetime.now().strftime('%H:%M:%S')} - {item.url}"
                )
                save_json(HISTORY_FILE, history)
                self.refresh_history()

            except Exception:
                if self.cancel_flag:
                    item.state = "cancelled"
                    item.status.configure(text="Cancelled")
                else:
                    item.state = "error"
                    item.status.configure(text="Error")
                item.retry_btn.configure(state="normal")

            if self.cancel_flag:
                break

    def start_queue(self):
        threading.Thread(target=self.worker, daemon=True).start()

    def cancel_download(self):
        self.cancel_flag = True

    def fetch_info(self):
        url = self.url_entry.get()
        if not url:
            return

        def worker():
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                img = requests.get(info['thumbnail']).content
                im = Image.open(BytesIO(img)).resize((320, 180))
                photo = ImageTk.PhotoImage(im)
                self.thumb_label.configure(image=photo)
                self.thumb_label.image = photo

        threading.Thread(target=worker, daemon=True).start()

    def browse_out(self):
        folder = filedialog.askdirectory()
        if folder:
            self.default_out.delete(0, "end")
            self.default_out.insert(0, folder)

    def save_settings(self):
        settings["default_output"] = self.default_out.get()
        save_json(SETTINGS_FILE, settings)

    def refresh_history(self):
        self.history_box.delete("1.0", "end")
        for i in history["items"]:
            self.history_box.insert("end", i + "\n")

    def download_playlist(self):
        url = self.playlist_entry.get().strip()
        if not url:
            return
        threading.Thread(
            target=lambda: yt_dlp.YoutubeDL(self.ydl_opts(self.queue_items[0] if self.queue_items else None)).download([url]),
            daemon=True
        ).start()


if __name__ == "__main__":
    app = App()
    app.mainloop()

# rawr
