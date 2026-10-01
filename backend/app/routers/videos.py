"""CRUD video: list 2 ngày qua, chi tiết/mô tả, tải về, upload, sửa, comment."""

import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response

from app.models import (
    CommentIn,
    OwnedVideoItem,
    OwnedVideosOut,
    RecentOut,
    UploadOut,
    VideoItem,
    VideoUpdateIn,
)
from app.services import store
from app.services.youtube_client import (
    get_video,
    my_uploaded_videos,
    post_comment,
    recent_videos,
    update_video,
    upload_video,
)

router = APIRouter()


def _auth_pair() -> tuple[str | None, str]:
    data = store.load_config()
    tokens = store.get_valid_tokens()
    access = (tokens or {}).get("access_token")
    return access, data.get("youtube_api_key", "")


@router.get("/videos/recent", response_model=RecentOut)
def list_recent(days: int = Query(2, ge=1, le=7)) -> RecentOut:
    data = store.load_config()
    channels = data.get("track_channel_ids", [])
    access, api_key = _auth_pair()
    try:
        items = recent_videos(access, api_key, channels, days=days)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"Lỗi YouTube API: {e}")
    return RecentOut(
        videos=[VideoItem(**v) for v in items],
        count=len(items),
        days=days,
        channels=channels,
    )


@router.get("/videos/{video_id}")
def video_detail(video_id: str) -> dict:
    access, api_key = _auth_pair()
    if not access and not api_key:
        raise HTTPException(400, "Chưa cấu hình API key và chưa login Google.")
    try:
        return get_video(access, api_key, video_id)
    except RuntimeError as e:
        raise HTTPException(404, str(e))


@router.get("/videos-mine", response_model=OwnedVideosOut)
def list_my_videos(limit: int = Query(200, ge=1, le=500)) -> OwnedVideosOut:
    tokens = store.get_valid_tokens()
    if not tokens:
        raise HTTPException(401, "Cần kết nối Google bằng tài khoản chủ kênh.")
    try:
        items = my_uploaded_videos(tokens["access_token"], limit)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"Không lấy được video của kênh: {e}")
    videos = [OwnedVideoItem(**item) for item in items]
    return OwnedVideosOut(
        videos=videos,
        count=len(videos),
        restricted_count=sum(1 for video in videos if video.restricted),
    )


@router.get("/videos/{video_id}/thumbnail")
def video_thumbnail(video_id: str):
    """Proxy ảnh thumbnail phân giải cao nhất (đính kèm khi đăng bài)."""
    import httpx
    from urllib.parse import quote

    from app.services.downloader import video_filename

    for name in ("maxresdefault", "sddefault", "hqdefault", "mqdefault"):
        try:
            r = httpx.get(
                f"https://i.ytimg.com/vi/{video_id}/{name}.jpg", timeout=20
            )
            if r.status_code == 200 and len(r.content) > 10_000:
                filename = video_filename(video_id, "jpg")
                return Response(
                    content=r.content,
                    media_type="image/jpeg",
                    headers={
                        "Content-Disposition":
                            f"attachment; filename*=UTF-8''{quote(filename)}"
                    },
                )
        except Exception:
            continue
    raise HTTPException(404, "Không lấy được thumbnail.")


@router.put("/videos/{video_id}")
def video_update(video_id: str, body: VideoUpdateIn) -> dict:
    tokens = store.get_valid_tokens()
    if not tokens:
        raise HTTPException(401, "Cần login Google (OAuth) để sửa mô tả/tiêu đề.")
    try:
        return update_video(
            tokens["access_token"],
            video_id,
            title=body.title,
            description=body.description,
            tags=body.tags,
            category_id=body.category_id,
            privacy=body.privacy,
        )
    except Exception as e:
        raise HTTPException(502, f"Cập nhật thất bại: {e}")


@router.get("/youtube/cookies/status")
def youtube_cookies_status() -> dict:
    """Kiểm tra file cookies.txt đã upload (dùng chung cho mọi lượt tải)."""
    from app.services.downloader import cookies_path

    path = cookies_path()
    try:
        if path.is_file():
            stat = path.stat()
            if stat.st_size > 0:
                return {"has_cookies": True, "size": stat.st_size, "mtime": stat.st_mtime}
    except OSError:
        pass
    return {"has_cookies": False, "size": 0, "mtime": 0}


