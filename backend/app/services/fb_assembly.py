"""Ghép intro cover + outro template YouTube vào video của Facebook flow.

Luồng sau khi cắt (30p):
1. Chuẩn hoá ảnh bìa về đúng 1088×1446 (ưu tiên ảnh ChatGPT đã gen cho
   video này, fallback upscale thumbnail YouTube gốc bằng FFmpeg).
2. Chèn cover vào ĐẦU video (mặc định 1s): giữ nguyên tỉ lệ, căn giữa,
   nền đen lấp phần thừa (scale+crop của FFmpeg, không méo hình).
3. Thêm OUTRO template ở CUỐI video: ảnh nền render từ PIL gồm thumbnail
   + tên kênh + tên video YouTube (không dán đường dẫn) để người xem
   tìm tới bản gốc trên YouTube.

Nếu user chưa kịp gen cover bằng ChatGPT, flow tự dùng thumbnail gốc
upscale để không kẹt hàng đợi — không bao giờ block worker.
"""

from pathlib import Path
from typing import Callable

from app.services.cancellation import Cancellation
from app.services.quiet_cut import probe_video, run_media

COVER_W, COVER_H = 1088, 1446

COVER_PROMPT_DEFAULT = (
    "Làm rõ nét hình ảnh, giữ lại thông tin Phần ở góc trên phải, "
    "chỉnh tỉ lệ hình thành 1088 × 1446"
)

_FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)


def _font(size: int, *, bold: bool = False):
    """Font hỗ trợ tiếng Việt; fallback font mặc định của PIL."""
    from PIL import ImageFont

    for path in _FONT_CANDIDATES:
        if bold and "Bold" not in path and "Arial Unicode" not in path:
            continue
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow cũ không có tham số size.
        return ImageFont.load_default()


def analyzed_cover(video_id: str, temp_dir: Path) -> Path | None:
    """Ảnh ChatGPT đã gen cho video (slot cover trước, thumbnail 16:9 sau)."""
    for name in (f"{video_id}.cover.png", f"{video_id}.generated.png"):
        path = temp_dir / "analyzed" / name
        if path.is_file() and path.stat().st_size > 1000:
            return path
    return None


def ensure_cover(source: Path, cover_path: Path, *, cancel: Cancellation | None = None) -> Path:
    """Chuẩn hoá ảnh bìa về đúng 1088×1446 (scale lấp đầy + crop giữa)."""
    if cancel:
        cancel.check()
    if not source.is_file():
        raise RuntimeError("Không tìm thấy ảnh nguồn để tạo cover.")
    cover_path.parent.mkdir(parents=True, exist_ok=True)
    run_media([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(source),
        "-vf", (f"scale={COVER_W}:{COVER_H}:force_original_aspect_ratio=increase,"
                f"crop={COVER_W}:{COVER_H},setsar=1,format=yuv420p"),
        "-frames:v", "1", "-q:v", "3", str(cover_path),
    ], timeout=300, cancel=cancel)
    return cover_path


def _dims(path: Path, *, cancel: Cancellation | None = None) -> tuple[int, int, float, bool]:
    import json

    raw = run_media([
        "ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path),
    ], timeout=60, cancel=cancel)
    info = json.loads(raw)
    video = next(s for s in info.get("streams", []) if s.get("codec_type") == "video")
    width, height = int(video["width"]), int(video["height"])
    num, den = (video.get("avg_frame_rate") or "30/1").split("/")
    fps = float(num) / float(den) if float(den or 0) else 30.0
    if not (15 <= fps <= 120):
        fps = 30.0
    has_audio = any(s.get("codec_type") == "audio" for s in info.get("streams", []))
    return width, height, fps, has_audio


