"""OAuth Google cho YouTube Data API (đọc + upload + sửa mô tả + comment)."""

import time

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.config import settings
from app.models import AuthStatusOut, AuthUrlOut
from app.services import store
from app.services.youtube_client import build_auth_url, exchange_code, my_channel_title

router = APIRouter()


@router.get("/youtube/auth/url", response_model=AuthUrlOut)
def auth_url() -> AuthUrlOut:
    data = store.load_config()
    client_id = data.get("youtube_client_id", "")
    redirect_uri = data.get("oauth_redirect_uri", "")
    if not client_id or not data.get("youtube_client_secret"):
        raise HTTPException(
            400,
            "Chưa nhập Client ID / Client Secret. Vào trang Cấu hình để lưu trước.",
        )
    if not redirect_uri:
        raise HTTPException(400, "Chưa cấu hình Redirect URI.")
    return AuthUrlOut(url=build_auth_url(client_id, redirect_uri))


@router.get("/youtube/auth/callback")
def auth_callback(code: str = Query(""), error: str = Query("")):
    if error:
        raise HTTPException(400, f"Google từ chối cấp quyền: {error}")
    if not code:
        raise HTTPException(400, "Thiếu code từ Google.")
    data = store.load_config()
    try:
        tokens = exchange_code(
            data["youtube_client_id"],
            data["youtube_client_secret"],
            data["oauth_redirect_uri"],
            code,
        )
    except Exception as e:
        raise HTTPException(400, str(e))
    saved = {
        "access_token": tokens.get("access_token", ""),
        "refresh_token": tokens.get("refresh_token", ""),
        "expires_at": time.time() + int(tokens.get("expires_in", 3600)),
        "channel_title": "",
    }
    # Giữ refresh_token cũ nếu Google không trả mới (lần login thứ 2+).
    old = (data.get("tokens") or {}).get("refresh_token", "")
    if not saved["refresh_token"] and old:
        saved["refresh_token"] = old
    store.save_tokens(saved)
    try:
        title = my_channel_title(saved["access_token"])
        saved["channel_title"] = title
        store.save_tokens(saved)
    except Exception:
        pass
    frontend = settings.frontend_url.rstrip("/")
    return RedirectResponse(f"{frontend}/?connected=1")


@router.get("/youtube/auth/status", response_model=AuthStatusOut)
def auth_status() -> AuthStatusOut:
    data = store.load_config()
    tokens = data.get("tokens") or {}
    if not tokens.get("refresh_token"):
        return AuthStatusOut(connected=False)
    return AuthStatusOut(
        connected=True,
        channel_title=tokens.get("channel_title", ""),
        expires_at=str(tokens.get("expires_at", "")),
    )


@router.post("/youtube/auth/disconnect")
def disconnect() -> dict:
    store.clear_tokens()
    return {"status": "ok"}
