"""Wrapper YouTube Data API v3 qua httpx (read) + google-api-client (write/upload).

Chọn phương thức xác thực phù hợp từng tác vụ:
- Đọc public (list video 2 ngày qua, lấy mô tả): ưu tiên OAuth access_token,
  fallback sang API key nếu chưa login.
- Ghi (upload, sửa tiêu đề/mô tả, comment): BẮT BUỘC OAuth (API key không đủ quyền).
- Community post (tab Cộng đồng): YouTube Data API KHÔNG hỗ trợ tạo bài đăng
  → endpoint comment thay thế + ghi rõ giới hạn trong message.
"""

from datetime import datetime, timedelta, timezone

import httpx

API_BASE = "https://www.googleapis.com/youtube/v3"

# Đủ cho: đọc kênh/video + tải lên + sửa mô tả + bình luận.
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


def build_auth_url(client_id: str, redirect_uri: str) -> str:
    from urllib.parse import urlencode

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(GOOGLE_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def exchange_code(client_id: str, client_secret: str, redirect_uri: str, code: str) -> dict:
    resp = httpx.post(
        GOOGLE_TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "code": code,
        },
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Đổi code thất bại: {resp.text[:300]}")
    return resp.json()


def _headers(access_token: str | None, api_key: str) -> tuple[dict, dict]:
    headers = {"Authorization": f"Bearer {access_token}"} if access_token else {}
    key_param = {} if access_token else ({"key": api_key} if api_key else {})
    return headers, key_param


def resolve_channel_id(session: httpx.Client, identifier: str) -> str:
    """Nhận channelId / handle (@name) / custom URL → trả về channelId chuẩn."""
    identifier = identifier.strip()
    if identifier.startswith("UC") and " " not in identifier and "/" not in identifier:
        return identifier
    handle = identifier
    if "youtube.com" in identifier:
        handle = identifier.rstrip("/").rsplit("/", 1)[-1]
    if not handle.startswith("@"):
        handle = "@" + handle.lstrip("@")
    r = session.get(f"{API_BASE}/channels", params={"part": "id", "forHandle": handle})
    r.raise_for_status()
    items = r.json().get("items", [])
    if not items:
        raise RuntimeError(f"Không tìm thấy kênh: {identifier}")
    return items[0]["id"]


def _uploads_playlist(session: httpx.Client, channel_id: str) -> str:
    r = session.get(
        f"{API_BASE}/channels", params={"part": "contentDetails", "id": channel_id}
    )
    r.raise_for_status()
    items = r.json().get("items", [])
    if not items:
        raise RuntimeError(f"Không tìm thấy kênh: {channel_id}")
    return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]


def recent_videos(
    access_token: str | None,
    api_key: str,
    channel_ids: list[str],
    days: int = 2,
    per_channel: int | None = None,
) -> list[dict]:
    """List video công khai đã đăng trong `days` ngày gần nhất từ các kênh theo dõi.

    Dùng uploads playlist (quota rẻ ~1-3 unit) thay vì search.list (~100 unit),
    rồi lọc theo videoPublishedAt. Sau đó gọi videos.list để lấy full
    snippet + contentDetails + statistics (mô tả, duration, view/like).

    Độ sâu quét tăng theo `days` (kênh đăng nhiều cần nhiều trang mới phủ hết
    khung ngày), dừng sớm khi gặp video cũ hơn cutoff vì playlist xếp mới-nhất-trước.
    """
    if not access_token and not api_key:
        raise RuntimeError("Chưa cấu hình: cần login Google (OAuth) hoặc nhập YouTube API key.")
    if not channel_ids:
        raise RuntimeError("Chưa có kênh theo dõi nào. Thêm channel ID/handle ở trang Cấu hình.")

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    # Quét đủ sâu để phủ hết `days` ngày (tối đa 500 video/kênh, 50 video/trang).
    scan_limit = per_channel or max(50, min(500, days * 50))
    headers, key_param = _headers(access_token, api_key)
    found: list[dict] = []

    with httpx.Client(headers=headers, params=key_param, timeout=30) as session:
        resolved: list[str] = []
        for raw in channel_ids:
            try:
                resolved.append(resolve_channel_id(session, raw))
            except Exception:
                continue
        for cid in resolved:
            try:
                playlist = _uploads_playlist(session, cid)
            except Exception:
                continue
            page_token: str | None = None
            scanned = 0
            candidate_ids: list[str] = []
            while scanned < scan_limit:
                params = {
                    "part": "contentDetails",
                    "playlistId": playlist,
                    "maxResults": min(50, scan_limit - scanned),
                }
                if page_token:
                    params["pageToken"] = page_token
                r = session.get(f"{API_BASE}/playlistItems", params=params)
                if r.status_code != 200:
                    break
                payload = r.json()
                for it in payload.get("items", []):
                    scanned += 1
                    cd = it.get("contentDetails", {})
                    vid = cd.get("videoId", "")
                    published = cd.get("videoPublishedAt", "")
                    try:
                        dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
                    except Exception:
                        continue
                    if dt >= cutoff and vid:
                        candidate_ids.append(vid)
                    if scanned >= scan_limit:
                        break
                page_token = payload.get("nextPageToken")
                if not page_token:
                    break
                # Playlist sắp xếp mới-nhất-trước: gặp video quá cũ thì dừng sớm.
                oldest = payload.get("items", [])[-1].get("contentDetails", {}).get(
                    "videoPublishedAt", ""
                )
                try:
                    if datetime.fromisoformat(oldest.replace("Z", "+00:00")) < cutoff:
                        break
                except Exception:
                    pass
            if candidate_ids:
                found.extend(_videos_details(session, candidate_ids, public_only=True))

    found.sort(key=lambda v: v.get("published_at", ""), reverse=True)
    return found


