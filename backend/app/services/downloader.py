"""Tải video YouTube bằng yt-dlp (nightly) vào backend/temp/videos/."""

import importlib.util
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from app.config import settings

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")
_BAD_FILENAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')

#: File cookie YouTube do người dùng upload (định dạng Netscape cookies.txt).
#: Nằm trong backend/temp (gitignored) để backend dùng cho mọi lượt tải.
def cookies_path() -> Path:
    return settings.temp_dir / "youtube_cookies.txt"


COOKIES_PATH = settings.temp_dir / "youtube_cookies.txt"

_BOT_CHECK_MARKERS = (
    "Sign in to confirm",
    "not a bot",
    "cookies-from-browser",
    "cookies for the authentication",
)


def youtube_cookies_file() -> Path | None:
    """Trả về file cookies.txt nếu đã upload và còn nội dung."""
    path = cookies_path()
    try:
        if path.is_file() and path.stat().st_size > 0:
            return path
    except OSError:
        return None
    return None


def cookies_args(browser: str = "") -> list[str]:
    """Ưu tiên file cookies.txt (ổn định hơn) rồi mới tới cookie trình duyệt."""
    cookies_file = youtube_cookies_file()
    if cookies_file is not None:
        return ["--cookies", str(cookies_file)]
    if browser:
        return ["--cookies-from-browser", browser]
    return []


def is_bot_check_error(text: str) -> bool:
    lowered = (text or "").lower()
    return any(marker.lower() in lowered for marker in _BOT_CHECK_MARKERS)


def bot_check_hint(browser: str = "") -> str:
    """Hướng dẫn khắc phục lỗi bot-check của YouTube, tùy theo cách đã thử."""
    if youtube_cookies_file() is not None:
        return (
            "YouTube vẫn chặn dù đã có cookies.txt: mở YouTube trên trình duyệt đã "
            "xuất cookie, đăng nhập lại nếu bị đăng xuất, xuất lại file cookies.txt "
            "mới (extension Get cookies.txt LOCALLY, tick youtube.com) rồi upload lại. "
            "Nếu vừa đổi IP/VPN hoặc xác minh nhiều lần, chờ một lúc rồi thử lại."
        )
    if browser:
        return (
            f"Không đọc được phiên YouTube từ {browser} (trình duyệt khóa cookie, "
            "chưa đăng nhập YouTube, hoặc backend chạy user khác). Cách chắc chắn: "
            "xuất file cookies.txt từ trình duyệt đã đăng nhập YouTube rồi upload "
            "ở mục Cookie YouTube — backend sẽ ưu tiên dùng file này."
        )
    return (
        "Video này yêu cầu đăng nhập YouTube (bot-check). Chọn trình duyệt đã "
        "đăng nhập YouTube ở mục Cookie, hoặc upload file cookies.txt xuất từ "
        "trình duyệt đó rồi chạy lại."
    )


def yt_dlp_command() -> list[str]:
    """Use the backend's Python environment even when its bin directory is not in PATH."""
    if importlib.util.find_spec("yt_dlp") is not None:
        return [sys.executable, "-m", "yt_dlp"]
    executable = shutil.which("yt-dlp")
    if executable:
        return [executable]
    install = shlex.join([
        sys.executable, "-m", "pip", "install", "-r", str(settings.base_dir / "requirements.txt"),
    ])
    raise RuntimeError(f"Chưa cài yt-dlp trong môi trường backend. Chạy: {install}")


def safe_name(name: str) -> str:
    return _SAFE.sub("_", name).strip("_")[:80] or "video"


