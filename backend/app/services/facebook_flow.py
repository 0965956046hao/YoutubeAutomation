"""Persistent single-worker YouTube → quiet cut → Facebook Page pipeline."""

import copy
import json
import re
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

import httpx

from app.config import settings
from app.models import FacebookFlowIn
from app.services import store
from app.services.cancellation import Cancellation, CancelledError, run_process
from app.services.downloader import (
    _challenge_solver_arg,
    _format_for,
    _js_runtime_arg,
    bot_check_hint,
    cookies_args,
    download_title,
    is_bot_check_error,
    yt_dlp_command,
)
from app.services.facebook_client import FacebookClient, build_blocked_comment, build_caption
from app.services.fb_assembly import assemble_intro_outro
from app.services.quiet_cut import cut_video, find_cut, probe_video, run_media
from app.services.youtube_client import get_video, post_comment

_tasks: dict[str, dict] = {}
_lock = threading.RLock()
_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="facebook-flow")
_TERMINAL = {"done", "error", "cancelled"}
_running: dict[str, Cancellation] = {}
_DOWNLOAD_PROGRESS_RE = re.compile(r"\[download\]\s+(\d+(?:\.\d+)?)%")


def _root() -> Path:
    return settings.temp_dir / "facebook_flows"


def _directory(task_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{12}", task_id):
        raise ValueError("Mã flow không hợp lệ.")
    return _root() / task_id


def _save(task: dict) -> None:
    path = _directory(task["task_id"]) / "task.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _update(task_id: str, **fields) -> None:
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            raise CancelledError("Tác vụ đã bị xóa.")
        if task["status"] in ("cancelling", "cancelled"):
            # Preserve remote IDs returned by an in-flight request, but never revive a cancelled task.
            task.update({key: value for key, value in fields.items() if key in (
                "facebook_video_id", "facebook_url", "upload_finished", "comment_id", "comment_posted",
            )})
            _save(task)
            raise CancelledError("Đã yêu cầu hủy tác vụ.")
        _tasks[task_id].update(fields, updated_at=time.time())
        _save(_tasks[task_id])


_ACTIVE_STATUSES = {"queued", "checking", "downloading", "analyzing", "cutting", "uploading", "processing", "publishing", "cancelling"}


def _queue_positions() -> dict[str, int]:
    """Vị trí trong hàng đợi (1 = đang xử lý/tiếp theo), chỉ tính task chưa xong."""
    ordered = sorted(
        (t for t in _tasks.values() if t.get("status") in _ACTIVE_STATUSES),
        key=lambda t: t.get("created_at", 0),
    )
    return {t["task_id"]: i + 1 for i, t in enumerate(ordered)}


def _public(task: dict) -> dict:
    data = copy.deepcopy(task)
    data.pop("request", None)
    data["download_progress"] = task.get("download_progress", 0.0)
    data["clip_ready"] = bool(task.get("clip_ready") and (_directory(task["task_id"]) / "clip.mp4").is_file())
    # thumbnail_ready = file ảnh đã tải về local (để UI hiển thị).
    # thumbnail_set = đã đặt ảnh bìa lên video Facebook (cờ nội bộ, chỉ True sau khi API thành công).
    data["thumbnail_ready"] = bool((_directory(task["task_id"]) / "thumbnail.jpg").is_file())
    data["thumbnail_set"] = bool(task.get("thumbnail_set"))
    data["cover_ready"] = bool((_directory(task["task_id"]) / "cover.jpg").is_file())
    data["can_resume"] = task["status"] == "error" and bool(task.get("upload_finished")) and task["task_id"] not in _running
    data["queue_position"] = _queue_positions().get(task["task_id"], 0)
    return data


def restore_tasks() -> None:
    if not _root().exists():
        return
    with _lock:
        for path in _root().glob("*/task.json"):
            try:
                task = json.loads(path.read_text(encoding="utf-8"))
                if _directory(task["task_id"]) != path.parent:
                    continue
                if task.get("delete_requested"):
                    try:
                        shutil.rmtree(path.parent)
                    except OSError:
                        task.update(status="cancelled", delete_requested=False,
                                    error="Không xóa được file local. Bấm Xóa để thử lại.", message="Đã hủy tác vụ.")
                        _save(task)
                        _tasks[task["task_id"]] = task
                    continue
                if task["status"] == "cancelling":
                    task.update(status="cancelled", error="", message="Đã hủy tác vụ.")
                    _save(task)
                if task["status"] not in _TERMINAL:
                    task.update(status="error", message="Flow bị gián đoạn do backend khởi động lại.",
                                error="Kiểm tra video Facebook đã tạo trước khi chạy lại; flow không tự đăng lại.")
                    _save(task)
                _tasks[task["task_id"]] = task
            except (ValueError, KeyError, OSError):
                continue


def list_tasks() -> list[dict]:
    with _lock:
        return [_public(t) for t in sorted(_tasks.values(), key=lambda t: t["created_at"], reverse=True)]


def get_task(task_id: str) -> dict | None:
    with _lock:
        task = _tasks.get(task_id)
        return _public(task) if task else None


def create_task(body: FacebookFlowIn) -> dict:
    config = store.load_config()
    if not config.get("facebook_page_id") or not config.get("facebook_page_token"):
        raise ValueError("Nhập Facebook Page ID và Page access token trong Cấu hình trước.")
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise ValueError(f"Chưa cài {tool} trên máy chạy backend.")
    try:
        yt_dlp_command()
    except RuntimeError as exc:
        raise ValueError(str(exc)) from exc
    with _lock:
        for existing in _tasks.values():
            if (existing["video_id"] == body.video_id and existing["page_id"] == config["facebook_page_id"]
                    and existing["status"] not in _TERMINAL):
                return _public(existing)
        task_id = uuid.uuid4().hex[:12]
        _directory(task_id).mkdir(parents=True)
        task = {
            "task_id": task_id, "video_id": body.video_id, "title": body.title or body.video_id,
            "page_id": config["facebook_page_id"], "page_name": "", "api_version": config["facebook_api_version"],
            "status": "queued", "progress": 0, "message": "Đang chờ xử lý…", "error": "",
            "download_progress": 0.0,
            "created_at": time.time(), "request": body.model_dump(),
            "facebook_video_id": "", "facebook_url": "", "upload_finished": False,
            "clip_ready": False, "thumbnail_set": False, "cut": None,
            "comment_posted": False, "comment_id": "", "comment_error": "",
        }
        _tasks[task_id] = task
        _save(task)
        _pool.submit(_run, task_id, config)
        return _public(task)


def create_tasks(bodies: list[FacebookFlowIn], page_id: str = "") -> dict:
    """Thêm nhiều video vào hàng đợi — worker đơn xử lý tuần tự từng video."""
    created: list[dict] = []
    skipped: list[dict] = []
    seen_in_batch: set[str] = set()
    for body in bodies:
        if body.video_id in seen_in_batch:
            skipped.append({"video_id": body.video_id, "reason": "Trùng trong danh sách vừa chọn."})
            continue
        seen_in_batch.add(body.video_id)
        with _lock:
            active = any(
                t["video_id"] == body.video_id and t["page_id"] == page_id
                and t["status"] not in _TERMINAL
                for t in _tasks.values()
            ) if page_id else False
        if active:
            skipped.append({"video_id": body.video_id, "reason": "Video đã có trong hàng đợi."})
            continue
        try:
            created.append(create_task(body))
        except ValueError as exc:
            skipped.append({"video_id": body.video_id, "reason": str(exc)})
    # Refresh queue_position sau khi thêm hàng loạt.
    with _lock:
        for task in created:
            task["queue_position"] = _queue_positions().get(task["task_id"], 0)
    return {"tasks": created, "skipped": skipped, "count": len(created)}


def resume_task(task_id: str) -> dict:
    config = store.load_config()
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            raise KeyError(task_id)
        if task["status"] != "error" or not task.get("upload_finished"):
            raise ValueError("Chỉ tiếp tục được flow đã upload xong Facebook và đang lỗi.")
        if task_id in _running:
            raise ValueError("Worker đang dừng, hãy chờ trước khi tiếp tục.")
        if task["page_id"] != config.get("facebook_page_id"):
            raise ValueError("Hãy cấu hình lại đúng Page của flow này trước khi tiếp tục.")
        _update(task_id, status="queued", error="", message="Đang chờ tiếp tục video đã upload…")
        _pool.submit(_run, task_id, {**config, "facebook_api_version": task["api_version"]}, True)
        return _public(task)


def retry_task(task_id: str) -> dict:
    """Chạy lại từ đầu flow đang báo lỗi (tải/cắt/ghép/upload lại toàn bộ).

    Khác resume (tiếp tục video đã upload xong): retry bỏ ID Facebook cũ,
    worker làm lại mọi bước nên không dùng bản dựng dở trước đó.
    """
    config = store.load_config()
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            raise KeyError(task_id)
        if task["status"] != "error":
            raise ValueError("Chỉ chạy lại được flow đang báo lỗi.")
        if task_id in _running:
            raise ValueError("Worker đang dừng, hãy chờ trước khi chạy lại.")
        if task["page_id"] != config.get("facebook_page_id"):
            raise ValueError("Hãy cấu hình lại đúng Page của flow này trước khi chạy lại.")
        task.update(
            status="queued", progress=0, download_progress=0.0,
            error="", message="Đang chờ chạy lại từ đầu…",
            facebook_video_id="", facebook_url="", upload_finished=False,
            clip_ready=False, thumbnail_set=False, cut=None, intro_outro=None,
            comment_posted=False, comment_id="", comment_error="",
            updated_at=time.time(),
        )
        _save(task)
        _pool.submit(_run, task_id, {**config, "facebook_api_version": task["api_version"]})
        return _public(task)


def artifact(task_id: str, name: str) -> tuple[Path, str] | None:
    task = get_task(task_id)
    if not task or name not in ("clip", "thumbnail", "cover"):
        return None
    if name == "clip" and not task["clip_ready"]:
        return None
    if name == "cover" and not task.get("cover_ready"):
        return None
    filename = {"clip": "clip.mp4", "thumbnail": "thumbnail.jpg", "cover": "cover.jpg"}[name]
    path = _directory(task_id) / filename
    if not path.is_file():
        return None
    # Tên file tải về = đúng tiêu đề video (giữ dấu |), không thêm hậu tố
    # _clip/_cover; riêng thumbnail giữ hậu tố để khỏi trùng tên cover.
    base = download_title(task["title"])
    suffix = "" if name in ("clip", "cover") else "_thumbnail"
    return path, f"{base}{suffix}{path.suffix}"


def _remove_task(task_id: str) -> None:
    directory = _directory(task_id)
    if directory.exists():
        shutil.rmtree(directory)
    del _tasks[task_id]


def cancel_task(task_id: str, *, delete: bool = False) -> dict:
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            raise KeyError(task_id)
        control = _running.get(task_id)
        if delete:
            task["delete_requested"] = True
        if control:
            task.update(status="cancelling", error="", updated_at=time.time(), message=(
                "Đang hủy, sẽ xóa file và lịch sử local khi worker dừng…" if task.get("delete_requested")
                else "Đang hủy… chờ thao tác hiện tại dừng."
            ))
            _save(task)
            control.cancel()
        elif delete:
            if task["status"] not in _TERMINAL:
                task.update(status="cancelled", message="Đã hủy tác vụ.")
            # Persist the stop before cleanup: a filesystem error must not let queued work start.
            _save(task)
            try:
                _remove_task(task_id)
            except OSError as exc:
                task.update(delete_requested=False, error="Không xóa được file local. Bấm Xóa để thử lại.")
                _save(task)
                raise ValueError(task["error"]) from exc
            return {"status": "deleted"}
        elif task["status"] not in _TERMINAL:
            task.update(status="cancelled", error="", updated_at=time.time(), message="Đã hủy tác vụ.")
            _save(task)
        return _public(task)


def delete_task(task_id: str) -> dict:
    return cancel_task(task_id, delete=True)


def _run_download(
    command: list[str], on_progress: Callable[[float], None], timeout: float = 7200,
    *, cancel: Cancellation | None = None,
) -> None:
    """Stream yt-dlp progress while retaining the download/merge time limit."""
    def on_line(line: str) -> None:
        match = _DOWNLOAD_PROGRESS_RE.search(line)
        if match:
            on_progress(min(100.0, float(match[1])))
    run_process(command, timeout, cancel=cancel, on_line=on_line)


def _download(
    video_id: str, directory: Path, browser: str, task_id: str, *, cancel: Cancellation | None = None,
) -> Path:
    fmt = _format_for("1080")
    url = f"https://www.youtube.com/watch?v={video_id}"
    base = [
        *yt_dlp_command(), "--no-playlist", "--no-warnings", "--newline", "--progress",
        "--progress-delta", "1", "--progress-template", "download:[download] %(progress._percent_str)s",
        "--merge-output-format", "mp4", "--retries", "3", "--fragment-retries", "3",
        *cookies_args(browser),
        *_js_runtime_arg(), *_challenge_solver_arg(),
        "-o", str(directory / "source.%(ext)s"),
    ]
    # Lần 1: client mặc định. Lần 2-3: ép player_client=android để né lỗi
    # "The page needs to be reloaded" / SABR của YouTube 2026.
    attempts = [
        base + ["-f", fmt, url],
        base + ["--extractor-args", "youtube:player_client=android", "-f", fmt, url],
        base + ["--extractor-args", "youtube:player_client=android", "-f", "bv*+ba/b", url],
    ]
    def report_progress(percent: float) -> None:
        message = f"Đang tải từ YouTube… {percent:.1f}%"
        if percent >= 100:
            message = "Đã tải 100% luồng hiện tại · đang hoàn tất tải / ghép video và âm thanh…"
        _update(task_id, download_progress=percent, message=message)

    last_err = ""
    for index, cmd in enumerate(attempts):
        _update(task_id, download_progress=0.0, message=(
            "Đang kết nối YouTube để tải video…" if index == 0
            else f"Thử lại cấu hình tải {index + 1}/{len(attempts)}…"
        ))
        try:
            _run_download(cmd, report_progress, cancel=cancel)
            break
        except RuntimeError as exc:
            last_err = str(exc)[-500:]
    else:
        msg = f"Tải video thất bại: {last_err}"
        if is_bot_check_error(last_err):
            msg += f" | {bot_check_hint(browser)}"
        elif not browser:
            msg += (" | Video bị chặn/bảo vệ thường cần cookie YouTube: chọn trình duyệt "
                    "đã đăng nhập YouTube ở mục Cookie rồi chạy lại.")
        raise RuntimeError(msg)
    for path in directory.glob("source.*"):
        if path.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov"):
            _update(task_id, download_progress=100.0, message="Đã tải và ghép video xong.")
            return path
    raise RuntimeError("Không tìm thấy video sau khi tải YouTube.")


def finalize_full(source: Path, output: Path, *, cancel: Cancellation | None = None) -> float:
    """Chuẩn bị file upload full: mp4 thì đổi tên, container khác thì remux nhanh.

    Trả về thời lượng (giây). Không cắt gì cả — dùng cho video bị chặn.
    """
    if cancel:
        cancel.check()
    if not source.is_file():
        raise RuntimeError("Không tìm thấy video sau khi tải YouTube.")
    if source.suffix.lower() == ".mp4":
        source.replace(output)
    else:
        run_media([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(source),
            "-map", "0:v:0", "-map", "0:a:0?", "-c", "copy",
            "-movflags", "+faststart", str(output),
        ], timeout=7200, cancel=cancel)
        try:
            source.unlink(missing_ok=True)
        except OSError:
            pass
    return probe_video(output, cancel=cancel)["duration"]


def _post_blocked_comment(task_id: str, video_id: str, *, cancel: Cancellation | None = None) -> None:
    """Đăng comment kèm link Facebook lên video YouTube bị chặn.

    Không bao giờ raise: comment lỗi thì ghi lại, flow vẫn giữ done.
    Ghim comment phải làm tay trong Studio (Data API không hỗ trợ ghim).
    """
    try:
        with _lock:
            task = _tasks.get(task_id)
            facebook_url = (task or {}).get("facebook_url", "")
        tokens = store.get_valid_tokens()
        if not tokens:
            raise RuntimeError("Chưa kết nối Google (OAuth) nên không đăng được comment.")
        text = build_blocked_comment(facebook_url)
        if not text:
            raise RuntimeError("Thiếu link bài Facebook nên không đăng comment.")
        if cancel:
            cancel.check()
        result = post_comment(tokens["access_token"], video_id, text)
        _update(task_id, comment_posted=True, comment_id=result.get("comment_id", ""), comment_error="",
                message="Đã đăng video + comment link Facebook. Mở Studio để ghim comment.")
    except CancelledError:
        raise
    except Exception as exc:
        _update(task_id, comment_posted=False,
                comment_error=f"Đăng comment thất bại: {exc}"[:500],
                message="Đã đăng video, nhưng đăng comment thất bại — đăng tay trong Studio.")


def _thumbnail(video_id: str, directory: Path, *, cancel: Cancellation | None = None) -> None:
    with httpx.Client(timeout=30) as client:
        for name in ("maxresdefault", "sddefault", "hqdefault", "mqdefault"):
            if cancel:
                cancel.check()
            response = client.get(f"https://i.ytimg.com/vi/{video_id}/{name}.jpg")
            if response.status_code == 200 and response.headers.get("content-type", "").startswith("image/") and len(response.content) > 1000:
                (directory / "thumbnail.jpg").write_bytes(response.content)
                return
    raise RuntimeError("Không tải được thumbnail gốc từ YouTube.")


def set_task_thumbnail(task_id: str) -> dict:
    """Đặt thumbnail YouTube đã tải về làm ảnh bìa video Facebook.

    Dùng cho flow mới (trước khi publish) và đặt bù cho video đã đăng xong.
    Chỉ đánh dấu thumbnail_set sau khi API thành công.
    """
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            raise KeyError(task_id)
        if task["status"] not in ("done", "error") or task_id in _running:
            raise ValueError("Chỉ đặt lại ảnh bìa khi flow đã dừng hoặc đăng xong.")
        video_id = task.get("facebook_video_id", "")
        page_id = task.get("page_id", "")
        api_version = task.get("api_version", "v25.0")
    if not video_id:
        raise ValueError("Flow chưa upload video lên Facebook nên chưa đặt được ảnh bìa.")
    thumb = _directory(task_id) / "thumbnail.jpg"
    if not thumb.is_file():
        raise ValueError("Không còn file thumbnail local của flow này.")
    config = store.load_config()
    if config.get("facebook_page_id") != page_id:
        raise ValueError("Hãy cấu hình lại đúng Page của flow này trước.")
    with FacebookClient({**config, "facebook_api_version": api_version}) as facebook:
        facebook.set_thumbnail(video_id, thumb)
    _update(task_id, thumbnail_set=True)
    with _lock:
        return _public(_tasks[task_id])


def _complete_publish(task_id: str, facebook: FacebookClient, *, cancel: Cancellation | None = None) -> None:
    cancel = cancel or Cancellation()
    cancel.check()
    task = get_task(task_id)
    video_id = task["facebook_video_id"]
    _update(task_id, status="processing", progress=90, message="Đợi Facebook xử lý video…")
    data = facebook.wait_ready(video_id)
    if not data.get("published"):
        if not task.get("thumbnail_set"):
            _update(task_id, message="Đang đặt thumbnail gốc cho video…", progress=94)
            facebook.set_thumbnail(video_id, _directory(task_id) / "thumbnail.jpg")
            _update(task_id, thumbnail_set=True)
        _update(task_id, status="publishing", progress=97, message="Đang xuất bản lên Facebook Page…")
        facebook.publish(video_id)
        # Success acknowledgement is not proof of publication; check the object.
        for _ in range(12):
            data = facebook.video_status(video_id)
            if data.get("published") and data.get("status", {}).get("video_status") == "ready":
                break
            cancel.wait(5)
        else:
            raise RuntimeError("Đã gửi yêu cầu đăng nhưng Facebook chưa xác nhận. Bấm Tiếp tục để kiểm tra cùng video này.")
    url = data.get("permalink_url") or f"https://www.facebook.com/watch/?v={video_id}"
    if url.startswith("/"):
        url = "https://www.facebook.com" + url
    _update(task_id, status="done", progress=100, error="", message="Đã đăng video lên Facebook Page.", facebook_url=url)


def _run(task_id: str, config: dict, resume: bool = False) -> None:
    with _lock:
        task = _tasks.get(task_id)
        if not task or task["status"] != "queued" or task_id in _running:
            return
        cancel = Cancellation()
        _running[task_id] = cancel
    try:
        with FacebookClient(config, cancel=cancel) as facebook:
            _update(task_id, status="checking", progress=2, message="Kiểm tra Facebook Page…")
            page = facebook.check_page()
            _update(task_id, page_name=page.get("name", ""))
            if resume:
                _complete_publish(task_id, facebook, cancel=cancel)
                return
            with _lock:
                body = FacebookFlowIn(**_tasks[task_id]["request"])
            directory = _directory(task_id)
            tokens = store.get_valid_tokens()
            cancel.check()
            info = get_video((tokens or {}).get("access_token"), config.get("youtube_api_key", ""), body.video_id)
            title = body.title if body.title is not None else info["title"][:255]
            description = body.description if body.description is not None else info.get("description", "")
            tags = body.tags if body.tags is not None else info.get("tags", [])
            caption = build_caption(description, tags, title=title, video_id=body.video_id)
            _update(task_id, title=title, description=caption, tags=tags,
                    status="downloading", progress=5, message="Đang tải video và thumbnail từ YouTube…")
            _thumbnail(body.video_id, directory, cancel=cancel)
            source = _download(body.video_id, directory, body.cookies_from_browser, task_id, cancel=cancel)
            output = directory / "clip.mp4"
            if body.full_video:
                # Video bị chặn: upload toàn bộ, bỏ qua tìm khoảng lặng + cắt.
                _update(task_id, status="cutting", progress=50, message="Video bị chặn: giữ nguyên full, không cắt…")
                duration = finalize_full(source, output, cancel=cancel)
                cut = {"seconds": duration, "source_duration": duration,
                       "reason": "Upload full video (video bị chặn, không cắt)."}
                _update(task_id, cut=cut)
            else:
                _update(task_id, status="analyzing", progress=40, message="Đang tìm khoảng lặng quanh mốc cắt…")
                cut = find_cut(source, body.target_minutes * 60, body.search_window, body.silence_db, body.silence_duration, cancel=cancel)
                _update(task_id, cut=cut, status="cutting", progress=50, message=f"Đang cắt tại {cut['seconds'] / 60:.2f} phút…")
                cut_video(source, output, cut["seconds"], cancel=cancel)
                # Cắt xong thì xóa video gốc YouTube cho nhẹ đĩa (giữ clip + thumbnail).
                try:
                    source.unlink(missing_ok=True)
                except OSError:
                    pass
            if body.add_intro_outro:
                # Sau khi cắt: chuẩn hoá cover 1088×1446 (ưu tiên ảnh ChatGPT
                # đã gen cho video), chèn vào đầu (giữ tỉ lệ + căn giữa) và
                # thêm outro template YT ở cuối. Không có cover AI thì dùng
                # thumbnail gốc upscale để không kẹt hàng đợi.
                _update(task_id, status="cutting", progress=58,
                        message="Đang chuẩn hoá cover 1088×1446 + ghép intro/outro…")
                meta = assemble_intro_outro(
                    output, directory, video_id=body.video_id, temp_dir=settings.temp_dir,
                    channel=info.get("channel_title", ""), title=title,
                    thumbnail=directory / "thumbnail.jpg",
                    intro_seconds=body.intro_seconds, outro_seconds=body.outro_seconds,
                    cancel=cancel,
                    on_step=lambda message: _update(task_id, message=message),
                )
                extra = (f" + intro cover {meta['intro_seconds']:g}s & outro YT {meta['outro_seconds']:g}s"
                         f" ({'ảnh bìa ChatGPT' if meta['cover_ai'] else 'cover từ thumbnail gốc'}).")
                cut = {**cut, "reason": cut.get("reason", "") + extra}
                _update(task_id, cut=cut, intro_outro=meta)
            _update(task_id, clip_ready=True, status="uploading", progress=75, message="Đang upload video đã cắt lên Facebook…")
            facebook.upload(output, title, caption, lambda **fields: _update(task_id, **fields))
            _complete_publish(task_id, facebook, cancel=cancel)
            if body.comment_blocked and get_task(task_id)["status"] == "done":
                _post_blocked_comment(task_id, body.video_id, cancel=cancel)
    except CancelledError:
        pass
    except Exception as exc:
        message = str(exc)
        for secret in (config.get("facebook_page_token"), config.get("youtube_api_key")):
            if secret:
                message = message.replace(secret, "[hidden]")
        with _lock:
            if not cancel.event.is_set():
                _update(task_id, status="error", error=message[:2000], message="Flow dừng do lỗi.")
    finally:
        with _lock:
            _running.pop(task_id, None)
            task = _tasks.get(task_id)
            if task and cancel.event.is_set():
                task.update(status="cancelled", error="", updated_at=time.time(), message="Đã hủy tác vụ.")
                _save(task)
                if task.get("delete_requested"):
                    try:
                        _remove_task(task_id)
                    except OSError:
                        task.update(delete_requested=False, error="Không xóa được file local. Bấm Xóa để thử lại.")
                        _save(task)
