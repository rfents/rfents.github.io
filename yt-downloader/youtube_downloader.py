#!/usr/bin/env python3
"""YouTube Downloader - a small portable GUI around yt-dlp.

Paste a link to a single video or a playlist, choose video (MP4) or audio
(MP3), and click Download. Only download videos you have the right to save.
"""
from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import yt_dlp
from yt_dlp.utils import DownloadCancelled

APP_NAME = "YouTube Downloader"
QUALITIES = ["Best", "1080p", "720p", "480p", "360p"]
BROWSERS = ["None", "chrome", "firefox", "edge", "brave", "opera", "vivaldi", "safari"]

# Playlists go into a folder named after the playlist and get numbered files;
# single videos are saved directly as "<title>.<ext>".
PLAYLIST_OUTTMPL = "%(playlist_title,playlist_id|Playlist)s/%(playlist_index)s - %(title)s.%(ext)s"
SINGLE_OUTTMPL = "%(title)s.%(ext)s"


# --------------------------------------------------------------------------
# Locating bundled tools
# --------------------------------------------------------------------------

def app_dir() -> Path:
    """Folder the program lives in (next to the .exe when frozen)."""
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        # macOS .app bundles: keep settings next to the .app, not inside it
        for parent in exe.parents:
            if parent.suffix == ".app":
                return parent.parent
        return exe.parent
    return Path(__file__).resolve().parent


def bundled_bin(name: str) -> str | None:
    """Path to a helper binary packed into the frozen app by build.py."""
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        return None
    path = Path(base) / "bin" / (name + (".exe" if os.name == "nt" else ""))
    return str(path) if path.is_file() else None


def find_ffmpeg() -> str | None:
    if path := bundled_bin("ffmpeg"):
        return path
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg")


def find_deno() -> str | None:
    """Deno is the JavaScript runtime yt-dlp needs for YouTube."""
    if path := bundled_bin("deno"):
        return path
    try:
        import deno
        return deno.find_deno_bin()
    except Exception:
        return shutil.which("deno")


# --------------------------------------------------------------------------
# yt-dlp options
# --------------------------------------------------------------------------

def build_options(*, kind: str, quality: str, out_dir: str, whole_playlist: bool,
                  browser: str, ffmpeg: str | None, deno: str | None,
                  logger=None, progress_hook=None, postprocessor_hook=None,
                  post_hook=None) -> dict:
    """Translate the GUI choices into a yt-dlp options dict.

    kind is "video" or "audio"; quality is one of QUALITIES.
    """
    opts = {
        "paths": {"home": out_dir},
        "outtmpl": SINGLE_OUTTMPL,
        "noplaylist": not whole_playlist,
        "ignoreerrors": True,  # one unavailable video must not stop a playlist
        # Remembers finished items so re-running skips them (separate per mode)
        "download_archive": os.path.join(out_dir, f".downloaded-{kind}.txt"),
        "windowsfilenames": True,
        "quiet": True,
        "noprogress": True,
        "no_color": True,
        "retries": 10,
        "fragment_retries": 10,
    }
    if logger is not None:
        opts["logger"] = logger
    if progress_hook is not None:
        opts["progress_hooks"] = [progress_hook]
    if postprocessor_hook is not None:
        opts["postprocessor_hooks"] = [postprocessor_hook]
    if post_hook is not None:
        opts["post_hooks"] = [post_hook]
    if ffmpeg:
        opts["ffmpeg_location"] = ffmpeg
    if deno:
        opts["js_runtimes"] = {"deno": {"path": deno}}
    if browser and browser != "None":
        opts["cookiesfrombrowser"] = (browser,)

    height = None if quality == "Best" else int(quality.rstrip("p"))

    if kind == "audio":
        if ffmpeg:
            opts["format"] = "ba/b"
            opts["postprocessors"] = [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"},
                {"key": "FFmpegMetadata"},
            ]
        else:
            # Without ffmpeg we cannot convert; keep YouTube's own m4a audio.
            opts["format"] = "ba[ext=m4a]/ba/b"
    else:
        if ffmpeg:
            # Separate best video + audio streams, merged into one MP4.
            opts["format"] = "bv*+ba/b"
            opts["format_sort"] = ([f"res:{height}"] if height else []) + ["vcodec:h264", "ext:mp4:m4a"]
            opts["merge_output_format"] = "mp4"
        else:
            # Without ffmpeg only pre-merged files work (usually 360p).
            opts["format"] = (f"b[height<={height}][ext=mp4]/" if height else "") + "b[ext=mp4]/b"
    return opts


