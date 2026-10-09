"""Focused offline checks: real FFmpeg cut, mocked Meta upload, config persistence."""

import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.models import FacebookFlowIn
from app.routers import analyze, config_router, facebook
from app.services import downloader, facebook_flow, store
from app.services.cancellation import Cancellation, CancelledError
from app.services.facebook_client import FacebookClient, build_blocked_comment, build_caption
from app.services.fb_assembly import (
    COVER_H,
    COVER_W,
    assemble_intro_outro,
    ensure_cover,
    make_outro_image,
)
from app.services.quiet_cut import cut_video, find_cut, probe_video, quiet_intervals, run_media


class QuietCutTests(unittest.TestCase):
    def test_parse_silence_including_trailing_interval(self):
        self.assertEqual(quiet_intervals(
            "silence_start: -0.01\nsilence_end: 0.7\nsilence_start: 2.5", 3,
        ), [(0, 0.7), (2.5, 3)])

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
    def test_real_audio_silence_cut_and_no_silence(self):
        with tempfile.TemporaryDirectory() as temp:
            source, output = Path(temp) / "source.mp4", Path(temp) / "cut.mp4"
            # A six-second tone, with a one-second silence at 2.5–3.5s.
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "color=c=blue:s=160x90:r=25:d=6",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
                "-af", "volume=0:enable='between(t,2.5,3.5)'",
                "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(source),
            ], check=True, capture_output=True, timeout=30)
            cut = find_cut(source, 3, 1, -35, 0.5)
            self.assertAlmostEqual(cut["seconds"], 3, delta=0.1)
            cut_video(source, output, cut["seconds"])
            self.assertAlmostEqual(probe_video(output)["duration"], cut["seconds"], delta=0.1)
            with self.assertRaisesRegex(RuntimeError, "Không tìm được khoảng lặng"):
                find_cut(source, 1, 0.4, -35, 0.3)
            self.assertAlmostEqual(find_cut(source, 30, 1, -35, 0.5)["seconds"], 6, delta=0.1)


class FbAssemblyTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
    def test_cover_intro_outro_roundtrip(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "color=c=teal:s=1280x720:r=30:d=10",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=10",
                "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
                str(directory / "clip.mp4"),
            ], check=True, capture_output=True, timeout=60)
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "color=c=red:s=1280x720:d=1",
                "-frames:v", "1", str(directory / "thumbnail.jpg"),
            ], check=True, capture_output=True, timeout=30)
            cover = ensure_cover(directory / "thumbnail.jpg", directory / "cover.jpg")
            with Image.open(cover) as cover_img:
                self.assertEqual(cover_img.size, (COVER_W, COVER_H))
            outro = make_outro_image(
                directory / "thumbnail.jpg", "Kênh Kiểm Tra Ỡ",
                "Tên video Phần 5 có dấu ữ",
                directory / "outro.jpg", 1280, 720,
            )
            with Image.open(outro) as outro_img:
                self.assertEqual(outro_img.size, (1280, 720))
            # Ảnh không phải nền đen trơ trụi (đã vẽ thumbnail + chữ).
            self.assertGreater(len(set(outro.read_bytes())), 100)
            steps = []
            meta = assemble_intro_outro(
                directory / "clip.mp4", directory, video_id="dQw4w9WgXcQ",
                temp_dir=directory, channel="Kênh", title="Tên video",
                thumbnail=directory / "thumbnail.jpg",
                intro_seconds=0.1, outro_seconds=5.0,
                on_step=steps.append,
            )
            self.assertFalse(meta["cover_ai"])
            self.assertTrue(steps)
            self.assertAlmostEqual(meta["duration"], 15.1, delta=0.5)
            self.assertAlmostEqual(probe_video(directory / "clip.mp4")["duration"], 15.1, delta=0.5)
            # Có ảnh bìa AI trong analyzed/ → worker dùng thay vì thumbnail upscale.
            analyzed = directory / "analyzed"
            analyzed.mkdir()
            shutil.copy(directory / "thumbnail.jpg", analyzed / "dQw4w9WgXcQ.cover.png")
            meta_ai = assemble_intro_outro(
                directory / "clip.mp4", directory, video_id="dQw4w9WgXcQ",
                temp_dir=directory, channel="Kênh", title="Tên video",
                thumbnail=directory / "thumbnail.jpg",
                intro_seconds=1.0, outro_seconds=2.0,
            )
            self.assertTrue(meta_ai["cover_ai"])
            self.assertAlmostEqual(meta_ai["duration"], 15.1 + 3.0, delta=0.6)

    def test_ensure_cover_rejects_missing_source(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(RuntimeError, "Không tìm thấy ảnh nguồn"):
                ensure_cover(Path(temp) / "missing.jpg", Path(temp) / "cover.jpg")


class FacebookClientTests(unittest.TestCase):
    def test_hashtags_preserve_description_and_deduplicate(self):
        self.assertEqual(
            build_caption("Tiêu đề video\n\nMô tả gốc #TiếngViệt", ["Tiếng Việt", "học tập", "học-tập", "!!!"],
                          title="Tiêu đề video", video_id="dQw4w9WgXcQ"),
            "Tiêu đề video\n\nXem full tại : https://www.youtube.com/watch?v=dQw4w9WgXcQ\n\n"
            "Mô tả gốc #TiếngViệt\n\n#họctập",
        )

    def test_blocked_comment_template_uses_facebook_url(self):
        self.assertEqual(
            build_blocked_comment("https://www.facebook.com/share/v/1DzU3cL7by/"),
            "Do video đã bị YT block ad phải che toàn bộ nội dung nên mng ghé phở bò của ad để xem full nha: "
            "https://www.facebook.com/share/v/1DzU3cL7by/\n"
            "Ủng hộ ad 1 like và 1 cmt giúp kênh phát triển hơn nha !!!",
        )

    def test_resumable_upload_declares_ai_before_publication_and_streams_chunks(self):
        calls = []
        def handle(request):
            body = request.read()
            calls.append((request.url.path, body))
            if b"upload_phase=start" in body:
                return httpx.Response(200, json={"video_id": "123", "upload_session_id": "session", "start_offset": "0", "end_offset": "4"})
            if b"video_file_chunk" in body:
                chunk_number = sum(b"video_file_chunk" in item[1] for item in calls)
                return httpx.Response(200, json={"start_offset": str(chunk_number * 4), "end_offset": "8"})
            return httpx.Response(200, json={"success": True})
        with tempfile.TemporaryDirectory() as temp, FacebookClient({
            "facebook_page_id": "456", "facebook_page_token": "test-token",
        }) as client:
            client.http.close()
            client.http = httpx.Client(transport=httpx.MockTransport(handle))
            path = Path(temp) / "video.mp4"
            path.write_bytes(b"abcdefgh")
            updates = []
            video_id = client.upload(path, "Title", "Description #tag", lambda **fields: updates.append(fields))
            self.assertEqual(video_id, "123")
            self.assertEqual(len(calls), 4)
            self.assertEqual(calls[-1][0], "/v25.0/456/videos")
            self.assertEqual(parse_qs(calls[-1][1].decode()), {
                "upload_phase": ["finish"], "upload_session_id": ["session"],
                "title": ["Title"], "description": ["Description #tag"],
                "published": ["false"], "is_ai_generated": ["true"],
            })
            self.assertIn(b"abcd", calls[1][1])
            self.assertIn(b"efgh", calls[2][1])
            self.assertTrue(updates[-1]["upload_finished"])
            self.assertEqual(updates[0]["facebook_video_id"], "123")

    def test_ai_declaration_rejection_does_not_finish_or_retry_without_label(self):
        finish_requests = []
        def handle(request):
            body = request.read()
            if b"upload_phase=start" in body:
                return httpx.Response(200, json={
                    "video_id": "123", "upload_session_id": "session",
                    "start_offset": "0", "end_offset": "4",
                })
            if b"video_file_chunk" in body:
                return httpx.Response(200, json={"start_offset": "4", "end_offset": "4"})
            finish_requests.append(parse_qs(body.decode()))
            return httpx.Response(400, json={"error": {
                "code": 100, "message": "Invalid parameter: is_ai_generated",
            }})
        with tempfile.TemporaryDirectory() as temp, FacebookClient({
            "facebook_page_id": "456", "facebook_page_token": "test-token",
        }) as client:
            client.http.close()
            client.http = httpx.Client(transport=httpx.MockTransport(handle))
            path = Path(temp) / "video.mp4"
            path.write_bytes(b"abcd")
            updates = []
            with self.assertRaisesRegex(RuntimeError, "is_ai_generated"):
                client.upload(path, "Title", "Description", lambda **fields: updates.append(fields))
            self.assertEqual(len(finish_requests), 1)
            self.assertEqual(finish_requests[0]["is_ai_generated"], ["true"])
            self.assertFalse(any(update.get("upload_finished") for update in updates))

    def test_page_token_mismatch_and_secret_redaction(self):
        with FacebookClient({"facebook_page_id": "456", "facebook_page_token": "sensitive"}) as client:
            client.http.close()
            client.http = httpx.Client(transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"id": "wrong-page"}),
            ))
            with self.assertRaisesRegex(RuntimeError, "đúng Page"):
                client.check_page()
            client.http.close()
            client.http = httpx.Client(transport=httpx.MockTransport(
                lambda _: httpx.Response(400, json={"error": {"code": 190, "message": "bad sensitive"}}),
            ))
            with self.assertRaisesRegex(RuntimeError, r"bad \[hidden\]"):
                client.check_page()

    def test_cancellation_after_transfer_prevents_finish_and_publish(self):
        cancel = Cancellation()
        calls = []
        def handle(request):
            body = request.read()
            calls.append(body)
            if b"upload_phase=start" in body:
                return httpx.Response(200, json={
                    "video_id": "123", "upload_session_id": "session",
                    "start_offset": "0", "end_offset": "4",
                })
            cancel.cancel()
            return httpx.Response(200, json={"start_offset": "4", "end_offset": "4"})
        with tempfile.TemporaryDirectory() as temp, FacebookClient({
            "facebook_page_id": "456", "facebook_page_token": "test-token",
        }, cancel=cancel) as client:
            client.http.close()
            client.http = httpx.Client(transport=httpx.MockTransport(handle))
            path = Path(temp) / "video.mp4"
            path.write_bytes(b"abcd")
            with self.assertRaises(CancelledError):
                client.upload(path, "Title", "Caption", lambda **_: None)
            with self.assertRaises(CancelledError):
                client.publish("123")
        self.assertEqual(len(calls), 2)
        self.assertFalse(any(b"upload_phase=finish" in body for body in calls))

    def test_cancellation_interrupts_facebook_processing_wait(self):
        cancel = Cancellation()
        with FacebookClient({"facebook_page_id": "456", "facebook_page_token": "test-token"}, cancel=cancel) as client:
            def status(_):
                cancel.cancel()
                return {"status": {"video_status": "processing"}}
            with patch.object(client, "video_status", side_effect=status) as request:
                with self.assertRaises(CancelledError):
                    client.wait_ready("123")
            self.assertEqual(request.call_count, 1)