@router.post("/youtube/cookies", status_code=201)
async def upload_youtube_cookies(file: UploadFile = File(...)) -> dict:
    """Upload file cookies.txt (Netscape) xuất từ trình duyệt đã login YouTube."""
    from app.services.downloader import cookies_path

    path = cookies_path()

    raw = await file.read()
    if not raw or len(raw) > 1024 * 1024:
        raise HTTPException(400, "File cookie rỗng hoặc quá lớn (tối đa 1MB).")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise HTTPException(400, "File cookie phải là text (cookies.txt Netscape).")
    lowered = text.lower()
    if "youtube.com" not in lowered:
        raise HTTPException(400, "File này không chứa cookie youtube.com — hãy xuất lại từ youtube.com.")
    if "netscape http cookie file" not in lowered and "#httponly" not in lowered and "\t.youtube.com" not in lowered:
        raise HTTPException(400, "File không đúng định dạng Netscape cookies.txt.")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        path.chmod(0o600)
    except OSError as e:
        raise HTTPException(500, f"Không lưu được cookie: {e}")
    return {"status": "ok", "size": len(raw)}


@router.delete("/youtube/cookies")
def delete_youtube_cookies() -> dict:
    from app.services.downloader import cookies_path

    try:
        cookies_path().unlink(missing_ok=True)
    except OSError as e:
        raise HTTPException(500, f"Không xóa được cookie: {e}")
    return {"status": "ok"}


@router.post("/videos/{video_id}/download-tasks")
def create_download_task(
    video_id: str,
    quality: str = Query("best"),
    cookies_from_browser: str = Query(""),
) -> dict:
    """Tạo tác vụ tải nền — trả ngay task_id, FE polling tiến độ (tránh proxy timeout)."""
    from app.services import download_manager as dm

    allowed_browsers = {"", "chrome", "firefox", "safari", "edge", "brave"}
    if cookies_from_browser not in allowed_browsers:
        raise HTTPException(400, "Trình duyệt cookie không được hỗ trợ.")
    return dm.create_task(video_id, quality, cookies_from_browser)


@router.get("/download-tasks")
def list_download_tasks() -> dict:
    from app.services import download_manager as dm

    return {"tasks": dm.list_tasks()}


@router.get("/download-tasks/{task_id}")
def get_download_task(task_id: str) -> dict:
    from app.services import download_manager as dm

    task = dm.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task không tồn tại.")
    return task


@router.get("/download-tasks/{task_id}/file")
def download_task_file(task_id: str) -> FileResponse:
    from app.services import download_manager as dm

    found = dm.file_for(task_id)
    if not found:
        raise HTTPException(404, "File chưa sẵn sàng (task chưa xong hoặc đã xóa).")
    path, filename = found
    return FileResponse(path, media_type="video/mp4", filename=filename)


@router.delete("/download-tasks/{task_id}")
def remove_download_task(task_id: str) -> dict:
    from app.services import download_manager as dm

    if not dm.delete_task(task_id):
        raise HTTPException(404, "Task không tồn tại.")
    return {"status": "ok"}


@router.get("/videos/{video_id}/download")
def video_download(video_id: str, quality: str = Query("best")) -> FileResponse:
    from app.services.downloader import download_video, video_filename

    try:
        path: Path = download_video(video_id, quality)
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    return FileResponse(
        path,
        media_type="video/mp4",
        filename=video_filename(video_id, path.suffix or ".mp4"),
    )


@router.post("/videos/upload", response_model=UploadOut)
def video_upload(
    file: UploadFile = File(...),
    title: str = Form(...),
    description: str = Form(""),
    privacy: str = Form("private"),
    tags: str = Form(""),
    category_id: str = Form("22"),
) -> UploadOut:
    tokens = store.get_valid_tokens()
    if not tokens:
        raise HTTPException(401, "Cần login Google (OAuth) để upload video.")
    if privacy not in ("public", "unlisted", "private"):
        raise HTTPException(400, "privacy phải là public | unlisted | private.")
    suffix = Path(file.filename or "upload.mp4").suffix or ".mp4"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(file.file.read())
        tmp.close()
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        res = upload_video(
            tokens["access_token"], tmp.name, title,
            description=description, privacy=privacy,
            tags=tag_list, category_id=category_id,
        )
    except Exception as e:
        raise HTTPException(502, f"Upload thất bại: {e}")
    finally:
        Path(tmp.name).unlink(missing_ok=True)
    return UploadOut(**res)


@router.post("/videos/{video_id}/comment")
def video_comment(video_id: str, body: CommentIn) -> dict:
    """Đăng bình luận (API không hỗ trợ tạo community post — trả message rõ ràng)."""
    tokens = store.get_valid_tokens()
    if not tokens:
        raise HTTPException(401, "Cần login Google (OAuth) để đăng.")
    if not body.text.strip():
        raise HTTPException(400, "Nội dung trống.")
    try:
        res = post_comment(tokens["access_token"], video_id, body.text.strip())
    except Exception as e:
        raise HTTPException(502, f"Đăng thất bại: {e}")
    res["note"] = (
        "YouTube Data API không hỗ trợ tạo bài đăng Cộng đồng (community post); "
        "đây là bình luận top-level trên video."
    )
    return res
