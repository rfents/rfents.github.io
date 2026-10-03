"""Unit tests for the option building and filename logic (no network needed)."""
import unittest

import youtube_downloader as y


def opts(**kw):
    base = dict(kind="video", quality="Best", out_dir="out", whole_playlist=True,
                browser="None", ffmpeg="/bin/ffmpeg", deno="/bin/deno")
    base.update(kw)
    return y.build_options(**base)


class OptionTests(unittest.TestCase):
    def test_video_with_ffmpeg_merges_to_mp4(self):
        o = opts(quality="720p")
        self.assertEqual(o["format"], "bv*+ba/b")
        self.assertEqual(o["format_sort"][0], "res:720")
        self.assertEqual(o["merge_output_format"], "mp4")

    def test_video_without_ffmpeg_uses_single_file(self):
        o = opts(ffmpeg=None, quality="480p")
        self.assertTrue(o["format"].startswith("b[height<=480][ext=mp4]"))
        self.assertNotIn("merge_output_format", o)

    def test_audio_converts_to_mp3(self):
        o = opts(kind="audio")
        self.assertEqual(o["postprocessors"][0]["preferredcodec"], "mp3")

    def test_audio_without_ffmpeg_keeps_m4a(self):
        o = opts(kind="audio", ffmpeg=None)
        self.assertNotIn("postprocessors", o)

    def test_archive_is_separate_per_mode(self):
        self.assertNotEqual(opts(kind="audio")["download_archive"], opts()["download_archive"])

    def test_playlist_toggle_and_browser(self):
        self.assertTrue(opts(whole_playlist=False)["noplaylist"])
        self.assertNotIn("cookiesfrombrowser", opts())
        self.assertEqual(opts(browser="firefox")["cookiesfrombrowser"], ("firefox",))
        self.assertEqual(opts()["js_runtimes"], {"deno": {"path": "/bin/deno"}})


class FilenameTests(unittest.TestCase):
    def setUp(self):
        self.ydl = y.Downloader(opts(out_dir="/out"))
        self.info = {"title": "Song", "ext": "mp4", "id": "x"}

    def test_single_video_saved_in_folder(self):
        self.assertEqual(self.ydl.prepare_filename(dict(self.info)).replace("\\", "/"), "/out/Song.mp4")

    def test_playlist_item_goes_in_playlist_folder(self):
        name = self.ydl.prepare_filename(dict(self.info, playlist_title="Mix", playlist_index=3))
        self.assertTrue(name.replace("\\", "/").endswith("/out/Mix/3 - Song.mp4"), name)
        # and a later single video is not affected
        self.assertTrue(self.ydl.prepare_filename(dict(self.info)).replace("\\", "/").endswith("/out/Song.mp4"))


class RevealTests(unittest.TestCase):
    def test_windows_selects_file_in_explorer(self):
        import tempfile
        from unittest import mock
        with tempfile.NamedTemporaryFile(suffix=".mp4") as f, \
                mock.patch.object(y.os, "name", "nt"), \
                mock.patch.object(y.subprocess, "Popen") as popen:
            y.reveal_file(f.name)
        popen.assert_called_once_with(f'explorer /select,"{y.os.path.normpath(f.name)}"')


class HelperTests(unittest.TestCase):
    def test_split_urls(self):
        self.assertEqual(y.split_urls(" https://youtu.be/a\nfoo https://www.youtube.com/watch?v=b "),
                         ["https://youtu.be/a", "https://www.youtube.com/watch?v=b"])

    def test_formatting(self):
        self.assertEqual(y.fmt_eta(75), "1:15 left")
        self.assertEqual(y.fmt_speed(2 * 1024 * 1024), "2.0 MB/s")


if __name__ == "__main__":
    unittest.main()
