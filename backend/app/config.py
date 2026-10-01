from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    base_dir: Path = Path(__file__).resolve().parent.parent
    temp_dir: Path = base_dir / "temp"

    port: int = 8001
    frontend_url: str = "http://localhost:3001"

    # Google OAuth (YouTube Data API v3). Có thể để trống ở .env rồi nhập ở UI.
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    # API key public (optional): dùng cho các call read-only khi chưa login OAuth.
    youtube_api_key: str = ""
    # Redirect URI phải khớp 100% với URI đã đăng ký trong Google Cloud Console.
    oauth_redirect_uri: str = "http://localhost:8001/api/youtube/auth/callback"

    model_config = {"env_prefix": "YTV_", "env_file": ".env"}


settings = Settings()
settings.temp_dir.mkdir(parents=True, exist_ok=True)
(settings.temp_dir / "videos").mkdir(exist_ok=True)
