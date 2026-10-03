# Fenix Downloader

A small portable desktop app: paste a YouTube link (one video or a whole
playlist), pick **Video (MP4)** or **Audio only (MP3)**, and click **Download**.

It is a single file with nothing to install. ffmpeg (for merging HD video and
converting to MP3) and Deno (the JavaScript runtime YouTube now requires) are
packed inside. It is built on [yt-dlp](https://github.com/yt-dlp/yt-dlp).

> Only download videos you have the right to save: your own uploads,
> Creative Commons videos, or videos whose creator allows it. YouTube's Terms
> of Service do not allow downloading other content.

## Getting the program

Download the build for your system from the **Actions** tab of this repository
(open the latest *Build Fenix Downloader* run, then **Artifacts**), or from
**Releases** if one has been published:

| System  | File                              | How to run |
|---------|-----------------------------------|------------|
| Windows | `FenixDownloader-Windows.zip`   | Unzip, double-click `FenixDownloader.exe`. If SmartScreen warns, click *More info → Run anyway*. |
| macOS   | `FenixDownloader-macOS.zip`     | Unzip, right-click `FenixDownloader.app` → *Open* the first time (the app is not signed). |
| Linux   | `FenixDownloader-Linux.tar.gz`  | `tar xzf FenixDownloader-Linux.tar.gz && ./FenixDownloader` |

It runs from anywhere, including a USB stick. It saves your last choices in
`fenix_downloader_settings.json` next to the program.

## Using it

1. Copy the link from YouTube. A playlist link (`...&list=...`) downloads
   the whole playlist into its own folder with numbered files. Untick
   *Download the whole playlist* to get only the one video.
2. Click **Paste**, choose Video or Audio and the quality, then **Download**.
3. **Cancel** stops the download. Running the same link again resumes it and
   skips everything already downloaded (tracked in `.downloaded-video.txt` /
   `.downloaded-audio.txt` in the save folder).

Files go to `Downloads/Fenix Downloader` unless you pick another folder with
**CHANGE** (a folder picker, so it shows folders only, not your files). To see
your downloads, click **OPEN FOLDER** (the latest file is selected) or click a
green path in the log.

**Age-restricted or members-only videos:** set *Use browser login* to the
browser where you are signed in to YouTube (close that browser first on Windows).

**Downloads suddenly fail for every video?** YouTube changes often and older
yt-dlp versions stop working. Get the latest build (or rebuild, below).

## Building it yourself

Requires Python 3.10+ with tkinter (the python.org installers include it).

```
cd yt-downloader
python -m pip install -r requirements.txt pyinstaller
python build.py
```

The program appears in `dist/`. PyInstaller builds only for the system it
runs on, so build on Windows to get the `.exe`. The GitHub workflow builds all
three automatically.

You can also run it straight from source with `python youtube_downloader.py`.
Run the tests with `python -m unittest test_youtube_downloader`.
