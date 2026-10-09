"""Phân tích link YouTube bất kỳ + AI gợi ý tiêu đề (Gemini)."""

import json
import re
import time

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.config import settings
from app.services import store

router = APIRouter()

_VIDEO_ID_RES = [
    re.compile(r"youtu\.be/([A-Za-z0-9_-]{6,})"),
    re.compile(r"[?&]v=([A-Za-z0-9_-]{6,})"),
    re.compile(r"/shorts/([A-Za-z0-9_-]{6,})"),
    re.compile(r"/embed/([A-Za-z0-9_-]{6,})"),
    re.compile(r"/live/([A-Za-z0-9_-]{6,})"),
]
_HASHTAG_RE = re.compile(r"#([^\s#@.,!?;:\"'()\[\]{}]+)", re.UNICODE)


class AnalyzeIn(BaseModel):
    url: str


class TitleAiIn(BaseModel):
    title: str
    model: str = "gemini-3.1-flash-lite"


def extract_video_id(url: str) -> str:
    url = (url or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url):
        return url
    for rx in _VIDEO_ID_RES:
        m = rx.search(url)
        if m:
            return m.group(1)
    raise HTTPException(400, "Link không phải URL video YouTube hợp lệ.")


def _hashtags(text: str) -> list[str]:
    seen: list[str] = []
    for tag in _HASHTAG_RE.findall(text or ""):
        t = "#" + tag.strip("#")
        if t not in seen:
            seen.append(t)
    return seen


@router.post("/analyze")
def analyze(body: AnalyzeIn) -> dict:
    from app.services.youtube_client import get_video

    video_id = extract_video_id(body.url)
    data = store.load_config()
    tokens = store.get_valid_tokens()
    access = (tokens or {}).get("access_token")
    api_key = data.get("youtube_api_key", "")

    warning = ""
    info: dict | None = None
    if access or api_key:
        try:
            info = get_video(access, api_key, video_id)
        except Exception as e:
            warning = f"YouTube API lỗi ({e}) — chỉ lấy được thông tin cơ bản."
    else:
        warning = "Chưa cấu hình API key / login Google — chỉ lấy được thông tin cơ bản (tags, mô tả đầy đủ cần API key)."

    if info is None:
        # Fallback oEmbed: tên + tác giả + thumbnail, không tốn quota.
        import httpx

        try:
            r = httpx.get(
                "https://www.youtube.com/oembed",
                params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
                timeout=15,
            )
            o = r.json() if r.status_code == 200 else {}
        except Exception:
            o = {}
        info = {
            "video_id": video_id,
            "channel_id": "",
            "channel_title": o.get("author_name", ""),
            "title": o.get("title", ""),
            "description": "",
            "published_at": "",
            "thumbnail": f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
            "duration": "",
            "view_count": 0,
            "like_count": 0,
            "url": f"https://www.youtube.com/watch?v={video_id}",
        }
        tags: list[str] = []
    else:
        tags = []
        # get_video không trả tags — lấy thêm qua videos.list? Dùng snippet.tags:
        tags = info.pop("tags", []) if isinstance(info.get("tags"), list) else []

    # Lấy tags đầy đủ qua snippet (get_video hiện chưa include) — gọi nhẹ 1 lần:
    if access or api_key:
        import httpx

        try:
            headers = {"Authorization": f"Bearer {access}"} if access else {}
            params = {"part": "snippet", "id": video_id}
            if not access and api_key:
                params["key"] = api_key
            r = httpx.get(
                "https://www.googleapis.com/youtube/v3/videos",
                headers=headers, params=params, timeout=20,
            )
            items = r.json().get("items", []) if r.status_code == 200 else []
            if items:
                tags = items[0].get("snippet", {}).get("tags", []) or tags
        except Exception:
            pass

    text_all = f"{info.get('title', '')}\n{info.get('description', '')}"
    return {
        **info,
        "tags": tags,
        "hashtags": _hashtags(text_all),
        "warning": warning,
    }