class DownloadProgressTests(unittest.TestCase):
    def test_cancel_stops_live_download_without_waiting_for_timeout(self):
        cancel = Cancellation()
        def report(_):
            cancel.cancel()
        with self.assertRaises(CancelledError):
            facebook_flow._run_download([
                sys.executable, "-u", "-c",
                "import time; print('[download] 25.0%', flush=True); time.sleep(30)",
            ], report, timeout=5, cancel=cancel)
        self.assertFalse(cancel._processes)

    def test_cancel_stops_media_process_without_progress_output(self):
        cancel = Cancellation()
        started = threading.Event()
        original_attach = cancel.attach
        def attach(proc):
            original_attach(proc)
            started.set()
        with patch.object(cancel, "attach", side_effect=attach), ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(run_media, [sys.executable, "-c", "import time; time.sleep(30)"], 5, cancel=cancel)
            self.assertTrue(started.wait(2))
            cancel.cancel()
            with self.assertRaises(CancelledError):
                future.result(timeout=2)
        self.assertFalse(cancel._processes)

    def test_progress_is_reported_before_process_finishes(self):
        with tempfile.TemporaryDirectory() as temp:
            acknowledgement = Path(temp) / "progress-received"
            script = (
                "import pathlib, sys, time\n"
                "ack = pathlib.Path(sys.argv[1])\n"
                "print('[download] 25.5%', flush=True)\n"
                "deadline = time.monotonic() + 3\n"
                "while not ack.exists() and time.monotonic() < deadline:\n"
                "    time.sleep(0.01)\n"
                "if not ack.exists(): sys.exit(1)\n"
                "print('[download] 100.0%')\n"
                "print('[download] NA%')\n"
                "print('[download] 4.0%')\n"
                "print('[download] 101.0%')\n"
                "print('[Merger] Merging formats')\n"
            )
            updates = []
            def report(percent):
                updates.append(percent)
                acknowledgement.touch()
            facebook_flow._run_download(
                [sys.executable, "-u", "-c", script, str(acknowledgement)], report, timeout=5,
            )
            self.assertEqual(updates, [25.5, 100.0, 4.0, 100.0])

    def test_download_timeout_stops_process(self):
        with self.assertRaisesRegex(RuntimeError, "vượt quá thời gian"):
            facebook_flow._run_download(
                [sys.executable, "-c", "import time; time.sleep(30)"], lambda _: None, timeout=0.2,
            )

    def test_download_failure_retains_error_output(self):
        with self.assertRaisesRegex(RuntimeError, "ERROR: download denied"):
            facebook_flow._run_download([
                sys.executable, "-c",
                "import sys; print('ERROR: download denied', file=sys.stderr); sys.exit(1)",
            ], lambda _: None)


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        temp_path = Path(self.temp.name)
        self.settings_patch = patch.object(settings, "temp_dir", temp_path)
        self.settings_patch.start()
        self.addCleanup(self.settings_patch.stop)
        self.tasks_patch = patch.dict(facebook_flow._tasks, clear=True)
        self.tasks_patch.start()
        self.addCleanup(self.tasks_patch.stop)
        self.running_patch = patch.dict(facebook_flow._running, clear=True)
        self.running_patch.start()
        self.addCleanup(self.running_patch.stop)
        self.config_patch = patch.object(store, "CONFIG_PATH", temp_path / "config.json")
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)

    def test_partial_config_retains_other_settings_and_hides_token(self):
        store.save_config({"youtube_client_id": "client", "facebook_page_id": "456", "facebook_page_token": "secret"})
        app = FastAPI()
        app.include_router(config_router.router)
        client = TestClient(app)
        self.assertEqual(client.post("/config", json={"post_template": "New template"}).status_code, 200)
        config = store.load_config()
        self.assertEqual(config["facebook_page_token"], "secret")
        self.assertEqual(config["facebook_page_id"], "456")
        self.assertEqual(config["youtube_client_id"], "client")
        output = client.get("/config").json()
        self.assertTrue(output["has_facebook_token"])
        self.assertNotIn("facebook_page_token", output)

    def _task(self):
        task_id = "abcdef123456"
        path = settings.temp_dir / "facebook_flows" / task_id
        path.mkdir(parents=True)
        task = {"task_id": task_id, "status": "processing", "progress": 90, "created_at": 1,
                "video_id": "dQw4w9WgXcQ", "title": "Test", "page_id": "456", "api_version": "v25.0",
                "facebook_video_id": "123", "upload_finished": True, "clip_ready": False,
                "thumbnail_ready": False, "request": {}}
        facebook_flow._tasks[task_id] = task
        facebook_flow._save(task)
        return task_id

    def test_publish_orders_thumbnail_before_publish_and_confirms(self):
        task_id = self._task()
        calls = []
        class FakeFacebook:
            def wait_ready(self, _):
                return {"published": False, "status": {"video_status": "ready"}}
            def set_thumbnail(self, *_):
                calls.append("thumbnail")
            def publish(self, _):
                calls.append("publish")
            def video_status(self, _):
                calls.append("confirm")
                return {"published": True, "status": {"video_status": "ready"}, "permalink_url": "/video/123"}
        facebook_flow._complete_publish(task_id, FakeFacebook())
        self.assertEqual(calls, ["thumbnail", "publish", "confirm"])
        self.assertEqual(facebook_flow.get_task(task_id)["status"], "done")
        self.assertTrue(facebook_flow.get_task(task_id)["thumbnail_set"])
        self.assertEqual(facebook_flow.get_task(task_id)["facebook_url"], "https://www.facebook.com/video/123")

    def test_download_progress_is_exposed_and_resets_on_retry(self):
        task_id = self._task()
        directory = settings.temp_dir / "facebook_flows" / task_id
        facebook_flow._update(task_id, status="downloading", progress=5)
        app = FastAPI()
        app.include_router(facebook.router)
        client = TestClient(app)
        observed = []
        attempts = []
        def run(command, report, **_kwargs):
            attempts.append(command)
            # Each fallback starts at zero, rather than keeping the previous percentage.
            self.assertEqual(facebook_flow.get_task(task_id)["download_progress"], 0)
            percent = 62.5 if len(attempts) == 1 else 18.2
            report(percent)
            task = client.get("/facebook/flows").json()["active"][0]
            observed.append(task["download_progress"])
            self.assertIn(f"{percent:.1f}%", task["message"])
            self.assertEqual(task["progress"], 5)  # Download percentage is separate from overall flow.
            if len(attempts) == 1:
                raise RuntimeError("First player failed")
            (directory / "source.mp4").write_bytes(b"video")
        with patch.object(facebook_flow, "_run_download", side_effect=run), \
             patch.object(facebook_flow, "yt_dlp_command", return_value=[sys.executable, "-m", "yt_dlp"]):
            result = facebook_flow._download("dQw4w9WgXcQ", directory, "chrome", task_id)
        self.assertEqual(result, directory / "source.mp4")
        self.assertEqual(observed, [62.5, 18.2])
        self.assertEqual(attempts[0][:3], [sys.executable, "-m", "yt_dlp"])
        self.assertIn("--progress", attempts[0])
        self.assertIn("--newline", attempts[0])
        self.assertIn("--cookies-from-browser", attempts[0])
        self.assertIn("youtube:player_client=android", attempts[1])
        self.assertEqual(facebook_flow.get_task(task_id)["download_progress"], 100)

    def test_cancel_queued_task_keeps_history_and_never_starts(self):
        task_id = self._task()
        facebook_flow._update(task_id, status="queued")
        app = FastAPI()
        app.include_router(facebook.router)
        client = TestClient(app)
        response = client.post(f"/facebook/flows/{task_id}/cancel")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "cancelled")
        self.assertEqual(response.json()["queue_position"], 0)
        self.assertFalse(response.json()["can_resume"])
        with patch.object(facebook_flow, "FacebookClient") as facebook_client:
            facebook_flow._run(task_id, {})
        facebook_client.assert_not_called()
        self.assertTrue((facebook_flow._directory(task_id) / "task.json").is_file())
        # Cancellation stays terminal after restarting, even with an uploaded video ID.
        facebook_flow._tasks.clear()
        facebook_flow.restore_tasks()
        self.assertEqual(facebook_flow.get_task(task_id)["status"], "cancelled")

    def test_delete_queued_task_removes_files_and_pending_worker_is_noop(self):
        task_id = self._task()
        facebook_flow._update(task_id, status="queued")
        directory = facebook_flow._directory(task_id)
        (directory / "source.mp4.part").write_bytes(b"partial")
        app = FastAPI()
        app.include_router(facebook.router)
        client = TestClient(app)
        self.assertEqual(client.delete(f"/facebook/flows/{task_id}").json()["status"], "deleted")
        self.assertFalse(directory.exists())
        with patch.object(facebook_flow, "FacebookClient") as facebook_client:
            facebook_flow._run(task_id, {})
        facebook_client.assert_not_called()
        self.assertIsNone(facebook_flow.get_task(task_id))
        self.assertEqual(client.post(f"/facebook/flows/{task_id}/cancel").status_code, 404)

    def test_cancel_running_worker_defers_delete_and_continues_queue(self):
        for delete in (False, True):
            with self.subTest(delete=delete):
                task_id = self._task()
                facebook_flow._update(task_id, status="queued")
                directory = facebook_flow._directory(task_id)
                entered = threading.Event()
                release = threading.Event()
                calls = []
                class FakeFacebook:
                    def __init__(self, config, *, cancel):
                        self.cancel = cancel
                    def __enter__(self):
                        return self
                    def __exit__(self, *_):
                        pass
                    def check_page(self):
                        return {"name": "Test Page"}
                    def wait_ready(self, _):
                        entered.set()
                        # Simulate an HTTP request already in flight when cancellation arrives.
                        if not release.wait(5):
                            raise RuntimeError("Test request timed out")
                        self.cancel.check()
                    def publish(self, _):
                        calls.append("publish")
                app = FastAPI()
                app.include_router(facebook.router)
                client = TestClient(app)
                with patch.object(facebook_flow, "FacebookClient", FakeFacebook), ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(facebook_flow._run, task_id, {}, True)
                    try:
                        self.assertTrue(entered.wait(2))
                        response = (client.delete(f"/facebook/flows/{task_id}") if delete else
                                    client.post(f"/facebook/flows/{task_id}/cancel"))
                        self.assertEqual(response.status_code, 202)
                        self.assertEqual(facebook_flow.get_task(task_id)["status"], "cancelling")
                        self.assertTrue(directory.exists())
                        # Late HTTP callbacks preserve IDs without replacing the cancellation state.
                        with self.assertRaises(CancelledError):
                            facebook_flow._update(task_id, status="done", facebook_video_id="late-id")
                        self.assertEqual(facebook_flow.get_task(task_id)["facebook_video_id"], "late-id")
                    finally:
                        release.set()
                    future.result(timeout=2)
                    self.assertEqual(pool.submit(lambda: "next video").result(timeout=2), "next video")
                self.assertEqual(calls, [])
                self.assertNotIn(task_id, facebook_flow._running)
                if delete:
                    self.assertIsNone(facebook_flow.get_task(task_id))
                    self.assertFalse(directory.exists())
                else:
                    self.assertEqual(facebook_flow.get_task(task_id)["status"], "cancelled")
                    facebook_flow.delete_task(task_id)

    def test_cleanup_failure_does_not_restart_queued_task(self):
        task_id = self._task()
        facebook_flow._update(task_id, status="queued")
        with patch.object(shutil, "rmtree", side_effect=OSError("permission denied")):
            with self.assertRaisesRegex(ValueError, "Không xóa được"):
                facebook_flow.delete_task(task_id)
        task = facebook_flow.get_task(task_id)
        self.assertEqual(task["status"], "cancelled")
        self.assertFalse(task["delete_requested"])
        with patch.object(facebook_flow, "FacebookClient") as client:
            facebook_flow._run(task_id, {})
        client.assert_not_called()
        facebook_flow.delete_task(task_id)
        self.assertIsNone(facebook_flow.get_task(task_id))

    def test_cancellation_during_download_does_not_retry(self):
        task_id = self._task()
        facebook_flow._update(task_id, status="downloading")
        with patch.object(facebook_flow, "_run_download", side_effect=CancelledError) as download:
            with self.assertRaises(CancelledError):
                facebook_flow._download("dQw4w9WgXcQ", facebook_flow._directory(task_id), "", task_id)
        self.assertEqual(download.call_count, 1)

    def test_restart_completes_pending_cancel_and_delete(self):
        task_id = self._task()
        task = facebook_flow._tasks[task_id]
        task.update(status="cancelling")
        facebook_flow._save(task)
        facebook_flow._tasks.clear()
        facebook_flow.restore_tasks()
        self.assertEqual(facebook_flow.get_task(task_id)["status"], "cancelled")
        task = facebook_flow._tasks[task_id]
        task.update(status="cancelling", delete_requested=True)
        facebook_flow._save(task)
        facebook_flow._tasks.clear()
        facebook_flow.restore_tasks()
        self.assertIsNone(facebook_flow.get_task(task_id))
        self.assertFalse(facebook_flow._directory(task_id).exists())

    def test_publish_skips_thumbnail_when_already_set(self):
        task_id = self._task()
        with facebook_flow._lock:
            facebook_flow._tasks[task_id]["thumbnail_set"] = True
        calls = []
        class FakeFacebook:
            def wait_ready(self, _):
                return {"published": False, "status": {"video_status": "ready"}}
            def set_thumbnail(self, *_):
                calls.append("thumbnail")
            def publish(self, _):
                calls.append("publish")
            def video_status(self, _):
                return {"published": True, "status": {"video_status": "ready"}, "permalink_url": "/video/123"}
        facebook_flow._complete_publish(task_id, FakeFacebook())
        self.assertNotIn("thumbnail", calls)
        self.assertEqual(calls, ["publish"])

    def test_local_thumbnail_file_alone_does_not_skip_setting(self):
        # Hồi quy: file thumbnail.jpg đã tải về KHÔNG được tính là "đã đặt".
        task_id = self._task()
        (settings.temp_dir / "facebook_flows" / task_id / "thumbnail.jpg").write_bytes(b"fake-image")
        self.assertTrue(facebook_flow.get_task(task_id)["thumbnail_ready"])
        self.assertFalse(facebook_flow.get_task(task_id)["thumbnail_set"])
        calls = []
        class FakeFacebook:
            def wait_ready(self, _):
                return {"published": False, "status": {"video_status": "ready"}}
            def set_thumbnail(self, *_):
                calls.append("thumbnail")
            def publish(self, _):
                pass
            def video_status(self, _):
                return {"published": True, "status": {"video_status": "ready"}, "permalink_url": "/video/123"}
        facebook_flow._complete_publish(task_id, FakeFacebook())
        self.assertIn("thumbnail", calls)

    def test_set_task_thumbnail_backfills_published_video(self):
        store.save_config({"facebook_page_id": "456", "facebook_page_token": "secret"})
        task_id = self._task()
        (settings.temp_dir / "facebook_flows" / task_id / "thumbnail.jpg").write_bytes(b"fake-image")
        with facebook_flow._lock:
            facebook_flow._tasks[task_id]["status"] = "done"
        calls = []
        class FakeClient:
            def __init__(self, *_args, **_kwargs):
                pass
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def set_thumbnail(self, *_args):
                calls.append("thumbnail")
        with patch.object(facebook_flow, "FacebookClient", FakeClient):
            updated = facebook_flow.set_task_thumbnail(task_id)
        self.assertEqual(calls, ["thumbnail"])
        self.assertTrue(updated["thumbnail_set"])
        self.assertEqual(updated["status"], "done")

    def test_restart_preserves_id_without_automatically_republishing(self):
        task_id = self._task()
        facebook_flow._tasks.clear()
        facebook_flow.restore_tasks()
        restored = facebook_flow.get_task(task_id)
        self.assertEqual(restored["status"], "error")
        self.assertEqual(restored["facebook_video_id"], "123")
        self.assertTrue(restored["can_resume"])
        self.assertNotIn("request", restored)

    def test_finalize_full_renames_mp4_and_rejects_missing_source(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            source = directory / "source.mp4"
            source.write_bytes(b"fake-video")
            output = directory / "clip.mp4"
            with patch.object(facebook_flow, "probe_video", return_value={"duration": 123.0}):
                self.assertEqual(facebook_flow.finalize_full(source, output), 123.0)
            self.assertTrue(output.is_file())
            self.assertFalse(source.exists())
            with self.assertRaisesRegex(RuntimeError, "Không tìm thấy video"):
                facebook_flow.finalize_full(directory / "missing.mp4", output)

    def _blocked_task(self):
        import uuid as _uuid
        task_id = _uuid.uuid4().hex[:12]
        path = settings.temp_dir / "facebook_flows" / task_id
        path.mkdir(parents=True)
        task = {"task_id": task_id, "status": "done", "progress": 100, "created_at": 2,
                "video_id": "dQw4w9WgXcQ", "title": "Blocked", "page_id": "456", "api_version": "v25.0",
                "facebook_video_id": "123", "facebook_url": "https://www.facebook.com/watch/?v=123",
                "upload_finished": True, "clip_ready": True, "thumbnail_set": True,
                "comment_posted": False, "comment_id": "", "comment_error": "", "request": {}}
        facebook_flow._tasks[task_id] = task
        facebook_flow._save(task)
        return task_id

    def test_post_blocked_comment_success_and_failure_never_raise(self):
        task_id = self._blocked_task()
        posted = []
        with patch.object(store, "get_valid_tokens", return_value={"access_token": "token"}), \
             patch.object(facebook_flow, "post_comment",
                          side_effect=lambda access, video_id, text: posted.append((access, video_id, text)) or {"comment_id": "c1"}):
            facebook_flow._post_blocked_comment(task_id, "dQw4w9WgXcQ")
        self.assertEqual(len(posted), 1)
        self.assertIn("https://www.facebook.com/watch/?v=123", posted[0][2])
        task = facebook_flow.get_task(task_id)
        self.assertTrue(task["comment_posted"])
        self.assertEqual(task["comment_id"], "c1")
        self.assertEqual(task["status"], "done")

        task_id2 = self._blocked_task()
        with patch.object(store, "get_valid_tokens", return_value=None):
            facebook_flow._post_blocked_comment(task_id2, "dQw4w9WgXcQ")  # không raise
        task2 = facebook_flow.get_task(task_id2)
        self.assertFalse(task2["comment_posted"])
        self.assertIn("OAuth", task2["comment_error"])
        self.assertEqual(task2["status"], "done")

    def test_invalid_video_id_and_missing_config_fail_before_work(self):
        app = FastAPI()
        app.include_router(facebook.router)
        client = TestClient(app)
        self.assertEqual(client.post("/facebook/flows", json={"video_id": "../escape"}).status_code, 422)
        self.assertEqual(client.post("/facebook/flows", json={"video_id": "dQw4w9WgXcQ"}).status_code, 400)
        self.assertEqual(client.post("/facebook/flows/batch", json={"items": []}).status_code, 422)
        self.assertEqual(facebook_flow.list_tasks(), [])

    def test_batch_queue_positions_dedupe_and_list_split(self):
        store.save_config({"facebook_page_id": "456", "facebook_page_token": "secret"})
        bodies = [
            FacebookFlowIn(video_id="dQw4w9WgXcQ"),
            FacebookFlowIn(video_id="9bZkp7q19f0"),
            FacebookFlowIn(video_id="dQw4w9WgXcQ"),
        ]
        with patch.object(facebook_flow._pool, "submit", return_value=None), \
             patch.object(shutil, "which", side_effect=lambda tool: f"/usr/bin/{tool}"):
            result = facebook_flow.create_tasks(bodies, page_id="456")
        self.assertEqual(result["count"], 2)
        self.assertEqual(len(result["skipped"]), 1)
        self.assertEqual(sorted(t["queue_position"] for t in result["tasks"]), [1, 2])
        # Đánh dấu 1 task đã xong → endpoint tách hàng đợi / đã upload.
        done_id = result["tasks"][0]["task_id"]
        with facebook_flow._lock:
            facebook_flow._tasks[done_id]["status"] = "done"
        app = FastAPI()
        app.include_router(facebook.router)
        client = TestClient(app)
        payload = client.get("/facebook/flows").json()
        self.assertEqual(payload["active_count"], 1)
        self.assertEqual(payload["uploaded_count"], 1)
        self.assertEqual(len(payload["active"]), 1)
        self.assertEqual(len(payload["uploaded"]), 1)
        self.assertEqual(payload["uploaded"][0]["task_id"], done_id)

    def test_full_video_can_be_queued_when_yt_dlp_is_only_in_python_environment(self):
        store.save_config({"facebook_page_id": "456", "facebook_page_token": "secret"})
        with patch.object(downloader.importlib.util, "find_spec", return_value=object()), \
             patch.object(shutil, "which", side_effect=lambda tool: f"/usr/bin/{tool}" if tool in ("ffmpeg", "ffprobe") else None), \
             patch.object(facebook_flow._pool, "submit", return_value=None):
            result = facebook_flow.create_tasks([
                FacebookFlowIn(video_id="dnSSVFL-iCg", full_video=True, comment_blocked=True),
            ], page_id="456")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["skipped"], [])
        self.assertEqual(result["tasks"][0]["status"], "queued")

    def test_intro_outro_options_default_on_and_cover_artifact(self):
        body = FacebookFlowIn(video_id="dQw4w9WgXcQ")
        self.assertTrue(body.add_intro_outro)
        self.assertEqual(body.intro_seconds, 0.1)
        self.assertEqual(body.outro_seconds, 10.0)
        self.assertIn("1088", body.cover_prompt)
        task_id = self._task()
        self.assertFalse(facebook_flow.get_task(task_id)["cover_ready"])
        self.assertIsNone(facebook_flow.artifact(task_id, "cover"))
        (settings.temp_dir / "facebook_flows" / task_id / "cover.jpg").write_bytes(b"fake-cover")
        self.assertTrue(facebook_flow.get_task(task_id)["cover_ready"])
        app = FastAPI()
        app.include_router(facebook.router)
        client = TestClient(app)
        response = client.get(f"/facebook/flows/{task_id}/cover")
        self.assertEqual(response.status_code, 200)

    def test_download_names_keep_pipe_and_drop_suffix(self):
        from app.services.downloader import download_title

        self.assertEqual(download_title("A | B Phần 5"), "A ｜ B Phần 5")
        self.assertEqual(download_title('a/b\\c:d*e?f"g<h>i'), "a b c d e f g h i")
        self.assertEqual(download_title("x\r\ny"), "x y")
        task_id = self._task()
        facebook_flow._update(task_id, title="Tóm Tắt | Phim Hay Phần 5", clip_ready=True)
        directory = settings.temp_dir / "facebook_flows" / task_id
        (directory / "clip.mp4").write_bytes(b"fake-clip")
        (directory / "cover.jpg").write_bytes(b"fake-cover")
        (directory / "thumbnail.jpg").write_bytes(b"fake-thumb")
        _, clip_name = facebook_flow.artifact(task_id, "clip")
        _, cover_name = facebook_flow.artifact(task_id, "cover")
        _, thumb_name = facebook_flow.artifact(task_id, "thumbnail")
        self.assertEqual(clip_name, "Tóm Tắt ｜ Phim Hay Phần 5.mp4")
        self.assertEqual(cover_name, "Tóm Tắt ｜ Phim Hay Phần 5.jpg")
        self.assertEqual(thumb_name, "Tóm Tắt ｜ Phim Hay Phần 5_thumbnail.jpg")

    def test_retry_failed_task_clears_stale_state_and_requeues(self):
        store.save_config({"facebook_page_id": "456", "facebook_page_token": "secret"})
        task_id = self._task()
        facebook_flow._update(
            task_id, status="error", error="Tải video thất bại",
            facebook_video_id="stale-id", facebook_url="https://fb/stale",
            upload_finished=False, clip_ready=True, thumbnail_set=True,
            cut={"seconds": 1, "source_duration": 2, "reason": "cũ"},
        )
        with patch.object(facebook_flow._pool, "submit", return_value=None) as submit:
            retried = facebook_flow.retry_task(task_id)
        self.assertEqual(retried["status"], "queued")
        self.assertEqual(retried["error"], "")
        self.assertEqual(retried["facebook_video_id"], "")
        self.assertEqual(retried["facebook_url"], "")
        self.assertFalse(retried["upload_finished"])
        self.assertIsNone(facebook_flow._tasks[task_id]["cut"])
        submit.assert_called_once()
        args, _ = submit.call_args
        self.assertEqual(args[0], facebook_flow._run)
        self.assertEqual(args[1], task_id)
        self.assertEqual(len(args), 3)  # _run/task/config, không cờ resume → chạy lại toàn bộ
        # Không phải lỗi → từ chối; đang chạy → từ chối; sai Page → từ chối.
        with facebook_flow._lock:
            facebook_flow._tasks[task_id]["status"] = "done"
        with self.assertRaisesRegex(ValueError, "đang báo lỗi"):
            facebook_flow.retry_task(task_id)
        with facebook_flow._lock:
            facebook_flow._tasks[task_id]["status"] = "error"
            facebook_flow._running[task_id] = Cancellation()
        with self.assertRaisesRegex(ValueError, "đang dừng"):
            facebook_flow.retry_task(task_id)
        with facebook_flow._lock:
            del facebook_flow._running[task_id]
        store.save_config({"facebook_page_id": "999", "facebook_page_token": "secret"})
        with self.assertRaisesRegex(ValueError, "đúng Page"):
            facebook_flow.retry_task(task_id)
        with self.assertRaises(KeyError):
            facebook_flow.retry_task("000000000000")

    def test_retry_endpoint_returns_202_or_404(self):
        store.save_config({"facebook_page_id": "456", "facebook_page_token": "secret"})
        task_id = self._task()
        facebook_flow._update(task_id, status="error", error="boom", upload_finished=False)
        app = FastAPI()
        app.include_router(facebook.router)
        client = TestClient(app)
        with patch.object(facebook_flow._pool, "submit", return_value=None):
            response = client.post(f"/facebook/flows/{task_id}/retry")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "queued")
        self.assertEqual(client.post("/facebook/flows/000000000000/retry").status_code, 404)

    def test_cover_slot_is_separate_from_generated_thumbnail(self):
        from app.routers import analyze as analyze_router

        app = FastAPI()
        app.include_router(analyze_router.router)
        client = TestClient(app)
        video_id = "dQw4w9WgXcQ"
        for slot, name in (("", f"{video_id}.generated.png"), ("cover", f"{video_id}.cover.png")):
            response = client.post(
                f"/analyzed/{video_id}/generated-thumbnail" + (f"?slot={slot}" if slot else ""),
                files={"file": ("img.png", b"\x89PNG" + b"0" * 2000, "image/png")},
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertTrue((settings.temp_dir / "analyzed" / name).is_file())
        self.assertEqual(client.get(f"/analyzed/{video_id}/cover").status_code, 200)
        self.assertEqual(
            client.get("/analyzed/unknownvideoid123/cover").status_code, 404,
        )


class AnalyzeOriginTests(unittest.TestCase):
    """Entry do Facebook-flow tạo (gen cover) không được nhảy vào tab Phân tích."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        temp_path = Path(self.temp.name)
        self.settings_patch = patch.object(settings, "temp_dir", temp_path)
        self.settings_patch.start()
        self.addCleanup(self.settings_patch.stop)
        from app.routers import analyze as analyze_router

        self.analyze_router = analyze_router
        self.fetch_patch = patch.object(
            analyze_router, "_fetch_thumbnail_bytes", return_value=None,
        )
        self.fetch_patch.start()
        self.addCleanup(self.fetch_patch.stop)
        app = FastAPI()
        app.include_router(analyze_router.router)
        self.client = TestClient(app)

    def _info(self, video_id: str) -> dict:
        return {"video_id": video_id, "title": f"Title {video_id}", "channel_title": "Ch"}

    def test_facebook_origin_hidden_from_list_but_files_still_served(self):
        self.assertEqual(
            self.client.post("/analyzed", json={"info": self._info("dQw4w9WgXcQ"), "ai": None}).status_code, 200,
        )
        self.assertEqual(
            self.client.post("/analyzed", json={
                "info": self._info("9bZkp7q19f0"), "ai": None, "origin": "facebook-flow",
            }).status_code, 200,
        )
        payload = self.client.get("/analyzed").json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["videos"][0]["video_id"], "dQw4w9WgXcQ")
        # Chi tiết vẫn đọc được (worker + route ChatGPT cần file này).
        self.assertEqual(self.client.get("/analyzed/9bZkp7q19f0").status_code, 200)
        with self.assertRaises(Exception):
            self.client.post("/analyzed", json={
                "info": self._info("9bZkp7q19f0"), "ai": None, "origin": "nơi-khác",
            }).raise_for_status()

    def test_legacy_entries_inferred_from_sibling_files(self):
        directory = Path(self.temp.name) / "analyzed"
        directory.mkdir(parents=True, exist_ok=True)
        # Bản lưu cũ: chỉ có cover.png (do FB-flow gen) → ẩn.
        (directory / "a1b2c3d4e5f.json").write_text(json.dumps({
            "info": self._info("a1b2c3d4e5f"), "ai": None, "saved_at": 1,
        }), encoding="utf-8")
        (directory / "a1b2c3d4e5f.cover.png").write_bytes(b"x" * 2000)
        # Bản lưu cũ: có generated.png (tab Phân tích gen) → hiện.
        (directory / "f5e4d3c2b1a.json").write_text(json.dumps({
            "info": self._info("f5e4d3c2b1a"), "ai": None, "saved_at": 2,
        }), encoding="utf-8")
        (directory / "f5e4d3c2b1a.generated.png").write_bytes(b"x" * 2000)
        # Bản lưu cũ thuần túy → hiện như trước.
        (directory / "00112233445.json").write_text(json.dumps({
            "info": self._info("00112233445"), "ai": None, "saved_at": 3,
        }), encoding="utf-8")
        ids = [v["video_id"] for v in self.client.get("/analyzed").json()["videos"]]
        self.assertNotIn("a1b2c3d4e5f", ids)
        self.assertIn("f5e4d3c2b1a", ids)
        self.assertIn("00112233445", ids)

    def test_delete_removes_cover_file(self):
        directory = Path(self.temp.name) / "analyzed"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "dQw4w9WgXcQ.cover.png").write_bytes(b"x" * 2000)
        (directory / "dQw4w9WgXcQ.generated.png").write_bytes(b"x" * 2000)
        self.client.post("/analyzed", json={"info": self._info("dQw4w9WgXcQ"), "ai": None})
        self.assertEqual(self.client.delete("/analyzed/dQw4w9WgXcQ").status_code, 200)
        remaining = {p.name for p in directory.iterdir()}
        self.assertNotIn("dQw4w9WgXcQ.json", remaining)
        self.assertNotIn("dQw4w9WgXcQ.cover.png", remaining)
        self.assertNotIn("dQw4w9WgXcQ.generated.png", remaining)


if __name__ == "__main__":
    unittest.main()
