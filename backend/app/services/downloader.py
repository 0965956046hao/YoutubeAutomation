"""Tải video YouTube bằng yt-dlp (nightly) vào backend/temp/videos/."""

import re
import shutil
import subprocess
from pathlib import Path

from app.config import settings

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")
_BAD_FILENAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def safe_name(name: str) -> str:
    return _SAFE.sub("_", name).strip("_")[:80] or "video"


def safe_title(name: str, max_len: int = 100) -> str:
    """Giữ nguyên Unicode (Việt/Trung) — chỉ bỏ ký tự cấm của filesystem."""
    cleaned = _BAD_FILENAME.sub(" ", name or "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
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


def download_video(video_id: str, quality: str = "best") -> Path:
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
        "yt-dlp",
        "--no-playlist",
        "--merge-output-format", "mp4",
        "--retries", "3",
        "--fragment-retries", "3",
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
        if not _has_js_runtime():
            msg += (
                " | Thiếu JS runtime (yt-dlp cần để giải mã formats YouTube 2026): "
                "cài Deno (`brew install deno`) hoặc Node (`brew install node`) rồi thử lại."
            )
        raise RuntimeError(msg)
    files = sorted(out_dir.glob(f"{video_id}.*"))
    if not files:
        raise RuntimeError("yt-dlp chạy xong nhưng không thấy file output.")
    return files[0]