@router.post("/analyze/title-ai")
def title_ai(body: TitleAiIn) -> dict:
    """Dịch tiêu đề sang tiếng Việt + gợi ý 3-4 tiêu đề ~70 ký tự (Gemini)."""
    from app.services.gemini import DEFAULT_MODEL, generate_with_fallback

    title = (body.title or "").strip()
    if not title:
        raise HTTPException(400, "Thiếu tiêu đề.")
    data = store.load_config()
    api_key = data.get("gemini_api_key", "")
    prompt = (
        "Dịch tiêu đề video sau sang tiếng Việt và gợi ý tiêu đề hấp dẫn "
        "giúp tôi, mỗi tiêu đề khoảng 70 ký tự, giữ đúng nội dung gốc.\n"
        f'Tiêu đề: "{title}"\n'
        "Trả về đúng JSON (không giải thích thêm): "
        '{"translation": "<bản dịch raw>", '
        '"options": ["<option 1>", "<option 2>", "<option 3>", "<option 4>"]}'
    )
    try:
        raw, used_model = generate_with_fallback(
            api_key, prompt, model=body.model or DEFAULT_MODEL
        )
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"Lỗi gọi Gemini: {e}")

    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned).strip()
    try:
        parsed = json.loads(cleaned)
        translation = str(parsed.get("translation", "") or "")
        options = [str(o) for o in (parsed.get("options") or []) if str(o).strip()][:4]
    except json.JSONDecodeError:
        translation, options = cleaned, []
    if not translation and not options:
        raise HTTPException(502, f"Gemini trả về không parse được: {raw[:300]}")
    return {"translation": translation, "options": options, "raw": raw, "model": used_model}


# ── Lưu phân tích (backend/temp/analyzed/{video_id}.json + {video_id}.jpg) ──

def _analyzed_dir():
    d = settings.temp_dir / "analyzed"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _fetch_thumbnail_bytes(video_id: str) -> bytes | None:
    import httpx

    for name in ("maxresdefault", "sddefault", "hqdefault", "mqdefault"):
        try:
            r = httpx.get(f"https://i.ytimg.com/vi/{video_id}/{name}.jpg", timeout=20)
            if r.status_code == 200 and len(r.content) > 10_000:
                return r.content
        except Exception:
            continue
    return None


def _thumbnail_local_path(video_id: str):
    return _analyzed_dir() / f"{video_id}.jpg"


class AnalyzedSaveIn(BaseModel):
    info: dict
    ai: dict | None = None
    # Nguồn tạo entry: "analyze" (tab Phân tích) hoặc "facebook-flow"
    # (nút gen cover bên tab Facebook — ẩn khỏi danh sách Phân tích).
    origin: str = "analyze"


def _entry_origin(video_id: str, data: dict) -> str:
    """Nguồn của entry đã lưu. Suy luận cho bản lưu cũ (chưa có origin):
    chỉ có .cover.png mà không có .generated.png → do Facebook-flow tạo,
    vì tab Phân tích không bao giờ ghi file .cover.png."""
    origin = (data.get("origin") or "").strip()
    if origin:
        return origin
    directory = _analyzed_dir()
    if ((directory / f"{video_id}.cover.png").exists()
            and not (directory / f"{video_id}.generated.png").exists()):
        return "facebook-flow"
    return "analyze"


@router.get("/analyzed")
def list_analyzed() -> dict:
    items = []
    for f in _analyzed_dir().glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            info = data.get("info", {})
            video_id = info.get("video_id", f.stem)
            # Entry do Facebook-flow tạo (gen cover) không thuộc tab Phân tích.
            if _entry_origin(video_id, data) != "analyze":
                continue
            items.append({
                "video_id": video_id,
                "title": info.get("title", ""),
                "channel_title": info.get("channel_title", ""),
                "thumbnail": info.get("thumbnail", ""),
                "thumbnail_local": (
                    f"/api/analyzed/{video_id}/image"
                    if _thumbnail_local_path(video_id).exists()
                    else ""
                ),
                "has_ai": bool((data.get("ai") or {}).get("translation")),
                "has_generated_thumbnail": (_analyzed_dir() / f"{video_id}.generated.png").exists(),
                "has_cover": (_analyzed_dir() / f"{video_id}.cover.png").exists(),
                "saved_at": data.get("saved_at", 0),
            })
        except Exception:
            continue
    items.sort(key=lambda x: x["saved_at"], reverse=True)
    return {"videos": items, "count": len(items)}


