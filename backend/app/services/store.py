"""Lưu cấu hình + OAuth tokens vào backend/temp/yt_config.json (gitignored).

Cấu hình được lưu qua UI (POST /api/config) nên backend restart không mất.
"""

import json
import time
from pathlib import Path
from typing import Any

from app.config import settings

CONFIG_PATH = settings.temp_dir / "yt_config.json"

DEFAULT_POST_TEMPLATE = (
    "Bài đăng mới hôm nay: {title} \U0001F60D\U0001F60D\U0001F60D.\n"
    "Xem ngay tại đây: {url}\n"
    "\n"
    "Các bạn thấy hay ủng hộ cho ad 1 like, share và cmt để tăng tương tác "
    "giúp kênh phát triển nha. Ad cảm ơn rất nhiều \U0001F970\U0001F970\U0001F970"
)

_DEFAULTS: dict[str, Any] = {
    "youtube_client_id": "",
    "youtube_client_secret": "",
    "youtube_api_key": "",
    "oauth_redirect_uri": "",
    "track_channel_ids": [],
    "days_window": 2,
    "gemini_api_key": "",
    "post_template": DEFAULT_POST_TEMPLATE,
    "facebook_page_id": "",
    "facebook_page_token": "",
    "facebook_api_version": "v25.0",
    "tokens": None,  # {"access_token","refresh_token","expires_at","channel_title"}
}


def _merge_env(data: dict[str, Any]) -> dict[str, Any]:
    """Ưu tiên giá trị đã lưu trong file; fallback sang env/.env."""
    if not data.get("youtube_client_id"):
        data["youtube_client_id"] = settings.youtube_client_id
    if not data.get("youtube_client_secret"):
        data["youtube_client_secret"] = settings.youtube_client_secret
    if not data.get("youtube_api_key"):
        data["youtube_api_key"] = settings.youtube_api_key
    if not data.get("oauth_redirect_uri"):
        data["oauth_redirect_uri"] = settings.oauth_redirect_uri or ""
    return data


def load_config() -> dict[str, Any]:
    data: dict[str, Any] = dict(_DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            data.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except Exception:
            pass
    return _merge_env(data)


def save_config(patch: dict[str, Any]) -> dict[str, Any]:
    data = load_config()
    for key in (
        "youtube_client_id",
        "youtube_client_secret",
        "youtube_api_key",
        "oauth_redirect_uri",
        "track_channel_ids",
        "days_window",
        "gemini_api_key",
        "post_template",
        "facebook_page_id",
        "facebook_page_token",
        "facebook_api_version",
    ):
        if key in patch and patch[key] is not None:
            data[key] = patch[key]
    CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def save_tokens(tokens: dict[str, Any]) -> dict[str, Any]:
    data = load_config()
    data["tokens"] = tokens
    CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def clear_tokens() -> dict[str, Any]:
    data = load_config()
    data["tokens"] = None
    CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def get_valid_tokens() -> dict[str, Any] | None:
    """Trả về tokens còn dùng được; tự refresh nếu access_token hết hạn."""
    from google.auth.transport.requests import Request as GoogleRequest
    from google.oauth2.credentials import Credentials

    from app.services.youtube_client import GOOGLE_SCOPES

    data = load_config()
    tokens = data.get("tokens")
    if not tokens or not tokens.get("refresh_token"):
        return None
    creds = Credentials(
        token=tokens.get("access_token"),
        refresh_token=tokens.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=data.get("youtube_client_id"),
        client_secret=data.get("youtube_client_secret"),
        scopes=GOOGLE_SCOPES,
    )
    expires_at = float(tokens.get("expires_at") or 0)
    if not creds.token or (expires_at and expires_at - time.time() < 120):
        try:
            creds.refresh(GoogleRequest())
        except Exception:
            return None
        tokens = {
            "access_token": creds.token,
            "refresh_token": creds.refresh_token or tokens.get("refresh_token"),
            "expires_at": time.time() + 3600,
            "channel_title": tokens.get("channel_title", ""),
        }
        save_tokens(tokens)
    return tokens
