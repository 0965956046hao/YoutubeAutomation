"""Facebook Page long-video upload (resumable), cover image and publication.

Uses /{page}/videos for 30-minute content. Reel presentation depends on Meta's
unified video rollout; the legacy /video_reels endpoint has separate limits.
"""

import re
import tempfile
import time
import unicodedata
from pathlib import Path
from typing import Callable

import httpx


BLOCKED_COMMENT_TEMPLATE = (
    "Do video đã bị YT block ad phải che toàn bộ nội dung nên mng ghé phở bò của ad để xem full nha: {facebook_url}\n"
    "Ủng hộ ad 1 like và 1 cmt giúp kênh phát triển hơn nha !!!"
)


def build_blocked_comment(facebook_url: str) -> str:
    """Nội dung comment đăng lên video YouTube bị chặn, kèm link bài Facebook."""
    return BLOCKED_COMMENT_TEMPLATE.format(facebook_url=(facebook_url or "").strip())


def build_caption(description: str, tags: list[str], *, title: str, video_id: str) -> str:
    body = description.strip()
    while body and body.partition("\n")[0].strip() == title.strip():
        body = body.partition("\n")[2].strip()
    header = f"{title.strip()}\n\nXem full tại : https://www.youtube.com/watch?v={video_id}".strip()
    caption = "\n\n".join(part for part in (header, body) if part)
    seen = {tag.casefold() for tag in re.findall(r"#\w+", caption)}
    hashtags = []
    for tag in tags:
        cleaned = re.sub(r"[^\w]", "", unicodedata.normalize("NFC", tag), flags=re.UNICODE)
        if not cleaned:
            continue
        hashtag = "#" + cleaned
        if hashtag.casefold() not in seen:
            seen.add(hashtag.casefold())
            hashtags.append(hashtag)
    return "\n\n".join(part for part in (caption, " ".join(hashtags)) if part)


class FacebookClient:
    def __init__(self, config: dict):
        self.page_id = config.get("facebook_page_id", "")
        self.token = config.get("facebook_page_token", "")
        version = config.get("facebook_api_version", "v25.0")
        if not re.fullmatch(r"\d+", self.page_id) or not self.token:
            raise RuntimeError("Nhập Facebook Page ID và Page access token trong Cấu hình.")
        if not re.fullmatch(r"v\d+\.\d+", version):
            raise RuntimeError("Phiên bản Facebook Graph API không hợp lệ.")
        self.graph = f"https://graph.facebook.com/{version}"
        self.video_graph = f"https://graph-video.facebook.com/{version}"
        self.http = httpx.Client(
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=httpx.Timeout(300, connect=30),
        )

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.http.close()

    def request(self, method: str, path: str, *, upload: bool = False, **kwargs) -> dict:
        try:
            response = self.http.request(
                method, f"{self.video_graph if upload else self.graph}/{path}", **kwargs,
            )
        except httpx.HTTPError as exc:
            raise RuntimeError("Mất kết nối Facebook. Trạng thái sẽ giữ lại để kiểm tra/tiếp tục.") from exc
        try:
            data = response.json()
        except ValueError as exc:
            raise RuntimeError(f"Facebook trả về phản hồi không hợp lệ (HTTP {response.status_code}).") from exc
        if isinstance(data, dict) and (data.get("error") or not response.is_success):
            error = data.get("error") or {}
            message = str(error.get("message", "Yêu cầu thất bại")).replace(self.token, "[hidden]")
            raise RuntimeError(f"Facebook ({error.get('code', response.status_code)}): {message}")
        if not response.is_success or data is False or (isinstance(data, dict) and data.get("success") is False):
            raise RuntimeError("Facebook không chấp nhận yêu cầu.")
        return data if isinstance(data, dict) else {"success": data is True}

    def check_page(self) -> dict:
        page = self.request("GET", "me", params={"fields": "id,name"})
        if str(page.get("id")) != self.page_id:
            raise RuntimeError("Token không thuộc Page ID đã nhập. Hãy dùng Page access token của đúng Page.")
        return page

    def upload(self, path: Path, title: str, caption: str, update: Callable[..., None]) -> str:
        size = path.stat().st_size
        route = f"{self.page_id}/videos"
        data = self.request("POST", route, upload=True, data={"upload_phase": "start", "file_size": str(size)})
        video_id = str(data["video_id"])
        session_id = data["upload_session_id"]
        update(facebook_video_id=video_id, facebook_url=f"https://www.facebook.com/watch/?v={video_id}")
        start, end = int(data["start_offset"]), int(data["end_offset"])
        with path.open("rb") as source:
            while start != end:
                if not 0 <= start < end <= size:
                    raise RuntimeError("Facebook trả về khoảng upload không hợp lệ.")
                # Stream each server-requested chunk; large chunks spill to disk.
                with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as chunk:
                    source.seek(start)
                    remaining = end - start
                    while remaining:
                        block = source.read(min(1024 * 1024, remaining))
                        if not block:
                            raise RuntimeError("File video bị thiếu dữ liệu khi upload.")
                        chunk.write(block)
                        remaining -= len(block)
                    chunk.seek(0)
                    data = self.request("POST", route, upload=True, data={
                        "upload_phase": "transfer", "upload_session_id": session_id,
                        "start_offset": str(start),
                    }, files={"video_file_chunk": ("chunk.mp4", chunk, "application/octet-stream")})
                next_start, next_end = int(data["start_offset"]), int(data["end_offset"])
                if next_start <= start or not 0 <= next_start <= next_end <= size:
                    raise RuntimeError("Facebook không xác nhận tiến độ upload.")
                start, end = next_start, next_end
                update(progress=75 + round(15 * start / size, 1), message=f"Đang upload Facebook · {start * 100 / size:.0f}%")
        if start != size:
            raise RuntimeError("Facebook kết thúc upload trước khi nhận đủ file.")
        self.request("POST", route, upload=True, data={
            "upload_phase": "finish", "upload_session_id": session_id,
            "title": title, "description": caption, "published": "false",
        })
        update(upload_finished=True, status="processing", progress=90, message="Facebook đang xử lý video…")
        return video_id

    def video_status(self, video_id: str) -> dict:
        return self.request("GET", video_id, params={"fields": "status,published,permalink_url"})

    def wait_ready(self, video_id: str, timeout: int = 7200) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            data = self.video_status(video_id)
            status = data.get("status", {}).get("video_status")
            if status == "ready":
                return data
            if status in ("error", "expired"):
                raise RuntimeError(f"Facebook xử lý video thất bại: {status}.")
            time.sleep(10)
        raise RuntimeError("Facebook chưa xử lý xong sau 120 phút. Bấm Tiếp tục để kiểm tra lại video đã upload.")

    def set_thumbnail(self, video_id: str, thumbnail: Path) -> None:
        with thumbnail.open("rb") as source:
            self.request("POST", f"{video_id}/thumbnails", data={"is_preferred": "true"},
                         files={"source": ("thumbnail.jpg", source, "image/jpeg")})

    def publish(self, video_id: str) -> None:
        self.request("POST", video_id, data={"published": "true"})