@router.post("/analyzed")
def save_analyzed(body: AnalyzedSaveIn) -> dict:
    video_id = (body.info.get("video_id") or "").strip()
    if not video_id:
        raise HTTPException(400, "Thiếu video_id.")
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,}", video_id):
        raise HTTPException(400, "video_id không hợp lệ.")
    origin = (body.origin or "analyze").strip() or "analyze"
    if origin not in ("analyze", "facebook-flow"):
        raise HTTPException(400, "origin chỉ nhận 'analyze' hoặc 'facebook-flow'.")
    # Tải thumbnail về đĩa ngay lúc lưu — link YT chết vẫn còn ảnh.
    thumb_saved = False
    try:
        blob = _fetch_thumbnail_bytes(video_id)
        if blob:
            _thumbnail_local_path(video_id).write_bytes(blob)
            thumb_saved = True
    except Exception:
        pass
    payload = {
        "info": body.info,
        "ai": body.ai,
        "origin": origin,
        "saved_at": time.time(),
        "thumbnail_local": f"/api/analyzed/{video_id}/image" if thumb_saved else "",
    }
    _analyzed_dir().joinpath(f"{video_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"status": "ok", "video_id": video_id, "thumbnail_saved": thumb_saved}


@router.get("/analyzed/{video_id}")
def get_analyzed(video_id: str) -> dict:
    f = _analyzed_dir() / f"{video_id}.json"
    if not f.exists():
        raise HTTPException(404, "Video chưa được lưu.")
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        raise HTTPException(500, "File lưu bị lỗi.")
    # Backfill cho bản lưu cũ (trước khi có tính năng lưu thumbnail).
    if not data.get("thumbnail_local") and _thumbnail_local_path(video_id).exists():
        data["thumbnail_local"] = f"/api/analyzed/{video_id}/image"
    generated = _analyzed_dir() / f"{video_id}.generated.png"
    data["generated_thumbnail"] = (
        f"/api/analyzed/{video_id}/generated-thumbnail" if generated.exists() else ""
    )
    cover = _analyzed_dir() / f"{video_id}.cover.png"
    data["cover"] = f"/api/analyzed/{video_id}/cover" if cover.exists() else ""
    return data


@router.get("/analyzed/{video_id}/image")
def get_analyzed_image(video_id: str):
    """Ảnh thumbnail đã lưu (ưu tiên file local — link YT chết vẫn xem được)."""
    from fastapi.responses import Response

    local = _thumbnail_local_path(video_id)
    if local.exists():
        return Response(content=local.read_bytes(), media_type="image/jpeg")
    # Bản lưu cũ chưa có ảnh local → thử proxy live rồi cache lại.
    blob = _fetch_thumbnail_bytes(video_id)
    if blob:
        try:
            local.write_bytes(blob)
        except OSError:
            pass
        return Response(content=blob, media_type="image/jpeg")
    raise HTTPException(404, "Không còn thumbnail (link gốc đã chết và chưa từng lưu ảnh).")


@router.post("/analyzed/{video_id}/generated-thumbnail")
async def save_generated_thumbnail(video_id: str, file: UploadFile = File(...), slot: str = "") -> dict:
    """Lưu ảnh ChatGPT tạo, tách biệt thumbnail gốc đã archive.

    slot="cover": lưu ảnh bìa 1088×1446 cho Facebook flow
    (analyzed/{video_id}.cover.png) thay vì thumbnail 16:9.
    """
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,}", video_id):
        raise HTTPException(400, "video_id không hợp lệ.")
    if slot not in ("", "cover"):
        raise HTTPException(400, "slot chỉ nhận '' hoặc 'cover'.")
    data = await file.read()
    if not data:
        raise HTTPException(400, "File ảnh trống.")
    name = f"{video_id}.cover.png" if slot == "cover" else f"{video_id}.generated.png"
    path = _analyzed_dir() / name
    tmp = path.with_suffix(".png.tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
    return {
        "status": "done",
        "url": f"/api/analyzed/{video_id}/cover" if slot == "cover" else f"/api/analyzed/{video_id}/generated-thumbnail",
    }


@router.get("/analyzed/{video_id}/generated-thumbnail")
def get_generated_thumbnail(video_id: str):
    from fastapi.responses import FileResponse

    path = _analyzed_dir() / f"{video_id}.generated.png"
    if not path.exists():
        raise HTTPException(404, "Chưa có thumbnail ChatGPT.")
    return FileResponse(path, media_type="image/png")


@router.get("/analyzed/{video_id}/cover")
def get_cover(video_id: str):
    """Ảnh bìa 1088×1446 ChatGPT đã gen cho Facebook flow."""
    from fastapi.responses import FileResponse

    path = _analyzed_dir() / f"{video_id}.cover.png"
    if not path.exists():
        raise HTTPException(404, "Chưa có ảnh bìa ChatGPT cho video này.")
    return FileResponse(path, media_type="image/png")


@router.delete("/analyzed/{video_id}")
def delete_analyzed(video_id: str) -> dict:
    f = _analyzed_dir() / f"{video_id}.json"
    if f.exists():
        try:
            f.unlink()
        except OSError:
            raise HTTPException(500, "Không xóa được file.")
    img = _thumbnail_local_path(video_id)
    if img.exists():
        try:
            img.unlink()
        except OSError:
            pass
    generated = _analyzed_dir() / f"{video_id}.generated.png"
    if generated.exists():
        try:
            generated.unlink()
        except OSError:
            pass
    cover = _analyzed_dir() / f"{video_id}.cover.png"
    if cover.exists():
        try:
            cover.unlink()
        except OSError:
            pass
    return {"status": "ok", "removed": f.exists() is False}