def _videos_details(
    session: httpx.Client, video_ids: list[str], *, public_only: bool = False
) -> list[dict]:
    out: list[dict] = []
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i : i + 50]
        r = session.get(
            f"{API_BASE}/videos",
            params={"part": "snippet,contentDetails,statistics,status", "id": ",".join(chunk)},
        )
        if r.status_code != 200:
            continue
        for it in r.json().get("items", []):
            if public_only and it.get("status", {}).get("privacyStatus") != "public":
                continue
            sn = it.get("snippet", {})
            cd = it.get("contentDetails", {})
            st = it.get("statistics", {})
            thumbs = sn.get("thumbnails", {})
            best = (
                thumbs.get("medium") or thumbs.get("default") or {}
            ).get("url", "")
            vid = it.get("id", "")
            out.append(
                {
                    "video_id": vid,
                    "channel_id": sn.get("channelId", ""),
                    "channel_title": sn.get("channelTitle", ""),
                    "title": sn.get("title", ""),
                    "description": sn.get("description", ""),
                    "tags": sn.get("tags", []) or [],
                    "published_at": sn.get("publishedAt", ""),
                    "thumbnail": best,
                    "duration": cd.get("duration", ""),
                    "view_count": int(st.get("viewCount", 0) or 0),
                    "like_count": int(st.get("likeCount", 0) or 0),
                    "url": f"https://www.youtube.com/watch?v={vid}",
                }
            )
    return out


def get_video(access_token: str | None, api_key: str, video_id: str) -> dict:
    headers, key_param = _headers(access_token, api_key)
    with httpx.Client(headers=headers, params=key_param, timeout=30) as session:
        details = _videos_details(session, [video_id])
    if not details:
        raise RuntimeError(f"Không tìm thấy video: {video_id}")
    return details[0]


