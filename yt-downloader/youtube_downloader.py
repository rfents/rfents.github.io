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


class App:
    def __init__(self, root):
        import tkinter as tk
        from tkinter import ttk

        self.tk, self.ttk = tk, ttk
        self.root = root
        self.events: queue.Queue = queue.Queue()
        self.worker: Worker | None = None
        s = load_settings()

        root.title(APP_NAME)
        root.minsize(620, 500)
        frm = ttk.Frame(root, padding=14)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text="Paste a YouTube link (video or playlist):").grid(
            row=0, column=0, columnspan=3, sticky="w")
        self.url = tk.StringVar()
        url_entry = ttk.Entry(frm, textvariable=self.url)
        url_entry.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 10))
        url_entry.bind("<Return>", lambda _e: self.start())
        url_entry.focus_set()
        ttk.Button(frm, text="Paste", command=self.paste).grid(row=1, column=2, padx=(6, 0), pady=(4, 10))

        opts = ttk.Frame(frm)
        opts.grid(row=2, column=0, columnspan=3, sticky="ew")
        self.kind = tk.StringVar(value=s["kind"])
        ttk.Radiobutton(opts, text="Video (MP4)", value="video", variable=self.kind,
                        command=self._kind_changed).pack(side="left")
        ttk.Radiobutton(opts, text="Audio only (MP3)", value="audio", variable=self.kind,
                        command=self._kind_changed).pack(side="left", padx=(12, 24))
        ttk.Label(opts, text="Quality:").pack(side="left")
        self.quality = tk.StringVar(value=s["quality"] if s["quality"] in QUALITIES else "Best")
        self.quality_box = ttk.Combobox(opts, textvariable=self.quality, values=QUALITIES,
                                        width=8, state="readonly")
        self.quality_box.pack(side="left", padx=(6, 0))

        self.whole_playlist = tk.BooleanVar(value=s["whole_playlist"])
        ttk.Checkbutton(frm, text="Download the whole playlist when the link contains one",
                        variable=self.whole_playlist).grid(row=3, column=0, columnspan=3,
                                                           sticky="w", pady=(8, 0))

        ttk.Label(frm, text="Save to:").grid(row=4, column=0, sticky="w", pady=(10, 0))
        self.out_dir = tk.StringVar(value=s["out_dir"])
        ttk.Entry(frm, textvariable=self.out_dir).grid(row=4, column=1, sticky="ew",
                                                       padx=6, pady=(10, 0))
        folder_btns = ttk.Frame(frm)
        folder_btns.grid(row=4, column=2, pady=(10, 0))
        ttk.Button(folder_btns, text="Browse…", command=self.browse).pack(side="left")
        ttk.Button(folder_btns, text="Open", command=lambda: open_folder(self.out_dir.get())
                   ).pack(side="left", padx=(4, 0))

        ttk.Label(frm, text="Use browser login:").grid(row=5, column=0, sticky="w", pady=(8, 0))
        brow = ttk.Frame(frm)
        brow.grid(row=5, column=1, columnspan=2, sticky="w", padx=6, pady=(8, 0))
        self.browser = tk.StringVar(value=s["browser"] if s["browser"] in BROWSERS else "None")
        ttk.Combobox(brow, textvariable=self.browser, values=BROWSERS, width=10,
                     state="readonly").pack(side="left")
        ttk.Label(brow, text="only needed for age-restricted or members-only videos",
                  foreground="gray").pack(side="left", padx=(8, 0))

        btns = ttk.Frame(frm)
        btns.grid(row=6, column=0, columnspan=3, sticky="w", pady=(14, 8))
        self.dl_btn = ttk.Button(btns, text="Download", command=self.start)
        self.dl_btn.pack(side="left")
        self.cancel_btn = ttk.Button(btns, text="Cancel", command=self.cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=(8, 0))

        self.item_label = tk.StringVar(value="Ready.")
        ttk.Label(frm, textvariable=self.item_label).grid(row=7, column=0, columnspan=3, sticky="w")
        self.item_bar = ttk.Progressbar(frm, maximum=100)
        self.item_bar.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        self.detail = tk.StringVar()
        ttk.Label(frm, textvariable=self.detail, foreground="gray").grid(
            row=9, column=0, columnspan=3, sticky="w")
        self.total_label = tk.StringVar()
        ttk.Label(frm, textvariable=self.total_label).grid(row=10, column=0, columnspan=3,
                                                           sticky="w", pady=(6, 0))
        self.total_bar = ttk.Progressbar(frm, maximum=100)
        self.total_bar.grid(row=11, column=0, columnspan=3, sticky="ew", pady=(4, 8))

        log_frame = ttk.Frame(frm)
        log_frame.grid(row=12, column=0, columnspan=3, sticky="nsew")
        frm.rowconfigure(12, weight=1)
        self.log = tk.Text(log_frame, height=8, wrap="word", state="disabled")
        scroll = ttk.Scrollbar(log_frame, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        ttk.Label(frm, text="Only download videos you have the right to save "
                            "(your own uploads, Creative Commons, or with the creator's permission).",
                  foreground="gray", wraplength=580).grid(row=13, column=0, columnspan=3,
                                                          sticky="w", pady=(8, 0))

        self._kind_changed()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(100, self.poll)

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
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
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
        else:
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