def _still_segment(
    image: Path, output: Path, width: int, height: int, fps: float, seconds: float,
    *, from_cover: bool, cancel: Cancellation | None = None,
) -> None:
    """Dựng đoạn video tĩnh từ ảnh, khớp kích thước/fps/audio với clip chính.

    from_cover=True: giữ tỉ lệ + căn giữa (scale vừa khít + pad đen).
    from_cover=False: ảnh outro đã render đúng W×H nên scale thẳng.
    """
    if from_cover:
        vf = (f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
              f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
              f"setsar=1,format=yuv420p,fps={fps:g}")
    else:
        vf = f"scale={width}:{height},setsar=1,format=yuv420p,fps={fps:g}"
    run_media([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-loop", "1", "-i", str(image),
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", str(seconds), "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
        "-c:a", "aac", "-b:a", "128k", "-shortest",
        "-movflags", "+faststart", str(output),
    ], timeout=600, cancel=cancel)


def make_outro_image(
    thumbnail: Path | None, channel: str, title: str, out_path: Path,
    width: int = 1280, height: int = 720,
) -> Path:
    """Render template outro: thumbnail + tên kênh + tên video YT (không URL)."""
    import textwrap

    from PIL import Image, ImageDraw, ImageOps

    out_path.parent.mkdir(parents=True, exist_ok=True)
    scale = min(width / 1280, height / 720)
    img = Image.new("RGB", (width, height), (16, 16, 16))
    draw = ImageDraw.Draw(img)
    # Vạch đỏ YouTube trên cùng.
    draw.rectangle([0, 0, width, max(4, int(10 * scale))], fill=(255, 0, 51))

    margin = int(48 * scale)
    thumb_w = int(width * 0.40)
    thumb_h = int(thumb_w * 9 / 16)
    thumb_y = (height - thumb_h) // 2
    if thumbnail and thumbnail.is_file():
        try:
            thumb = ImageOps.fit(Image.open(thumbnail).convert("RGB"), (thumb_w, thumb_h))
            img.paste(thumb, (margin, thumb_y))
        except OSError:
            draw.rectangle([margin, thumb_y, margin + thumb_w, thumb_y + thumb_h],
                           outline=(80, 80, 80), width=2)
    else:
        draw.rectangle([margin, thumb_y, margin + thumb_w, thumb_y + thumb_h],
                       outline=(80, 80, 80), width=2)

    x = margin + thumb_w + int(40 * scale)
    max_w = width - x - margin
    y = thumb_y + int(6 * scale)
    heading = _font(int(34 * scale), bold=True)
    draw.text((x, y), "XEM FULL TRÊN YOUTUBE", font=heading, fill=(255, 0, 51))
    y += int(52 * scale)

    channel = (channel or "").strip() or "Kênh YouTube"
    title = (title or "").strip() or "Video gốc trên YouTube"
    normal = _font(int(30 * scale))
    small = _font(int(26 * scale))

    def wrapped(text: str, font, width_px: int, max_lines: int) -> list[str]:
        words, lines, line = text.split(), [], ""
        for word in words:
            trial = f"{line} {word}".strip()
            if draw.textlength(trial, font=font) <= width_px:
                line = trial
            else:
                if line:
                    lines.append(line)
                line = word
                if len(lines) >= max_lines:
                    break
        if line and len(lines) < max_lines + 1:
            lines.append(line)
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            lines[-1] = lines[-1].rstrip() + "…"
        return lines or [""]

    for line in wrapped(f"Kênh: {channel}", normal, max_w, 2):
        draw.text((x, y), line, font=normal, fill=(255, 255, 255))
        y += int(40 * scale)
    y += int(8 * scale)
    for line in wrapped(title, normal, max_w, 4):
        draw.text((x, y), line, font=normal, fill=(255, 213, 79))
        y += int(40 * scale)
    y += int(10 * scale)
    hint = "Mở YouTube và tìm tên kênh hoặc tên video trên để xem bản đầy đủ."
    for line in textwrap.wrap(hint, width=44):
        draw.text((x, y), line, font=small, fill=(170, 170, 170))
        y += int(34 * scale)

    img.save(out_path, quality=92)
    return out_path