def my_uploaded_videos(access_token: str, limit: int = 200) -> list[dict]:
    """Lấy uploads của chính tài khoản cùng trạng thái hạn chế mà Data API công khai."""
    headers, _ = _headers(access_token, "")
    with httpx.Client(headers=headers, timeout=30) as session:
        channel_res = session.get(
            f"{API_BASE}/channels",
            params={"part": "contentDetails", "mine": "true"},
        )
        channel_res.raise_for_status()
        channels = channel_res.json().get("items", [])
        if not channels:
            raise RuntimeError("Tài khoản OAuth không có kênh YouTube.")
        playlist_id = channels[0]["contentDetails"]["relatedPlaylists"]["uploads"]

        video_ids: list[str] = []
        page_token = ""
        while len(video_ids) < limit:
            params = {
                "part": "contentDetails",
                "playlistId": playlist_id,
                "maxResults": min(50, limit - len(video_ids)),
            }
            if page_token:
                params["pageToken"] = page_token
            playlist_res = session.get(f"{API_BASE}/playlistItems", params=params)
            playlist_res.raise_for_status()
            payload = playlist_res.json()
            for item in payload.get("items", []):
                video_id = item.get("contentDetails", {}).get("videoId", "")
                if video_id:
                    video_ids.append(video_id)
            page_token = payload.get("nextPageToken", "")
            if not page_token:
                break

        details: dict[str, dict] = {}
        for offset in range(0, len(video_ids), 50):
            chunk = video_ids[offset : offset + 50]
            videos_res = session.get(
                f"{API_BASE}/videos",
                params={
                    "part": "snippet,contentDetails,statistics,status",
                    "id": ",".join(chunk),
                },
            )
            videos_res.raise_for_status()
            for item in videos_res.json().get("items", []):
                snippet = item.get("snippet", {})
                content = item.get("contentDetails", {})
                stats = item.get("statistics", {})
                status = item.get("status", {})
                regions = content.get("regionRestriction", {})
                rating = content.get("contentRating", {})
                privacy = status.get("privacyStatus", "")
                upload = status.get("uploadStatus", "")
                blocked = regions.get("blocked", []) or []
                allowed = regions.get("allowed", []) or []
                age_restricted = rating.get("ytRating") == "ytAgeRestricted"
                thumbs = snippet.get("thumbnails", {})
                thumbnail = (
                    thumbs.get("medium") or thumbs.get("default") or {}
                ).get("url", "")
                video_id = item.get("id", "")
                details[video_id] = {
                    "video_id": video_id,
                    "channel_id": snippet.get("channelId", ""),
                    "channel_title": snippet.get("channelTitle", ""),
                    "title": snippet.get("title", ""),
                    "description": snippet.get("description", ""),
                    "published_at": snippet.get("publishedAt", ""),
                    "thumbnail": thumbnail,
                    "duration": content.get("duration", ""),
                    "view_count": int(stats.get("viewCount", 0) or 0),
                    "like_count": int(stats.get("likeCount", 0) or 0),
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "privacy_status": privacy,
                    "upload_status": upload,
                    "failure_reason": status.get("failureReason", ""),
                    "rejection_reason": status.get("rejectionReason", ""),
                    "region_blocked": blocked,
                    "region_allowed": allowed,
                    "age_restricted": age_restricted,
                    "restricted": (
                        privacy != "public"
                        or upload != "processed"
                        or bool(blocked)
                        or bool(allowed)
                        or age_restricted
                    ),
                }
    return [details[video_id] for video_id in video_ids if video_id in details]


def _youtube_service(access_token: str):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(token=access_token)
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def update_video(
    access_token: str,
    video_id: str,
    title: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
    category_id: str | None = None,
    privacy: str | None = None,
) -> dict:
    """Sửa tiêu đề/mô tả/tags/quyền riêng tư — yêu cầu OAuth (force-ssl)."""
    yt = _youtube_service(access_token)
    current = yt.videos().list(part="snippet,status", id=video_id).execute()
    items = current.get("items", [])
    if not items:
        raise RuntimeError(f"Không tìm thấy video: {video_id}")
    snippet = items[0]["snippet"]
    status = items[0].get("status", {})
    if title is not None:
        snippet["title"] = title
    if description is not None:
        snippet["description"] = description
    if tags is not None:
        snippet["tags"] = tags
    if category_id is not None:
        snippet["categoryId"] = category_id
    if privacy is not None:
        status["privacyStatus"] = privacy
    updated = (
        yt.videos()
        .update(part="snippet,status", body={"id": video_id, "snippet": snippet, "status": status})
        .execute()
    )
    return {"video_id": updated.get("id", video_id)}


def post_comment(access_token: str, video_id: str, text: str) -> dict:
    """Đăng bình luận top-level vào video (thay cho community post — API không hỗ trợ tạo bài đăng)."""
    yt = _youtube_service(access_token)
    res = (
        yt.commentThreads()
        .insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {"snippet": {"textOriginal": text}},
                }
            },
        )
        .execute()
    )
    return {"comment_id": res.get("id", "")}


def upload_video(
    access_token: str,
    file_path: str,
    title: str,
    description: str = "",
    privacy: str = "private",
    tags: list[str] | None = None,
    category_id: str = "22",
) -> dict:
    from googleapiclient.http import MediaFileUpload

    yt = _youtube_service(access_token)
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or [],
            "categoryId": category_id,
        },
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(file_path, resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    video_id = resp.get("id", "")
    return {"video_id": video_id, "url": f"https://www.youtube.com/watch?v={video_id}"}


def my_channel_title(access_token: str) -> str:
    yt = _youtube_service(access_token)
    res = yt.channels().list(part="snippet", mine=True).execute()
    items = res.get("items", [])
    return items[0]["snippet"]["title"] if items else ""