class Downloader(yt_dlp.YoutubeDL):
    """YoutubeDL that picks the playlist or single-video filename per item."""

    def _prepare_filename(self, info_dict, *, outtmpl=None, tmpl_type=None):
        if outtmpl is None:
            self.params["outtmpl"]["default"] = (
                PLAYLIST_OUTTMPL if info_dict.get("playlist_index") else SINGLE_OUTTMPL)
        return super()._prepare_filename(info_dict, outtmpl=outtmpl, tmpl_type=tmpl_type)


def split_urls(text: str) -> list[str]:
    return [u for u in text.split() if u.startswith(("http://", "https://", "www.", "youtu"))]


# --------------------------------------------------------------------------
# Download worker (runs in a background thread, talks to the GUI via a queue)
# --------------------------------------------------------------------------

class Worker:
    def __init__(self, urls: list[str], settings: dict, events: queue.Queue):
        self.urls = urls
        self.settings = settings
        self.events = events
        self.cancel = threading.Event()
        self.done = 0
        self.failed = 0
        self.skipped = 0

    # yt-dlp logger interface ------------------------------------------------
    def debug(self, msg):
        if msg.startswith("[debug]"):
            return
        if "has already been recorded in the archive" in msg:
            self.skipped += 1
            self.events.put(("log", "Skipped (already downloaded): " + msg.split("]", 1)[-1].strip()))
        elif msg.startswith(("[download] Downloading item", "[download] Downloading playlist",
                             "[youtube:tab] Playlist", "[Merger]", "[ExtractAudio]")):
            self.events.put(("log", msg))

    def info(self, msg):
        self.debug(msg)

    def warning(self, msg):
        # These are noisy and harmless for normal use
        if "nsig extraction" in msg or "Falling back" in msg:
            return
        self.events.put(("log", "Warning: " + msg))

    def error(self, msg):
        self.failed += 1
        self.events.put(("log", msg))

    # yt-dlp hooks ------------------------------------------------------------
    def _item_label(self, info: dict) -> str:
        title = info.get("title") or "?"
        idx, count = info.get("playlist_index"), info.get("n_entries") or info.get("playlist_count")
        return f"{idx} of {count}: {title}" if idx and count else title

    def progress_hook(self, d: dict):
        if self.cancel.is_set():
            raise DownloadCancelled("Cancelled by user")
        info = d.get("info_dict") or {}
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            pct = (d.get("downloaded_bytes", 0) / total * 100) if total else None
            self.events.put(("progress", {
                "label": self._item_label(info),
                "percent": pct,
                "speed": d.get("speed"),
                "eta": d.get("eta"),
                "index": info.get("playlist_index"),
                "count": info.get("n_entries") or info.get("playlist_count"),
            }))
        elif d["status"] == "finished":
            self.events.put(("progress", {"label": self._item_label(info), "percent": 100,
                                          "speed": None, "eta": None,
                                          "index": info.get("playlist_index"),
                                          "count": info.get("n_entries") or info.get("playlist_count")}))

    def postprocessor_hook(self, d: dict):
        if d["status"] == "started" and d["postprocessor"] in ("Merger", "ExtractAudio"):
            what = "Converting to MP3" if d["postprocessor"] == "ExtractAudio" else "Merging video and audio"
            self.events.put(("status", f"{what}…"))

    def post_hook(self, filepath: str):
        self.done += 1
        self.events.put(("log", "Saved: " + filepath))

    # -------------------------------------------------------------------------
    def run(self):
        s = self.settings
        ffmpeg, deno = find_ffmpeg(), find_deno()
        if not ffmpeg:
            self.events.put(("log", "Warning: ffmpeg not found - videos are limited to low quality "
                                    "and audio is saved as M4A instead of MP3."))
        if not deno:
            self.events.put(("log", "Warning: Deno (JavaScript runtime) not found - some YouTube "
                                    "videos may fail or only offer low quality."))
        opts = build_options(
            kind=s["kind"], quality=s["quality"], out_dir=s["out_dir"],
            whole_playlist=s["whole_playlist"], browser=s["browser"],
            ffmpeg=ffmpeg, deno=deno, logger=self, progress_hook=self.progress_hook,
            postprocessor_hook=self.postprocessor_hook, post_hook=self.post_hook)
        cancelled = False
        try:
            os.makedirs(s["out_dir"], exist_ok=True)
            with Downloader(opts) as ydl:
                for url in self.urls:
                    if self.cancel.is_set():
                        break
                    self.events.put(("status", "Fetching video information…"))
                    self.events.put(("log", "Link: " + url))
                    ydl.download([url])
        except DownloadCancelled:
            cancelled = True
        except Exception as e:  # noqa: BLE001 - show anything unexpected to the user
            self.failed += 1
            self.events.put(("log", f"Error: {e}"))
        cancelled = cancelled or self.cancel.is_set()
        self.events.put(("finished", {"done": self.done, "failed": self.failed,
                                      "skipped": self.skipped, "cancelled": cancelled}))