def assemble_intro_outro(
    clip: Path, directory: Path, *, video_id: str, temp_dir: Path,
    channel: str, title: str, thumbnail: Path,
    intro_seconds: float = 1.0, outro_seconds: float = 5.0,
    cancel: Cancellation | None = None,
    on_step: Callable[[str], None] | None = None,
) -> dict:
    """Chuẩn hoá cover, dựng intro/outro và nối thành clip cuối. Trả về metadata."""
    def say(message: str) -> None:
        if on_step:
            on_step(message)

    if cancel:
        cancel.check()
    intro_seconds = min(10.0, max(0.5, float(intro_seconds or 1.0)))
    outro_seconds = min(15.0, max(2.0, float(outro_seconds or 5.0)))

    say("Đang chuẩn hoá ảnh bìa 1088×1446…")
    ai_cover = analyzed_cover(video_id, temp_dir)
    if ai_cover:
        say("Đã dùng ảnh bìa ChatGPT đã gen, chuẩn hoá 1088×1446…")
        cover_src = ai_cover
    else:
        say("Chưa có ảnh bìa ChatGPT — upscale thumbnail gốc để không kẹt flow…")
        cover_src = thumbnail
    cover = ensure_cover(cover_src, directory / "cover.jpg", cancel=cancel)

    say("Đang dựng intro cover + outro YouTube…")
    width, height, fps, has_audio = _dims(clip, cancel=cancel)
    intro = directory / "intro.mp4"
    _still_segment(cover, intro, width, height, fps, intro_seconds,
                   from_cover=True, cancel=cancel)
    outro_img = make_outro_image(
        thumbnail if thumbnail.is_file() else None, channel, title,
        directory / "outro.jpg", width, height,
    )
    outro = directory / "outro.mp4"
    _still_segment(outro_img, outro, width, height, fps, outro_seconds,
                   from_cover=False, cancel=cancel)

    say("Đang nối intro + clip + outro…")
    final = directory / "final.mp4"
    if has_audio:
        filt = ("[0:v]setsar=1,format=yuv420p[v0];[0:a]aresample=44100,"
                "aformat=sample_fmts=fltp:channel_layouts=stereo[a0];"
                "[1:v]setsar=1,format=yuv420p,fps={fps}[v1];[1:a]aresample=44100,"
                "aformat=sample_fmts=fltp:channel_layouts=stereo[a1];"
                "[2:v]setsar=1,format=yuv420p[v2];[2:a]aresample=44100,"
                "aformat=sample_fmts=fltp:channel_layouts=stereo[a2];"
                "[v0][a0][v1][a1][v2][a2]concat=n=3:v=1:a=1[v][a]".format(fps=fps))
        audio_args = ["-map", "[a]", "-c:a", "aac", "-b:a", "192k"]
    else:
        filt = ("[0:v]setsar=1,format=yuv420p[v0];"
                "[1:v]setsar=1,format=yuv420p,fps={fps}[v1];"
                "[2:v]setsar=1,format=yuv420p[v2];"
                "[v0][v1][v2]concat=n=3:v=1:a=0[v]".format(fps=fps))
        audio_args = ["-an"]
    run_media([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-i", str(intro), "-i", str(clip), "-i", str(outro),
        "-filter_complex", filt, "-map", "[v]", *audio_args,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(final),
    ], timeout=7200, cancel=cancel)

    duration = probe_video(final, cancel=cancel)["duration"]
    expected = probe_video(clip, cancel=cancel)["duration"] + intro_seconds + outro_seconds
    if abs(duration - expected) > 2:
        raise RuntimeError("Ghép intro/outro xong nhưng thời lượng lệch bất thường.")
    for path in (intro, outro):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    final.replace(clip)
    return {
        "intro_seconds": intro_seconds, "outro_seconds": outro_seconds,
        "duration": duration, "cover_ai": bool(ai_cover),
        "width": width, "height": height,
    }
