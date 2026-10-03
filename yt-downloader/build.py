#!/usr/bin/env python3
"""Build a single-file portable Fenix Downloader for the current OS.

    python -m pip install -r requirements.txt pyinstaller
    python build.py

The result is in dist/: FenixDownloader.exe on Windows, FenixDownloader.app
on macOS, FenixDownloader on Linux. ffmpeg and Deno are packed inside, so
nothing else needs to be installed on the computer that runs it.
"""
import os
import shutil
import sys
from pathlib import Path

import deno
import imageio_ffmpeg
import PyInstaller.__main__

HERE = Path(__file__).resolve().parent
EXE = ".exe" if os.name == "nt" else ""


def main():
    os.chdir(HERE)
    # Stage the helper binaries under their plain names (ffmpeg, deno) so the
    # app finds them in <bundle>/bin at runtime.
    stage = HERE / "build" / "bin"
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True)
    for src, name in ((imageio_ffmpeg.get_ffmpeg_exe(), "ffmpeg"), (deno.find_deno_bin(), "deno")):
        dst = stage / (name + EXE)
        shutil.copy2(src, dst)
        dst.chmod(0o755)
        print(f"Bundling {name}: {src}")

    args = [
        "youtube_downloader.py",
        "--name", "FenixDownloader",
        # macOS: the .app bundle is already one item; one-file mode is deprecated there
        "--onedir" if sys.platform == "darwin" else "--onefile",
        "--windowed",
        "--noconfirm",
        "--clean",
        "--add-binary", f"{stage / ('ffmpeg' + EXE)}{os.pathsep}bin",
        "--add-binary", f"{stage / ('deno' + EXE)}{os.pathsep}bin",
        # FD icon: window/taskbar at runtime, and the program file itself
        "--add-data", f"{HERE / 'assets' / 'fenix.png'}{os.pathsep}assets",
        "--add-data", f"{HERE / 'assets' / 'fenix.ico'}{os.pathsep}assets",
        "--icon", str(HERE / "assets" / ("fenix.icns" if sys.platform == "darwin" else "fenix.ico")),
    ]
    if sys.platform == "darwin":
        args += ["--osx-bundle-identifier", "io.github.rfents.fenixdownloader"]
    PyInstaller.__main__.run(args)


if __name__ == "__main__":
    main()