# --------------------------------------------------------------------------
# Settings (kept next to the program so the app stays portable)
# --------------------------------------------------------------------------

def default_out_dir() -> str:
    return str(Path.home() / "Downloads" / APP_NAME)


def settings_path() -> Path:
    portable = app_dir() / "youtube_downloader_settings.json"
    if os.access(portable.parent, os.W_OK):
        return portable
    return Path.home() / ".youtube_downloader_settings.json"


def load_settings() -> dict:
    s = {"kind": "video", "quality": "Best", "out_dir": default_out_dir(),
         "whole_playlist": True, "browser": "None"}
    try:
        s.update(json.loads(settings_path().read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return s


def save_settings(s: dict):
    try:
        settings_path().write_text(json.dumps(s, indent=2), encoding="utf-8")
    except OSError:
        pass


def open_folder(path: str):
    os.makedirs(path, exist_ok=True)
    if os.name == "nt":
        os.startfile(path)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


# --------------------------------------------------------------------------
# GUI
# --------------------------------------------------------------------------

def fmt_eta(seconds) -> str:
    if seconds is None:
        return ""
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d} left" if h else f"{m}:{s:02d} left"


def fmt_speed(bps) -> str:
    if not bps:
        return ""
    for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
        if bps < 1024:
            return f"{bps:.1f} {unit}"
        bps /= 1024
    return f"{bps:.1f} TB/s"


# Futuristic dark-blue palette
BG = "#040a18"         # window background, deep navy
PANEL = "#081430"      # cards
FIELD = "#0c1d42"      # inputs, progress troughs
BORDER = "#1a3770"
ACCENT = "#00d9ff"     # neon cyan
ACCENT_2 = "#2f6bff"   # electric blue
ACCENT_HOVER = "#6ee8ff"
TEXT = "#e4efff"
MUTED = "#7489b4"
SUCCESS = "#2cf5a8"
WARNING = "#ffc857"
ERROR = "#ff5577"
LOG_BG = "#020713"


def _blend(c1: str, c2: str, t: float) -> str:
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def _pick_font(families, candidates, fallback):
    return next((f for f in candidates if f in families), fallback)


def _dark_title_bar(root):
    """Windows 10/11: make the native title bar dark to match the theme."""
    if os.name != "nt":
        return
    try:
        import ctypes
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        value = ctypes.c_int(1)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (new, old builds)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value),
                                                           ctypes.sizeof(value)) == 0:
                break
    except Exception:  # noqa: BLE001 - purely cosmetic
        pass


