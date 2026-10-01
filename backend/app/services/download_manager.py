"""Tác vụ tải video chạy nền (tránh proxy/timeout khi tải file lớn).

Flow: POST tạo task → trả ngay task_id → yt-dlp chạy trong ThreadPool,
parse `%` từ stdout → FE polling GET /api/download-tasks → xong thì tải file
qua GET /api/download-tasks/{id}/file (stream từ đĩa, nhanh, không timeout).
"""

from __future__ import annotations

import re
import subprocess
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.config import settings
from app.services.downloader import (
    _challenge_solver_arg,
    _format_for,
    _js_runtime_arg,
    bot_check_hint,
    cookies_args,
    is_bot_check_error,
    video_filename,
    video_title,
    yt_dlp_command,
)

_PROGRESS_RE = re.compile(r"\[download\]\s+(\d+(?:\.\d+)?)%")
_ERROR_RE = re.compile(r"ERROR:\s*(.*)")

_PUBLIC_KEYS = (
    "task_id", "video_id", "title", "quality", "status",
    "progress", "message", "filename", "error", "size",
)

_tasks: dict[str, dict] = {}
_lock = threading.Lock()
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="dl")


def _public(t: dict) -> dict:
    return {k: t.get(k) for k in _PUBLIC_KEYS}


def _set(task_id: str, **fields) -> None:
    with _lock:
        t = _tasks.get(task_id)
        if t:
            t.update(fields)


def _cancelled(task_id: str) -> bool:
    with _lock:
        t = _tasks.get(task_id)
        return bool(t and t.get("cancel"))


def create_task(
    video_id: str,
    quality: str = "best",
    cookies_from_browser: str = "",
) -> dict:
    task_id = uuid.uuid4().hex[:12]
    title = video_title(video_id) or video_id
    with _lock:
        _tasks[task_id] = {
            "task_id": task_id,
            "video_id": video_id,
            "title": title,
            "quality": quality or "best",
            "cookies_from_browser": cookies_from_browser,
            "status": "queued",
            "progress": 0.0,
            "message": "Đang chờ tải…",
            "filename": "",
            "path": "",
            "error": "",
            "size": 0,
            "proc": None,
            "cancel": False,
        }
        # Giữ tối đa 20 task gần nhất để khỏi phình memory.
        while len(_tasks) > 20:
            oldest = next(iter(_tasks))
            if oldest == task_id:
                break
            _tasks.pop(oldest, None)
    _pool.submit(_run_task, task_id)
    with _lock:
        return _public(_tasks[task_id])


def list_tasks() -> list[dict]:
    with _lock:
        items = [_public(t) for t in _tasks.values()]
    items.reverse()  # mới nhất trước
    return items


def get_task(task_id: str) -> dict | None:
    with _lock:
        t = _tasks.get(task_id)
        return _public(t) if t else None


def file_for(task_id: str) -> tuple[Path, str] | None:
    with _lock:
        t = _tasks.get(task_id)
        if not t or t.get("status") != "done":
            return None
        p = Path(t["path"]) if t.get("path") else None
    if p and p.exists():
        return p, t.get("filename") or p.name
    return None


def delete_task(task_id: str) -> bool:
    with _lock:
        t = _tasks.get(task_id)
        if not t:
            return False
        t["cancel"] = True
        proc = t.get("proc")
    if proc and proc.poll() is None:
        try:
            proc.terminate()
        except Exception:
            pass
    # Dọn file của task (xong hoặc dở dang) để khỏi đầy đĩa.
    out_dir = settings.temp_dir / "videos"
    for f in out_dir.glob(f"dl_{task_id}.*"):
        try:
            f.unlink()
        except OSError:
            pass
    with _lock:
        t = _tasks.get(task_id)
        if t and (t.get("status") not in ("downloading", "queued") or t.get("cancel")):
            _tasks.pop(task_id, None)
        elif t:
            t["status"] = "cancelled"
            t["message"] = "Đã hủy."
    return True


def _run_task(task_id: str) -> None:
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            return
        video_id, quality = task["video_id"], task["quality"]
        cookies_from_browser = task.get("cookies_from_browser", "")
    _set(task_id, status="downloading", message="Đang tải từ YouTube…")

    try:
        command = yt_dlp_command()
    except RuntimeError as exc:
        _set(task_id, status="error", error=str(exc), message="Lỗi thiếu yt-dlp.")
        return

    out_dir = settings.temp_dir / "videos"
    out_dir.mkdir(parents=True, exist_ok=True)
    fmt = _format_for(quality)
    template = str(out_dir / f"dl_{task_id}.%(ext)s")
    url = f"https://www.youtube.com/watch?v={video_id}"
    cookie_args = cookies_args(cookies_from_browser)
    base = [
        *command,
        "--no-playlist",
        "--merge-output-format", "mp4",
        "--retries", "3",
        "--fragment-retries", "3",
        "--newline", "--progress",
        *cookie_args,
        *_js_runtime_arg(),
        *_challenge_solver_arg(),
        "-o", template,
    ]
    attempts = [
        base + ["-f", fmt, url],
        base + ["--extractor-args", "youtube:player_client=android", "-f", fmt, url],
        base + ["--extractor-args", "youtube:player_client=android", "-f", "bv*+ba/b", url],
    ]
    last_err = ""
    for i, cmd in enumerate(attempts):
        if _cancelled(task_id):
            _set(task_id, status="cancelled", message="Đã hủy.")
            return
        if i > 0:
            _set(task_id, message=f"Thử lại cấu hình {i + 1}/3…", progress=0.0)
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
        except FileNotFoundError:
            _set(task_id, status="error",
                 error="Chưa cài yt-dlp. Chạy: pip install -r backend/requirements.txt",
                 message="Lỗi thiếu yt-dlp.")
            return
        with _lock:
            if task_id in _tasks:
                _tasks[task_id]["proc"] = proc
        assert proc.stdout is not None
        for line in proc.stdout:
            m = _PROGRESS_RE.search(line)
            if m:
                try:
                    pct = min(100.0, float(m.group(1)))
                except ValueError:
                    continue
                _set(task_id, progress=pct, message=f"Đang tải… {pct:.0f}%")
            em = _ERROR_RE.search(line)
            if em:
                last_err = em.group(1).strip()[-300:]
            if _cancelled(task_id):
                try:
                    proc.terminate()
                except Exception:
                    pass
                break
        proc.wait()
        _set(task_id, proc=None)
        if _cancelled(task_id):
            _set(task_id, status="cancelled", message="Đã hủy.")
            return
        if proc.returncode == 0:
            break
    else:
        raw_err = last_err or "không rõ nguyên nhân"
        if is_bot_check_error(raw_err):
            last_err = f"{raw_err} | {bot_check_hint(cookies_from_browser)}"
        elif cookies_from_browser:
            last_err += (
                f" | Không đọc được phiên YouTube từ {cookies_from_browser}. "
                "Hãy đăng nhập YouTube trên trình duyệt đó rồi thử lại."
            )
        _set(task_id, status="error",
             error=f"Tải thất bại: {last_err or 'không rõ nguyên nhân'}",
             message="Tải thất bại.")
        return

    files = sorted(out_dir.glob(f"dl_{task_id}.*"))
    if not files:
        _set(task_id, status="error", error="yt-dlp xong nhưng không thấy file.",
             message="Tải thất bại.")
        return
    path = files[0]
    _set(
        task_id, status="done", progress=100.0,
        message="Tải xong — bấm Lưu về máy.",
        filename=video_filename(video_id, path.suffix or ".mp4"),
        path=str(path), size=path.stat().st_size,
    )
