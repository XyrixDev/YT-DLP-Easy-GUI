import os
import sys
import json
import threading
import time
import sqlite3
import re
import platform
import psutil
import urllib.request
import subprocess
import uuid
import datetime
import io
import cv2
import queue
from collections import deque
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, filedialog
from tkinterdnd2 import TkinterDnD, DND_FILES
import customtkinter as ctk
from PIL import Image, ImageTk
import yt_dlp
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

PALETTE = {
    "primary": "#6366f1", "secondary": "#4f46e5", "bg_main": "#020617", 
    "bg_card": "#0f172a", "bg_border": "#1e293b", "text_p": "#f8fafc", 
    "text_s": "#94a3b8", "accent": "#10b981", "danger": "#ef4444",
    "warning": "#f59e0b", "cyan": "#06b6d4", "purple": "#a855f7",
    "slate": "#1e293b", "rose": "#f43f5e", "amber": "#fbbf24",
    "emerald": "#10b981", "indigolight": "#818cf8"
}

class EasyStorage:
    def __init__(self):
        self.db_path = "ytdlp_easy_gui_core.db"
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS downloads (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    url TEXT,
                    timestamp DATETIME,
                    container TEXT,
                    resolution TEXT,
                    status TEXT,
                    file_path TEXT
                )
            """)
            conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, val TEXT)")

    def log_transaction(self, t, u, c, r, s, p):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("INSERT INTO downloads VALUES (?,?,?,?,?,?,?,?)",
                             (str(uuid.uuid4()), t, u, datetime.datetime.now(), c, r, s, p))
        except:
            pass

class EasyFrame(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        defaults = {"fg_color": PALETTE["bg_card"], "border_color": PALETTE["bg_border"], 
                    "border_width": 1, "corner_radius": 15}
        defaults.update(kwargs)
        super().__init__(master, **defaults)

class EasyButton(ctk.CTkButton):
    def __init__(self, master, text="Action", icon=None, **kwargs):
        h = kwargs.pop("height", 45)
        f = kwargs.pop("font", ("Inter", 13, "bold"))
        fg = kwargs.pop("fg_color", PALETTE["bg_border"])
        txt = f"{icon}  {text}" if icon else text
        super().__init__(master, text=txt, height=h, font=f, fg_color=fg,
                         hover_color=PALETTE["primary"], text_color=PALETTE["text_p"],
                         corner_radius=10, **kwargs)

class YTDLPEasyGUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        try:
            self.tkdnd = TkinterDnD._require(self)
        except:
            pass
            
        self.title("YT-DLP Easy GUI")
        self.geometry("1850x1050")
        self.configure(fg_color=PALETTE["bg_main"])
        
        self.bus = queue.Queue()
        self.db = EasyStorage()
        self.tabs = {}
        self.nav_elements = {}
        self.task_registry = {}
        self.kill_preview = threading.Event()
        
        self.vars = {
            "url": tk.StringVar(),
            "target_id": tk.StringVar(),
            "target_res": tk.StringVar(),
            "ext": tk.StringVar(value="mp4"),
            "path": tk.StringVar(value=str(Path.home() / "Downloads")),
            "t_start": tk.StringVar(value="00:00:00"),
            "t_end": tk.StringVar(value="00:00:10"),
            "opt_sponsor": tk.BooleanVar(value=True),
            "opt_aac": tk.BooleanVar(value=True),
            "opt_thumb": tk.BooleanVar(value=True),
            "opt_gpu": tk.BooleanVar(value=True),
            "opt_subs": tk.BooleanVar(value=False)
        }
        
        self.telemetry_cpu = deque([0]*100, maxlen=100)
        self.cache_media = None
        self.cache_playlist = []

        self._build_scaffold()
        self._ignite_daemons()

    def _build_scaffold(self):
        self.sidebar = ctk.CTkFrame(self, width=320, corner_radius=0, fg_color=PALETTE["bg_main"])
        self.sidebar.pack(side="left", fill="y")
        
        ctk.CTkLabel(self.sidebar, text="YT-DLP", font=("Inter", 48, "bold"), text_color=PALETTE["primary"]).pack(pady=(60,0))
        ctk.CTkLabel(self.sidebar, text="Easy GUI - v0.02", font=("Inter", 11, "bold"), text_color=PALETTE["text_s"]).pack(pady=(0,50))

        nav = [
            ("Dashboard", "⚡"), ("Playlist Engine", "🧬"), ("Clip Surgeon", "✂️"), 
            ("Live Monitor", "📡"), ("Execution Queue", "🔋"), ("Log History", "📜"), 
            ("System Telemetry", "📊"), ("Global Config", "🛠️")
        ]
        
        for name, icon in nav:
            b = EasyButton(self.sidebar, text=name, icon=icon, width=260, anchor="w", command=lambda n=name: self.navigate(n))
            b.pack(pady=4, padx=30)
            self.nav_elements[name] = b

        self.screen = ctk.CTkFrame(self, fg_color="transparent")
        self.screen.pack(side="right", fill="both", expand=True, padx=40, pady=40)

        self._ui_dashboard()
        self._ui_playlist()
        self._ui_surgeon()
        self._ui_monitor()
        self._ui_queue()
        self._ui_logs()
        self._ui_telemetry()
        self._ui_config()
        
        self.navigate("Dashboard")

    def _ui_dashboard(self):
        p = ctk.CTkFrame(self.screen, fg_color="transparent")
        self.tabs["Dashboard"] = p
        
        h = EasyFrame(p, height=130)
        h.pack(fill="x", pady=(0, 25))
        h.pack_propagate(False)
        
        self.url_bar = ctk.CTkEntry(h, textvariable=self.vars["url"], placeholder_text="REACH PROTOCOL: Input Media URL...", height=55, font=("Inter", 15), border_color=PALETTE["bg_border"], fg_color=PALETTE["bg_main"])
        self.url_bar.pack(side="left", fill="x", expand=True, padx=30)
        
        EasyButton(h, text="INITIALIZE SCAN", width=180, fg_color=PALETTE["primary"], command=self.op_scan).pack(side="right", padx=30)

        split = ctk.CTkFrame(p, fg_color="transparent")
        split.pack(fill="both", expand=True)

        self.res_shell = EasyFrame(split)
        self.res_shell.pack(side="left", fill="both", expand=True, padx=(0, 15))
        ctk.CTkLabel(self.res_shell, text="RESOLUTION MANIFEST", font=("Inter", 13, "bold"), text_color=PALETTE["text_s"]).pack(pady=20)
        
        self.res_scroll = ctk.CTkScrollableFrame(self.res_shell, fg_color="transparent")
        self.res_scroll.pack(fill="both", expand=True, padx=15, pady=10)

        self.info_pane = EasyFrame(split, width=450)
        self.info_pane.pack(side="right", fill="y")
        self.info_pane.pack_propagate(False)

        self.viz_preview = ctk.CTkLabel(self.info_pane, text="IDLE_WAITING_FOR_INPUT", width=390, height=220, fg_color="#000", corner_radius=12)
        self.viz_preview.pack(pady=25, padx=25)

        self.meta_box = ctk.CTkFrame(self.info_pane, fg_color="transparent")
        self.meta_box.pack(fill="x", padx=40)
        
        ctk.CTkLabel(self.meta_box, text="TARGET ENCODING", font=("Inter", 10, "bold"), text_color=PALETTE["text_s"]).pack(anchor="w")
        ctk.CTkSegmentedButton(self.meta_box, variable=self.vars["ext"], values=["mp4", "mkv", "mp3", "wav"], height=45, selected_color=PALETTE["secondary"], fg_color=PALETTE["bg_main"]).pack(fill="x", pady=15)

        self.btn_run = EasyButton(self.info_pane, text="EXECUTE FULL DEPLOY", height=80, fg_color=PALETTE["emerald"], state="disabled", command=self.op_download_full)
        self.btn_run.pack(side="bottom", fill="x", padx=40, pady=40)

    def _ui_surgeon(self):
        p = ctk.CTkFrame(self.screen, fg_color="transparent")
        self.tabs["Clip Surgeon"] = p
        w = EasyFrame(p); w.pack(expand=True, fill="both", padx=80, pady=80)
        ctk.CTkLabel(w, text="TEMPORAL CLIP EXTRACTION", font=("Inter", 32, "bold")).pack(pady=(60,15))
        ctk.CTkLabel(w, text="Nondestructive extraction using stream-copy architecture.", text_color=PALETTE["text_s"]).pack(pady=(0,50))
        rs = ctk.CTkFrame(w, fg_color="transparent"); rs.pack(pady=25)
        st = {"font": ("JetBrains Mono", 28), "width": 240, "height": 70, "justify": "center", "fg_color": PALETTE["bg_main"], "border_color": PALETTE["bg_border"]}
        ls = ctk.CTkFrame(rs, fg_color="transparent"); ls.pack(side="left", padx=50)
        ctk.CTkLabel(ls, text="VECTOR START (HH:MM:SS)", font=("Inter", 11, "bold")).pack(pady=10)
        ctk.CTkEntry(ls, textvariable=self.vars["t_start"], **st).pack()
        rx = ctk.CTkFrame(rs, fg_color="transparent"); rx.pack(side="left", padx=50)
        ctk.CTkLabel(rx, text="VECTOR END (HH:MM:SS)", font=("Inter", 11, "bold")).pack(pady=10)
        ctk.CTkEntry(rx, textvariable=self.vars["t_end"], **st).pack()
        EasyButton(w, text="INJECT EXTRACTION TASK", fg_color=PALETTE["warning"], width=450, height=80, command=self.op_download_clip).pack(pady=60)

    def _ui_playlist(self):
        p = ctk.CTkFrame(self.screen, fg_color="transparent")
        self.tabs["Playlist Engine"] = p
        self.pl_list = ctk.CTkScrollableFrame(p, fg_color=PALETTE["bg_card"], border_width=1, border_color=PALETTE["bg_border"])
        self.pl_list.pack(fill="both", expand=True, pady=(0,25))
        EasyButton(p, text="QUEUE ALL VALIDATED ENTRIES", height=70, fg_color=PALETTE["primary"], command=self.op_bulk).pack(fill="x")

    def _ui_monitor(self):
        p = ctk.CTkFrame(self.screen, fg_color="transparent")
        self.tabs["Live Monitor"] = p
        self.mon_canv = tk.Canvas(p, bg="#000", highlightthickness=0)
        self.mon_canv.pack(fill="both", expand=True, padx=15, pady=15)
        EasyButton(p, text="ACTIVATE STREAM INTERCEPT", width=300, command=self.op_preview).pack(pady=15)

    def _ui_queue(self):
        p = ctk.CTkFrame(self.screen, fg_color="transparent")
        self.tabs["Execution Queue"] = p
        self.q_scroll = ctk.CTkScrollableFrame(p, fg_color="transparent")
        self.q_scroll.pack(fill="both", expand=True)

    def _ui_logs(self):
        p = ctk.CTkFrame(self.screen, fg_color="transparent")
        self.tabs["Log History"] = p
        self.log_scroll = ctk.CTkScrollableFrame(p, fg_color="transparent")
        self.log_scroll.pack(fill="both", expand=True)

    def _ui_telemetry(self):
        p = ctk.CTkFrame(self.screen, fg_color="transparent")
        self.tabs["System Telemetry"] = p
        self.tel_fig = Figure(figsize=(12, 6), facecolor=PALETTE["bg_card"])
        self.tel_ax = self.tel_fig.add_subplot(111)
        self.tel_ax.set_facecolor(PALETTE["bg_card"])
        self.tel_canv = FigureCanvasTkAgg(self.tel_fig, master=p)
        self.tel_canv.get_tk_widget().pack(fill="both", expand=True)

    def _ui_config(self):
        p = ctk.CTkScrollableFrame(self.screen, fg_color="transparent")
        self.tabs["Global Config"] = p
        def row(txt, v):
            f = EasyFrame(p); f.pack(fill="x", pady=6)
            ctk.CTkLabel(f, text=txt, font=("Inter", 14)).pack(side="left", padx=30, pady=25)
            ctk.CTkSwitch(f, text="", variable=v, progress_color=PALETTE["primary"]).pack(side="right", padx=30)
        row("Force AAC Transcoding (Windows Compatibility Layer)", self.vars["opt_aac"])
        row("Nvidia/AMD/Intel Hardware Acceleration", self.vars["opt_gpu"])
        row("SponsorBlock API Deep Packet Inspection", self.vars["opt_sponsor"])
        row("Atomic Metadata & Thumbnail Injection", self.vars["opt_thumb"])
        row("Sub-orbital Auto-Subtitle Fetching", self.vars["opt_subs"])

    def _ignite_daemons(self):
        threading.Thread(target=self._tel_loop, daemon=True).start()
        self._signal_processor()

    def _signal_processor(self):
        while not self.bus.empty():
            sig = self.bus.get()
            tid = sig['id']
            if tid in self.task_registry:
                m = self.task_registry[tid]
                if sig['type'] == 'p':
                    m['pb'].set(sig['v'] / 100)
                    m['tx'].configure(text=f"{sig['v']}% | {sig['s']} | ETA: {sig['e']}")
                elif sig['type'] == 'f':
                    m['tx'].configure(text="STATUS: COMPLETE", text_color=PALETTE["emerald"])
                    m['pb'].set(1.0)
                elif sig['type'] == 'e':
                    m['tx'].configure(text="STATUS: FATAL_ERROR", text_color=PALETTE["danger"])
        self.after(50, self._signal_processor)

    def _tel_loop(self):
        while True:
            self.telemetry_cpu.append(psutil.cpu_percent())
            self.tel_ax.clear()
            self.tel_ax.plot(list(self.telemetry_cpu), color=PALETTE["primary"], linewidth=2)
            self.tel_ax.fill_between(range(len(self.telemetry_cpu)), list(self.telemetry_cpu), color=PALETTE["primary"], alpha=0.1)
            try: self.tel_canv.draw()
            except: pass
            time.sleep(1)

    def navigate(self, n):
        if n != "Live Monitor": self.kill_preview.set()
        for k, v in self.tabs.items():
            if k == n: v.pack(fill="both", expand=True)
            else: v.pack_forget()
        for k, b in self.nav_elements.items():
            b.configure(fg_color=PALETTE["primary"] if k == n else PALETTE["bg_border"])

    def op_scan(self):
        u = self.vars["url"].get()
        if not u: return
        self.btn_run.configure(text="SCANNING KERNEL...", state="disabled")
        threading.Thread(target=self._scan_kernel, args=(u,), daemon=True).start()

    def _scan_kernel(self, u):
        try:
            with yt_dlp.YoutubeDL({'quiet': True, 'extract_flat': 'in_playlist'}) as ydl:
                meta = ydl.extract_info(u, download=False)
                if 'entries' in meta: self.after(0, lambda: self._render_playlist(meta))
                else: self.after(0, lambda: self._render_single(meta))
        except Exception as e: self.after(0, lambda: messagebox.showerror("IO_ERROR", str(e)))

    def _render_single(self, m):
        self.cache_media = m
        for w in self.res_scroll.winfo_children(): w.destroy()
        fmts = sorted([f for f in m.get('formats',[]) if f.get('height')], key=lambda x: x['height'], reverse=True)
        found = set()
        for f in fmts:
            h = f['height']
            if h not in found:
                found.add(h)
                fid = f['format_id']
                ctk.CTkRadioButton(self.res_scroll, text=f"{h}P | {f['ext'].upper()} | {f.get('vcodec','NULL')[:8]}", 
                                   variable=self.vars["target_id"], value=fid, 
                                   command=lambda res=h: self.vars["target_res"].set(str(res))).pack(anchor="w", pady=8, padx=25)
        threading.Thread(target=self._get_thumb, args=(m.get('thumbnail'),), daemon=True).start()
        self.btn_run.configure(text="EXECUTE FULL DEPLOY", state="normal")

    def _get_thumb(self, u):
        try:
            r = urllib.request.urlopen(u).read()
            i = Image.open(io.BytesIO(r)).resize((390, 220), Image.LANCZOS)
            p = ctk.CTkImage(i, size=(390, 220))
            self.after(0, lambda: self.viz_preview.configure(image=p, text=""))
        except: pass

    def op_download_full(self):
        self.navigate("Execution Queue")
        self._spawn_worker(self.cache_media['title'], self.cache_media['webpage_url'])

    def op_download_clip(self):
        if not self.cache_media: return
        self.navigate("Execution Queue")
        self._spawn_worker(f"{self.cache_media['title']}_SURGERY", self.cache_media['webpage_url'], surgical=True)

    def _spawn_worker(self, t, u, surgical=False):
        tid = str(uuid.uuid4())
        c = EasyFrame(self.q_scroll, height=110); c.pack(fill="x", pady=6, padx=20); c.pack_propagate(False)
        ctk.CTkLabel(c, text=t[:65], font=("Inter", 13, "bold")).pack(side="left", padx=30)
        p = ctk.CTkProgressBar(c, width=350, progress_color=PALETTE["primary"]); p.set(0); p.pack(side="left", padx=25)
        l = ctk.CTkLabel(c, text="HANDSHAKING...", font=("JetBrains Mono", 11)); l.pack(side="left")
        self.task_registry[tid] = {'pb': p, 'tx': l}
        threading.Thread(target=self._dl_engine, args=(tid, u, t, surgical), daemon=True).start()

    def _dl_engine(self, tid, u, t, surg):
        ext = self.vars["ext"].get()
        fid = self.vars["target_id"].get()
        
        def h(d):
            if d['status'] == 'downloading':
                try:
                    v = float(d.get('_percent_str', '0%').replace('%','').strip())
                    self.bus.put({'id': tid, 'type': 'p', 'v': v, 's': d.get('_speed_str','0B/s'), 'e': d.get('_eta_str','00:00')})
                except: pass

        # Basic Format Selection
        opts = {
            'format': f"{fid}+bestaudio/best" if fid else "bestvideo+bestaudio/best",
            'outtmpl': os.path.join(self.vars["path"].get(), "%(title)s.%(ext)s"),
            'progress_hooks': [h],
            'postprocessors': []
        }

        # --- FIX: Handle Audio Extraction (MP3/WAV) ---
        if ext in ['mp3', 'wav']:
            opts['format'] = 'bestaudio/best'
            opts['postprocessors'].append({
                'key': 'FFmpegExtractAudio',
                'preferredcodec': ext,
                'preferredquality': '192',
            })
        
        # --- FIX: Handle Video Container (MP4/MKV) ---
        elif ext in ['mp4', 'mkv']:
            opts['merge_output_format'] = ext
            if ext == 'mp4' and self.vars["opt_aac"].get():
                opts['postprocessors'].append({'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'})
                opts['postprocessor_args'] = ['-c:a', 'aac', '-b:a', '192k']

        # Temporal Clipping
        if surg:
            s_t = self._t_parse(self.vars["t_start"].get())
            e_t = self._t_parse(self.vars["t_end"].get())
            opts['download_ranges'] = lambda info, dict: [{'start_time': s_t, 'end_time': e_t}]
            opts['force_keyframes_at_cuts'] = True

        # SponsorBlock Logic
        if self.vars["opt_sponsor"].get():
            opts['postprocessors'].append({'key': 'SponsorBlock'})
            opts['postprocessors'].append({'key': 'ModifyChapters', 'remove_sponsor_segments': ['sponsor', 'intro', 'outro', 'selfpromo']})

        # Thumbnail & Metadata Logic
        if self.vars["opt_thumb"].get():
            opts['postprocessors'].append({'key': 'EmbedThumbnail'})
            opts['postprocessors'].append({'key': 'FFmpegMetadata'})

        # Subtitles
        if self.vars["opt_subs"].get():
            opts['writesubtitles'] = True
            opts['subtitleslangs'] = ['en.*']

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([u])
            self.bus.put({'id': tid, 'type': 'f'})
            self.db.log_transaction(t, u, ext, self.vars["target_res"].get(), "SUCCESS", self.vars["path"].get())
        except Exception as e:
            print(f"Error executing task: {e}")
            self.bus.put({'id': tid, 'type': 'e'})

    def _t_parse(self, ts):
        try:
            v = list(map(int, ts.split(':')))
            if len(v) == 3: return v[0]*3600 + v[1]*60 + v[2]
            return v[0]*60 + v[1]
        except: return 0

    def op_preview(self):
        if not self.cache_media: return
        self.kill_preview.clear()
        threading.Thread(target=self._prev_engine, daemon=True).start()

    def _prev_engine(self):
        u = self.cache_media['webpage_url']
        try:
            with yt_dlp.YoutubeDL({'format': 'best[height<=360]'}) as ydl:
                raw = ydl.extract_info(u, download=False)['url']
            cap = cv2.VideoCapture(raw)
            while not self.kill_preview.is_set():
                ok, f = cap.read()
                if not ok: break
                rgb = cv2.cvtColor(f, cv2.COLOR_BGR2RGB)
                im = Image.fromarray(rgb).resize((self.mon_canv.winfo_width(), self.mon_canv.winfo_height()))
                tk_im = ImageTk.PhotoImage(image=im)
                self.after(0, lambda x=tk_im: self._prev_draw(x))
                time.sleep(0.03)
            cap.release()
        except: pass

    def _prev_draw(self, x):
        self.mon_canv.create_image(0, 0, anchor="nw", image=x)
        self.mon_canv.image = x

    def _render_playlist(self, m):
        self.navigate("Playlist Engine")
        for w in self.pl_list.winfo_children(): w.destroy()
        self.cache_playlist = []
        for ent in m['entries']:
            v = tk.BooleanVar(value=True)
            r = ctk.CTkFrame(self.pl_list, fg_color="transparent"); r.pack(fill="x", pady=3)
            ctk.CTkCheckBox(r, text=ent.get('title', 'ENTRY_NULL'), variable=v, font=("Inter", 12), checkbox_color=PALETTE["primary"]).pack(side="left", padx=25)
            self.cache_playlist.append((v, ent.get('title'), ent.get('url') or ent.get('webpage_url')))

    def op_bulk(self):
        self.navigate("Execution Queue")
        for v, t, u in self.cache_playlist:
            if v.get(): self._spawn_worker(t, u)

if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    app = YTDLPEasyGUI()
    app.mainloop()
