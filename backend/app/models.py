"""Pydantic v2 schemas cho YT Recent Videos."""

from typing import Literal

from pydantic import BaseModel, Field


class AppConfigIn(BaseModel):
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    youtube_api_key: str = ""
    oauth_redirect_uri: str = ""
    track_channel_ids: list[str] = Field(default_factory=list)
    days_window: int = 2
    gemini_api_key: str = ""
    post_template: str = ""
    facebook_page_id: str = Field(default="", pattern=r"^\d*$")
    facebook_page_token: str = ""
    facebook_api_version: str = Field(default="v25.0", pattern=r"^v\d+\.\d+$")


class AppConfigOut(BaseModel):
    youtube_client_id: str = ""
    has_client_secret: bool = False
    has_api_key: bool = False
    oauth_redirect_uri: str = ""
    track_channel_ids: list[str] = Field(default_factory=list)
    days_window: int = 2
    has_gemini_key: bool = False
    post_template: str = ""
    connected: bool = False
    channel_title: str = ""
    facebook_page_id: str = ""
    has_facebook_token: bool = False
    facebook_api_version: str = "v25.0"


class AuthUrlOut(BaseModel):
    url: str


class AuthStatusOut(BaseModel):
    connected: bool = False
    channel_title: str = ""
    expires_at: str = ""


class VideoItem(BaseModel):
    video_id: str
    channel_id: str = ""
    channel_title: str = ""
    title: str = ""
    description: str = ""
    published_at: str = ""
    thumbnail: str = ""
    duration: str = ""
    view_count: int = 0
    like_count: int = 0
    url: str = ""
    tags: list[str] = Field(default_factory=list)


class RecentOut(BaseModel):
    videos: list[VideoItem] = Field(default_factory=list)
    count: int = 0
    days: int = 2
    channels: list[str] = Field(default_factory=list)


class OwnedVideoItem(VideoItem):
    privacy_status: str = ""
    upload_status: str = ""
    failure_reason: str = ""
    rejection_reason: str = ""
    region_blocked: list[str] = Field(default_factory=list)
    region_allowed: list[str] = Field(default_factory=list)
    age_restricted: bool = False
    restricted: bool = False


class OwnedVideosOut(BaseModel):
    videos: list[OwnedVideoItem] = Field(default_factory=list)
    count: int = 0
    restricted_count: int = 0


class VideoUpdateIn(BaseModel):
    title: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    category_id: str | None = None
    privacy: Literal["public", "unlisted", "private"] | None = None


class CommentIn(BaseModel):
    text: str


class UploadOut(BaseModel):
    video_id: str
    url: str


class FacebookFlowIn(BaseModel):
    video_id: str = Field(pattern=r"^[A-Za-z0-9_-]{11}$")
    title: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=20000)
    tags: list[str] | None = Field(default=None, max_length=100)
    target_minutes: float = Field(default=30, ge=1, le=180)
    search_window: float = Field(default=60, ge=5, le=300)
    silence_db: float = Field(default=-35, ge=-60, le=-15)
    silence_duration: float = Field(default=0.5, ge=0.2, le=3)
    cookies_from_browser: Literal["", "chrome", "firefox", "safari", "edge", "brave"] = ""
    full_video: bool = False
    comment_blocked: bool = False
    # Intro cover + outro YT: ghép sau khi cắt xong.
    add_intro_outro: bool = True
    intro_seconds: float = Field(default=1.0, ge=0.5, le=10)
    outro_seconds: float = Field(default=5.0, ge=2, le=15)
    cover_prompt: str = Field(
        default="Làm rõ nét hình ảnh, giữ lại thông tin Phần ở góc trên phải, "
        "chỉnh tỉ lệ hình thành 1088 × 1446",
        max_length=2000,
    )


class FacebookFlowBatchIn(BaseModel):
    items: list[FacebookFlowIn] = Field(min_length=1, max_length=20)