def safe_title(name: str, max_len: int = 100) -> str:
    """Giữ nguyên Unicode (Việt/Trung) — chỉ bỏ ký tự cấm của filesystem."""
    cleaned = _BAD_FILENAME.sub(" ", name or "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned[:max_len] or "video"


_DOWNLOAD_BAD = re.compile(r'[\\/:*?"<>\x00-\x1f]+')


def download_title(name: str, max_len: int = 100) -> str:
    """Tên file gợi ý khi tải về qua browser: giữ dấu | theo yêu cầu user.

    Chỉ bỏ ký tự nguy hiểm cho Content-Disposition/Windows (kể cả \r\n
    chống header injection), giữ nguyên Unicode. Riêng | được đổi thành
    ｜ (fullwidth) vì Chrome/Safari tự thay | bằng _ khi lưu file
    (| là ký tự cấm tên file trên Windows nên browser sanitize mọi OS).
    """
    cleaned = _DOWNLOAD_BAD.sub(" ", name or "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    cleaned = cleaned.replace("|", "｜")
    return cleaned[:max_len] or "video"


def video_title(video_id: str) -> str:
    """Lấy tên video qua oEmbed (nhẹ, không tốn quota, không cần auth)."""
    import httpx

    try:
        r = httpx.get(
            "https://www.youtube.com/oembed",
            params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
            timeout=15,
        )
        if r.status_code == 200:
            return (r.json().get("title") or "").strip()
    except Exception:
        pass
    return ""


def video_filename(video_id: str, ext: str) -> str:
    """Tên file tải về = tên video; fallback về video_id khi không lấy được."""
    title = video_title(video_id)
    base = safe_title(title) if title else video_id
    return f"{base}.{ext.lstrip('.')}"


def _format_for(quality: str) -> str:
    """Format có fallback: ưu tiên gộp video+audio riêng, luôn rơi về được `b`."""
    if not quality or quality == "best":
        return "bv*+ba/b"
    digits = "".join(c for c in str(quality) if c.isdigit())
    if not digits:
        return "bv*+ba/b"
    h = int(digits)
    return f"bv*[height<={h}]+ba/b[height<={h}]/bv*+ba/b"


def _has_js_runtime() -> bool:
    return _js_runtime_arg() != []


def _js_runtime_arg() -> list[str]:
    """yt-dlp nightly chỉ bật deno mặc định → truyền runtime có sẵn (node/bun)
    vào để nó giải được JS challenge, nếu không nhiều format sẽ biến mất."""
    for rt in ("deno", "node", "bun"):
        p = shutil.which(rt)
        if p:
            return ["--js-runtimes", f"{rt}:{p}"]
    return []


def _challenge_solver_arg() -> list[str]:
    """yt-dlp 2026 cần script giải n-challenge (EJS) tải từ GitHub.

    Không có flag này, video bị chặn/bảo vệ sẽ lỗi "n challenge solving
    failed" rồi "The page needs to be reloaded".
    """
    return ["--remote-components", "ejs:github"]


def download_video(video_id: str, quality: str = "best", cookies_from_browser: str = "") -> Path:
    command = yt_dlp_command()
    out_dir = settings.temp_dir / "videos"
    out_dir.mkdir(parents=True, exist_ok=True)
    # Dọn file cũ của cùng video để không trả nhầm bản cũ.
    for old in out_dir.glob(f"{video_id}.*"):
        try:
            old.unlink()
        except OSError:
            pass

    fmt = _format_for(quality)
    template = str(out_dir / f"{video_id}.%(ext)s")
    url = f"https://www.youtube.com/watch?v={video_id}"
    base = [
        *command,
        "--no-playlist",
        "--merge-output-format", "mp4",
        "--retries", "3",
        "--fragment-retries", "3",
        *cookies_args(cookies_from_browser),
        *_js_runtime_arg(),
        *_challenge_solver_arg(),
        "-o", template,
    ]
    # Lần 1: client mặc định. Lần 2: ép player_client=android để né lỗi
    # SABR/PO-token ("Requested format is not available") của YouTube 2026.
    attempts = [
        base + ["-f", fmt, url],
        base + ["--extractor-args", "youtube:player_client=android", "-f", fmt, url],
        base + ["--extractor-args", "youtube:player_client=android", "-f", "bv*+ba/b", url],
    ]
    last_err = ""
    for cmd in attempts:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        except FileNotFoundError:
            raise RuntimeError("Chưa cài yt-dlp. Chạy: pip install -r backend/requirements.txt")
        if proc.returncode == 0:
            break
        last_err = (proc.stderr or proc.stdout or "")[-800:]
    else:
        msg = f"Tải video thất bại: {last_err}"
        if is_bot_check_error(last_err):
            msg += f" | {bot_check_hint(cookies_from_browser)}"
        elif not _has_js_runtime():
            msg += (
                " | Thiếu JS runtime (yt-dlp cần để giải mã formats YouTube 2026): "
                "cài Deno (`brew install deno`) hoặc Node (`brew install node`) rồi thử lại."
            )
        raise RuntimeError(msg)
    files = sorted(out_dir.glob(f"{video_id}.*"))
    if not files:
        raise RuntimeError("yt-dlp chạy xong nhưng không thấy file output.")
    return files[0]
