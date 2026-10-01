"""Resolve yt-dlp from the backend interpreter without activating its venv."""

import io
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.routers import videos as videos_router
from app.services import download_manager, downloader


class YtDlpCommandTests(unittest.TestCase):
    def test_uses_current_python_without_path_lookup_when_module_is_installed(self):
        with patch.object(downloader.importlib.util, "find_spec", return_value=object()), \
             patch.object(downloader.shutil, "which", return_value=None) as which:
            self.assertEqual(downloader.yt_dlp_command(), [sys.executable, "-m", "yt_dlp"])
        which.assert_not_called()

    def test_falls_back_to_standalone_executable(self):
        with patch.object(downloader.importlib.util, "find_spec", return_value=None), \
             patch.object(downloader.shutil, "which", return_value="/opt/homebrew/bin/yt-dlp"):
            self.assertEqual(downloader.yt_dlp_command(), ["/opt/homebrew/bin/yt-dlp"])

    def test_missing_dependency_names_the_correct_python_install_command(self):
        with patch.object(downloader.importlib.util, "find_spec", return_value=None), \
             patch.object(downloader.shutil, "which", return_value=None):
            with self.assertRaises(RuntimeError) as error:
                downloader.yt_dlp_command()
        command = str(error.exception).split("Chạy: ", 1)[1]
        self.assertEqual(shlex.split(command), [
            sys.executable, "-m", "pip", "install", "-r", str(settings.base_dir / "requirements.txt"),
        ])

    def test_direct_download_launches_python_module(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(settings, "temp_dir", Path(temp)):
            output = Path(temp) / "videos" / "dQw4w9WgXcQ.mp4"
            def run(command, **_kwargs):
                self.assertEqual(command[:3], [sys.executable, "-m", "yt_dlp"])
                output.write_bytes(b"video")
                return subprocess.CompletedProcess(command, 0, "", "")
            with patch.object(downloader.importlib.util, "find_spec", return_value=object()), \
                 patch.object(downloader.shutil, "which", return_value=None), \
                 patch.object(downloader.subprocess, "run", side_effect=run):
                self.assertEqual(downloader.download_video("dQw4w9WgXcQ"), output)

    def test_background_download_launches_python_module(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(settings, "temp_dir", Path(temp)), \
             patch.dict(download_manager._tasks, {"test": {
                 "task_id": "test", "video_id": "dQw4w9WgXcQ", "quality": "best",
             }}, clear=True):
            def popen(command, **_kwargs):
                self.assertEqual(command[:3], [sys.executable, "-m", "yt_dlp"])
                (Path(temp) / "videos" / "dl_test.mp4").write_bytes(b"video")
                return Mock(stdout=iter(["[download] 100.0%\n"]), returncode=0)
            with patch.object(downloader.importlib.util, "find_spec", return_value=object()), \
                 patch.object(downloader.shutil, "which", return_value=None), \
                 patch.object(download_manager.subprocess, "Popen", side_effect=popen), \
                 patch.object(download_manager, "video_filename", return_value="video.mp4"):
                download_manager._run_task("test")
            self.assertEqual(download_manager.get_task("test")["status"], "done")


class YoutubeCookiesTests(unittest.TestCase):
    def test_cookies_file_takes_priority_over_browser(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(settings, "temp_dir", Path(temp)):
            self.assertEqual(downloader.cookies_args(""), [])
            self.assertEqual(downloader.cookies_args("chrome"), ["--cookies-from-browser", "chrome"])
            (Path(temp) / "youtube_cookies.txt").write_bytes(b"")
            self.assertEqual(downloader.cookies_args("chrome"), ["--cookies-from-browser", "chrome"])
            (Path(temp) / "youtube_cookies.txt").write_text(
                "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tabc\n",
                encoding="utf-8",
            )
            args = downloader.cookies_args("chrome")
            self.assertEqual(args, ["--cookies", str(Path(temp) / "youtube_cookies.txt")])

    def test_bot_check_error_hint_mentions_cookies_file(self):
        self.assertTrue(downloader.is_bot_check_error(
            "ERROR: [youtube] huLrdArgmqQ: Sign in to confirm you're not a bot. "
            "Use --cookies-from-browser or --cookies for the authentication."))
        self.assertFalse(downloader.is_bot_check_error("ERROR: Video unavailable"))
        with tempfile.TemporaryDirectory() as temp, patch.object(settings, "temp_dir", Path(temp)):
            self.assertIn("cookies.txt", downloader.bot_check_hint(""))
            self.assertIn("chrome", downloader.bot_check_hint("chrome"))
            (Path(temp) / "youtube_cookies.txt").write_text(
                "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tabc\n",
                encoding="utf-8",
            )
            self.assertIn("xuất lại", downloader.bot_check_hint("chrome"))

    def test_cookies_upload_status_and_delete_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(settings, "temp_dir", Path(temp)):
            app = FastAPI()
            app.include_router(videos_router.router)
            client = TestClient(app)
            self.assertFalse(client.get("/youtube/cookies/status").json()["has_cookies"])
            bad = client.post("/youtube/cookies", files={"file": ("cookies.txt", io.BytesIO(b"hello"), "text/plain")})
            self.assertEqual(bad.status_code, 400)
            good_body = (
                b"# Netscape HTTP Cookie File\n"
                b".youtube.com\tTRUE\t/\tTRUE\t0\tSID\tabc123\n"
            )
            ok = client.post("/youtube/cookies", files={"file": ("cookies.txt", io.BytesIO(good_body), "text/plain")})
            self.assertEqual(ok.status_code, 201)
            status = client.get("/youtube/cookies/status").json()
            self.assertTrue(status["has_cookies"])
            self.assertEqual(status["size"], len(good_body))
            self.assertEqual(client.delete("/youtube/cookies").status_code, 200)
            self.assertFalse(client.get("/youtube/cookies/status").json()["has_cookies"])
