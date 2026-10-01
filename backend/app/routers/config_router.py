from fastapi import APIRouter

from app.models import AppConfigIn, AppConfigOut
from app.services import store

router = APIRouter()


@router.get("/config", response_model=AppConfigOut)
def get_config() -> AppConfigOut:
    data = store.load_config()
    tokens = data.get("tokens") or {}
    return AppConfigOut(
        youtube_client_id=data.get("youtube_client_id", ""),
        has_client_secret=bool(data.get("youtube_client_secret")),
        has_api_key=bool(data.get("youtube_api_key")),
        oauth_redirect_uri=data.get("oauth_redirect_uri", ""),
        track_channel_ids=data.get("track_channel_ids", []),
        days_window=int(data.get("days_window", 2) or 2),
        has_gemini_key=bool(data.get("gemini_api_key")),
        post_template=data.get("post_template", "") or store.DEFAULT_POST_TEMPLATE,
        connected=bool(tokens.get("refresh_token")),
        channel_title=tokens.get("channel_title", ""),
        facebook_page_id=data.get("facebook_page_id", ""),
        has_facebook_token=bool(data.get("facebook_page_token")),
        facebook_api_version=data.get("facebook_api_version", "v25.0"),
    )


@router.post("/config")
def post_config(body: AppConfigIn) -> dict:
    patch = body.model_dump(exclude_unset=True)
    # Không ghi đè secret/api key bằng chuỗi rỗng khi user chỉ sửa kênh theo dõi.
    if not patch.get("youtube_client_secret"):
        patch.pop("youtube_client_secret", None)
    if not patch.get("youtube_api_key"):
        patch.pop("youtube_api_key", None)
    if not patch.get("gemini_api_key"):
        patch.pop("gemini_api_key", None)
    if not patch.get("facebook_page_token"):
        patch.pop("facebook_page_token", None)
    if not patch.get("post_template"):
        patch.pop("post_template", None)
    data = store.save_config(patch)
    return {"status": "ok", "track_channels": len(data.get("track_channel_ids", []))}