class App:
    HEADER_H = 84

    def __init__(self, root):
        import tkinter as tk
        from tkinter import font as tkfont
        from tkinter import ttk

        self.tk, self.ttk = tk, ttk
        self.root = root
        self.events: queue.Queue = queue.Queue()
        self.worker: Worker | None = None
        self._state = "ready"
        self._scan = 0
        s = load_settings()

        families = set(tkfont.families(root))
        ui = _pick_font(families, ["Segoe UI", "SF Pro Text", "Helvetica Neue", "Inter",
                                   "Ubuntu", "DejaVu Sans"], "TkDefaultFont")
        mono = _pick_font(families, ["Cascadia Mono", "Consolas", "Menlo", "JetBrains Mono",
                                     "Ubuntu Mono", "DejaVu Sans Mono"], "TkFixedFont")
        self.f_ui = (ui, 10)
        self.f_small = (ui, 9)
        self.f_section = (mono, 9, "bold")
        self.f_title = (ui, 22, "bold")
        self.f_mono = (mono, 9)

        root.title(APP_NAME)
        root.configure(bg=BG)
        root.minsize(700, 720)
        root.geometry("780x830")
        self._style()
        _dark_title_bar(root)

        # ---- Header ---------------------------------------------------------
        self.header = tk.Canvas(root, height=self.HEADER_H, bg=BG, highlightthickness=0, bd=0)
        self.header.pack(fill="x")
        self.header.bind("<Configure>", lambda _e: self._draw_header())

        body = tk.Frame(root, bg=BG)
        body.pack(fill="both", expand=True, padx=18, pady=(6, 12))
        body.columnconfigure(0, weight=1)

        # ---- 01 Source ------------------------------------------------------
        src = self._card(body, "01", "SOURCE")
        src.master.grid(row=0, column=0, sticky="ew")
        src.columnconfigure(0, weight=1)
        ttk.Label(src, text="Paste a YouTube link: a single video or a whole playlist",
                  style="CardMuted.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        self.url = tk.StringVar()
        url_entry = ttk.Entry(src, textvariable=self.url, style="Neon.TEntry", font=self.f_ui)
        url_entry.grid(row=1, column=0, sticky="ew", pady=(6, 0), ipady=3)
        url_entry.bind("<Return>", lambda _e: self.start())
        url_entry.focus_set()
        ttk.Button(src, text="PASTE", style="Ghost.TButton", command=self.paste).grid(
            row=1, column=1, padx=(8, 0), pady=(6, 0))

        # ---- 02 Format ------------------------------------------------------
        fmt = self._card(body, "02", "FORMAT")
        fmt.master.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        row = ttk.Frame(fmt, style="Card.TFrame")
        row.grid(row=0, column=0, sticky="w")
        self.kind = tk.StringVar(value=s["kind"])
        ttk.Radiobutton(row, text="Video  ·  MP4", value="video", variable=self.kind,
                        style="Neon.TRadiobutton", command=self._kind_changed).pack(side="left")
        ttk.Radiobutton(row, text="Audio  ·  MP3", value="audio", variable=self.kind,
                        style="Neon.TRadiobutton", command=self._kind_changed).pack(side="left", padx=(18, 30))
        ttk.Label(row, text="QUALITY", style="CardSection.TLabel").pack(side="left")
        self.quality = tk.StringVar(value=s["quality"] if s["quality"] in QUALITIES else "Best")
        self.quality_box = ttk.Combobox(row, textvariable=self.quality, values=QUALITIES, width=8,
                                        state="readonly", style="Neon.TCombobox", font=self.f_ui)
        self.quality_box.pack(side="left", padx=(8, 0))
        self.whole_playlist = tk.BooleanVar(value=s["whole_playlist"])
        ttk.Checkbutton(fmt, text="Download the whole playlist when the link contains one",
                        variable=self.whole_playlist, style="Neon.TCheckbutton").grid(
            row=1, column=0, sticky="w", pady=(10, 0))

        # ---- 03 Output ------------------------------------------------------
        out = self._card(body, "03", "OUTPUT")
        out.master.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        out.columnconfigure(1, weight=1)
        ttk.Label(out, text="Save to", style="Card.TLabel").grid(row=0, column=0, sticky="w")
        self.out_dir = tk.StringVar(value=s["out_dir"])
        ttk.Entry(out, textvariable=self.out_dir, style="Neon.TEntry", font=self.f_ui).grid(
            row=0, column=1, sticky="ew", padx=(12, 8), ipady=2)
        ttk.Button(out, text="BROWSE", style="Ghost.TButton", command=self.browse).grid(row=0, column=2)
        ttk.Button(out, text="OPEN", style="Ghost.TButton",
                   command=lambda: open_folder(self.out_dir.get())).grid(row=0, column=3, padx=(6, 0))
        ttk.Label(out, text="Browser login", style="Card.TLabel").grid(row=1, column=0, sticky="w",
                                                                       pady=(10, 0))
        brow = ttk.Frame(out, style="Card.TFrame")
        brow.grid(row=1, column=1, columnspan=3, sticky="w", padx=(12, 0), pady=(10, 0))
        self.browser = tk.StringVar(value=s["browser"] if s["browser"] in BROWSERS else "None")
        ttk.Combobox(brow, textvariable=self.browser, values=BROWSERS, width=10, state="readonly",
                     style="Neon.TCombobox", font=self.f_ui).pack(side="left")
        ttk.Label(brow, text="only for age-restricted or members-only videos",
                  style="CardMuted.TLabel").pack(side="left", padx=(10, 0))

        # ---- Actions --------------------------------------------------------
        btns = ttk.Frame(body, style="TFrame")
        btns.grid(row=3, column=0, sticky="ew", pady=(14, 2))
        self.dl_btn = ttk.Button(btns, text="↓  DOWNLOAD", style="Accent.TButton", command=self.start)
        self.dl_btn.pack(side="left")
        self.cancel_btn = ttk.Button(btns, text="✕  CANCEL", style="Danger.TButton",
                                     command=self.cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=(10, 0))

        # ---- 04 Status ------------------------------------------------------
        st = self._card(body, "04", "STATUS")
        st.master.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        st.columnconfigure(0, weight=1)
        self.item_label = tk.StringVar(value="Ready.")
        ttk.Label(st, textvariable=self.item_label, style="Card.TLabel").grid(row=0, column=0, sticky="w")
        self.detail = tk.StringVar()
        ttk.Label(st, textvariable=self.detail, style="CardAccent.TLabel").grid(row=0, column=1, sticky="e")
        self.item_bar = ttk.Progressbar(st, maximum=100, style="Neon.Horizontal.TProgressbar")
        self.item_bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.total_label = tk.StringVar()
        ttk.Label(st, textvariable=self.total_label, style="CardMuted.TLabel").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.total_bar = ttk.Progressbar(st, maximum=100, style="Total.Horizontal.TProgressbar")
        self.total_bar.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(4, 0))

        # ---- 05 Log ---------------------------------------------------------
        lg = self._card(body, "05", "LOG")
        lg.master.grid(row=5, column=0, sticky="nsew", pady=(10, 0))
        body.rowconfigure(5, weight=1, minsize=130)
        lg.columnconfigure(0, weight=1)
        lg.rowconfigure(0, weight=1)
        self.log = tk.Text(lg, height=6, wrap="word", state="disabled", bg=LOG_BG, fg="#9cc3ff",
                           insertbackground=ACCENT, selectbackground=ACCENT_2, relief="flat",
                           bd=0, highlightthickness=1, highlightbackground=BORDER,
                           highlightcolor=BORDER, padx=10, pady=8, font=self.f_mono)
        self.log.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(lg, command=self.log.yview, style="Neon.Vertical.TScrollbar")
        scroll.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scroll.set)
        self.log.tag_configure("time", foreground=MUTED)
        self.log.tag_configure("ok", foreground=SUCCESS)
        self.log.tag_configure("warn", foreground=WARNING)
        self.log.tag_configure("err", foreground=ERROR)
        self.log.tag_configure("info", foreground=ACCENT)

        ttk.Label(body, text="Only download videos you have the right to save: your own uploads, "
                             "Creative Commons, or with the creator's permission.",
                  style="Footer.TLabel", wraplength=740).grid(row=6, column=0, sticky="w", pady=(8, 0))

        self._kind_changed()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(100, self.poll)
        root.after(40, self._animate)

    # ---- Styling -------------------------------------------------------------
    def _style(self):
        root, ttk = self.root, self.ttk
        st = ttk.Style(root)
        st.theme_use("clam")
        st.configure(".", background=BG, foreground=TEXT, fieldbackground=FIELD, bordercolor=BORDER,
                     lightcolor=BORDER, darkcolor=BORDER, troughcolor=FIELD, focuscolor=ACCENT,
                     selectbackground=ACCENT_2, selectforeground=TEXT, insertcolor=ACCENT,
                     font=self.f_ui)
        st.configure("TFrame", background=BG)
        st.configure("Card.TFrame", background=PANEL)
        st.configure("Card.TLabel", background=PANEL, foreground=TEXT, font=self.f_ui)
        st.configure("CardMuted.TLabel", background=PANEL, foreground=MUTED, font=self.f_small)
        st.configure("CardAccent.TLabel", background=PANEL, foreground=ACCENT, font=self.f_section)
        st.configure("CardSection.TLabel", background=PANEL, foreground=ACCENT, font=self.f_section)
        st.configure("Footer.TLabel", background=BG, foreground=MUTED, font=self.f_small)

        st.configure("Neon.TEntry", fieldbackground=FIELD, foreground=TEXT, insertcolor=ACCENT,
                     bordercolor=BORDER, lightcolor=FIELD, darkcolor=FIELD, padding=(8, 4))
        st.map("Neon.TEntry", bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)])

        st.configure("Ghost.TButton", background=FIELD, foreground=TEXT, bordercolor=BORDER,
                     lightcolor=FIELD, darkcolor=FIELD, padding=(14, 6), font=self.f_section)
        st.map("Ghost.TButton", background=[("pressed", BORDER), ("active", "#12285a")],
               bordercolor=[("active", ACCENT)], foreground=[("active", ACCENT)])

        st.configure("Accent.TButton", background=ACCENT, foreground=BG, bordercolor=ACCENT,
                     lightcolor=ACCENT_HOVER, darkcolor=ACCENT, padding=(30, 11),
                     font=(self.f_section[0], 11, "bold"))
        st.map("Accent.TButton",
               background=[("disabled", "#0f2752"), ("pressed", "#00b3d6"), ("active", ACCENT_HOVER)],
               foreground=[("disabled", MUTED)],
               bordercolor=[("disabled", BORDER)], lightcolor=[("disabled", "#0f2752")],
               darkcolor=[("disabled", "#0f2752")])

        st.configure("Danger.TButton", background=BG, foreground=ERROR, bordercolor=ERROR,
                     lightcolor=BG, darkcolor=BG, padding=(20, 11), font=(self.f_section[0], 11, "bold"))
        st.map("Danger.TButton", background=[("active", "#2a0f22")],
               foreground=[("disabled", "#34466e")], bordercolor=[("disabled", "#1a2b52")])

        for w in ("Neon.TRadiobutton", "Neon.TCheckbutton"):
            st.configure(w, background=PANEL, foreground=TEXT, font=self.f_ui,
                         indicatorbackground=FIELD, indicatorforeground=BG,
                         upperbordercolor=ACCENT, lowerbordercolor=ACCENT, indicatormargin=(0, 0, 8, 0))
            st.map(w, background=[("active", PANEL)], foreground=[("active", ACCENT)],
                   indicatorbackground=[("selected", ACCENT), ("active", "#12285a")])

        st.configure("Neon.TCombobox", fieldbackground=FIELD, background=FIELD, foreground=TEXT,
                     arrowcolor=ACCENT, bordercolor=BORDER, lightcolor=FIELD, darkcolor=FIELD,
                     padding=(6, 3))
        st.map("Neon.TCombobox",
               fieldbackground=[("readonly", FIELD), ("disabled", PANEL)],
               foreground=[("disabled", "#3e5280"), ("readonly", TEXT)],
               selectbackground=[("readonly", FIELD)], selectforeground=[("readonly", TEXT)],
               arrowcolor=[("disabled", "#3e5280")], bordercolor=[("focus", ACCENT), ("active", ACCENT)])
        root.option_add("*TCombobox*Listbox.background", FIELD)
        root.option_add("*TCombobox*Listbox.foreground", TEXT)
        root.option_add("*TCombobox*Listbox.selectBackground", ACCENT_2)
        root.option_add("*TCombobox*Listbox.selectForeground", TEXT)
        root.option_add("*TCombobox*Listbox.font", self.f_ui)

        st.configure("Neon.Horizontal.TProgressbar", troughcolor=FIELD, background=ACCENT,
                     bordercolor=BORDER, lightcolor=ACCENT_HOVER, darkcolor=ACCENT, thickness=12)
        st.configure("Total.Horizontal.TProgressbar", troughcolor=FIELD, background=ACCENT_2,
                     bordercolor=BORDER, lightcolor="#5b8cff", darkcolor=ACCENT_2, thickness=6)
        st.configure("Neon.Vertical.TScrollbar", background=FIELD, troughcolor=LOG_BG,
                     bordercolor=BORDER, arrowcolor=ACCENT, lightcolor=FIELD, darkcolor=FIELD)
        st.map("Neon.Vertical.TScrollbar", background=[("active", BORDER)])

    def _card(self, parent, number: str, title: str):
        """A bordered panel with a section heading; returns its inner frame."""
        tk, ttk = self.tk, self.ttk
        outer = tk.Frame(parent, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
        head = tk.Frame(outer, bg=PANEL)
        head.pack(fill="x", padx=14, pady=(8, 0))
        tk.Label(head, text=f"{number} //", bg=PANEL, fg=ACCENT_2, font=self.f_section).pack(side="left")
        tk.Label(head, text=title, bg=PANEL, fg=ACCENT, font=self.f_section).pack(side="left", padx=(6, 0))
        tk.Frame(head, bg=BORDER, height=1).pack(side="left", fill="x", expand=True, padx=(10, 0), pady=(2, 0))
        inner = ttk.Frame(outer, style="Card.TFrame")
        inner.pack(fill="both", expand=True, padx=14, pady=(6, 10))
        return inner

    # ---- Header art ------------------------------------------------------------
    def _draw_header(self):
        c = self.header
        c.delete("all")
        w, h = max(c.winfo_width(), 1), self.HEADER_H
        # faint perspective grid
        for x in range(0, w, 28):
            c.create_line(x, 0, x, h, fill="#0a1938")
        for y in range(0, h, 14):
            c.create_line(0, y, w, y, fill="#071330")
        # title
        c.create_text(22, 32, anchor="w", text="FENIX", fill=ACCENT, font=self.f_title)
        c.create_text(22 + self._text_w("FENIX ", self.f_title) + 4, 32, anchor="w", text="DOWNLOADER",
                      fill=TEXT, font=self.f_title)
        c.create_text(24, 60, anchor="w", text="VIDEO  ·  AUDIO  ·  PLAYLIST    —    POWERED BY YT-DLP",
                      fill=MUTED, font=self.f_section)
        # corner brackets
        for x0, sx in ((10, 1), (w - 10, -1)):
            c.create_line(x0, 22, x0, 12, x0 + 14 * sx, 12, fill=ACCENT_2, width=2)
            c.create_line(x0, h - 22, x0, h - 12, x0 + 14 * sx, h - 12, fill=ACCENT_2, width=2)
        # glowing gradient rule at the bottom
        steps = 60
        for i in range(steps):
            t = i / (steps - 1)
            col = _blend(ACCENT_2, ACCENT, t) if t < 0.5 else _blend(ACCENT, ACCENT_2, t)
            c.create_line(w * i / steps, h - 2, w * (i + 1) / steps + 1, h - 2, fill=col, width=2)
        self._draw_state()

    def _text_w(self, text, font):
        from tkinter import font as tkfont
        return tkfont.Font(root=self.root, font=font).measure(text)

    STATES = {"ready": ("READY", ACCENT), "busy": ("DOWNLOADING", WARNING),
              "done": ("COMPLETE", SUCCESS), "error": ("FINISHED WITH ERRORS", ERROR),
              "cancel": ("CANCELLED", MUTED)}

    def _draw_state(self):
        c = self.header
        c.delete("state")
        w = c.winfo_width()
        label, col = self.STATES[self._state]
        tw = self._text_w(label, self.f_section)
        x1, x0 = w - 30, w - 30 - tw - 34
        c.create_rectangle(x0, 22, x1, 46, outline=col, width=1, tags="state")
        r = 4 if (self._state != "busy" or (self._scan // 8) % 2 == 0) else 2
        c.create_oval(x0 + 13 - r, 34 - r, x0 + 13 + r, 34 + r, fill=col, outline=col, tags="state")
        c.create_text(x0 + 24, 34, anchor="w", text=label, fill=col, font=self.f_section, tags="state")

    def set_state(self, state: str):
        self._state = state
        self._draw_state()

    def _animate(self):
        """While downloading, sweep a light along the header rule and pulse the dot."""
        c = self.header
        c.delete("scan")
        if self._state == "busy":
            self._scan += 1
            w, h = c.winfo_width(), self.HEADER_H
            x = (self._scan * 9) % (w + 160) - 80
            for i, width in enumerate((140, 90, 44)):
                c.create_line(max(x - width / 2, 0), h - 2, min(x + width / 2, w), h - 2,
                              fill=_blend(ACCENT, "#ffffff", 0.25 * (i + 1)), width=2 + i, tags="scan")
            if self._scan % 8 == 0:
                self._draw_state()
        self.root.after(40, self._animate)

    # ------------------------------------------------------------------------
    def _kind_changed(self):
        self.quality_box.configure(state="disabled" if self.kind.get() == "audio" else "readonly")

    def paste(self):
        try:
            self.url.set(self.root.clipboard_get().strip())
        except self.tk.TclError:
            pass

    def browse(self):
        from tkinter import filedialog
        path = filedialog.askdirectory(initialdir=self.out_dir.get() or str(Path.home()))
        if path:
            self.out_dir.set(path)

    def current_settings(self) -> dict:
        return {"kind": self.kind.get(), "quality": self.quality.get(),
                "out_dir": self.out_dir.get().strip() or default_out_dir(),
                "whole_playlist": self.whole_playlist.get(), "browser": self.browser.get()}

    def write_log(self, text: str):
        import time
        if text.startswith("Saved"):
            tag = "ok"
        elif text.startswith(("ERROR", "Error")):
            tag = "err"
        elif text.startswith("Warning"):
            tag = "warn"
        elif text.startswith(("Link", "—")):
            tag = "info"
        else:
            tag = ""
        self.log.configure(state="normal")
        self.log.insert("end", time.strftime("[%H:%M:%S] "), "time")
        self.log.insert("end", text + "\n", tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    def start(self):
        from tkinter import messagebox
        if self.worker:
            return
        urls = split_urls(self.url.get())
        if not urls:
            messagebox.showinfo(APP_NAME, "Paste a YouTube video or playlist link first.")
            return
        settings = self.current_settings()
        save_settings(settings)
        self.worker = Worker(urls, settings, self.events)
        self.dl_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.item_bar["value"] = 0
        self.total_bar["value"] = 0
        self.total_label.set("")
        self.detail.set("")
        self.item_label.set("Starting…")
        self.set_state("busy")
        threading.Thread(target=self.worker.run, daemon=True).start()

    def cancel(self):
        if self.worker:
            self.worker.cancel.set()
            self.item_label.set("Cancelling…")
            self.cancel_btn.configure(state="disabled")

    def poll(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "log":
                    self.write_log(data)
                elif kind == "status":
                    self.item_label.set(data)
                    self.detail.set("")
                elif kind == "progress":
                    self.item_label.set(data["label"])
                    if data["percent"] is not None:
                        self.item_bar["value"] = data["percent"]
                    parts = [p for p in (f"{data['percent']:.0f}%" if data["percent"] is not None else "",
                                         fmt_speed(data["speed"]), fmt_eta(data["eta"])) if p]
                    self.detail.set(" · ".join(parts))
                    if data["index"] and data["count"]:
                        frac = (data["index"] - 1 + (data["percent"] or 0) / 100) / data["count"]
                        self.total_bar["value"] = frac * 100
                        self.total_label.set(f"Playlist: item {data['index']} of {data['count']}")
                elif kind == "finished":
                    self.finish(data)
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def finish(self, r: dict):
        self.worker = None
        self.dl_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")
        self.detail.set("")
        summary = f"{r['done']} downloaded"
        if r["skipped"]:
            summary += f", {r['skipped']} already downloaded"
        if r["failed"]:
            summary += f", {r['failed']} failed (see log)"
        if r["cancelled"]:
            self.item_label.set("Cancelled. " + summary + ".")
            self.set_state("cancel")
        else:
            self.set_state("error" if r["failed"] else "done")
            self.item_label.set("Finished. " + summary + ".")
            if not r["failed"]:
                self.total_bar["value"] = 100
                self.item_bar["value"] = 100
        self.write_log("— " + self.item_label.get())

    def on_close(self):
        save_settings(self.current_settings())
        if self.worker:
            self.worker.cancel.set()
        self.root.destroy()


def self_check() -> int:
    """`--check`: verify the bundled tools run. Used by the build workflow."""
    ok = True
    for name, path, args in (("ffmpeg", find_ffmpeg(), ["-version"]), ("deno", find_deno(), ["--version"])):
        try:
            out = subprocess.run([path, *args], capture_output=True, text=True, timeout=60).stdout
            print(f"{name}: {path}\n  {out.splitlines()[0]}")
        except Exception as e:  # noqa: BLE001
            ok = False
            print(f"{name}: NOT WORKING ({path}): {e}")
    print(f"yt-dlp: {yt_dlp.version.__version__}")
    return 0 if ok else 1


def main():
    # In a windowed (no console) build, stdout/stderr can be None
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")  # noqa: SIM115
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")  # noqa: SIM115
    if "--check" in sys.argv:
        sys.exit(self_check())

    import tkinter as tk
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
