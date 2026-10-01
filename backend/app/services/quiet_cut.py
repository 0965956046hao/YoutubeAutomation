"""Cut the beginning of a video at a nearby quiet interval, with frame accuracy."""

import json
import math
import re
from pathlib import Path

from app.services.cancellation import Cancellation, run_process


def run_media(command: list[str], timeout: int = 300, *, cancel: Cancellation | None = None) -> str:
    return run_process(command, timeout, cancel=cancel)


def probe_video(path: Path, *, cancel: Cancellation | None = None) -> dict:
    raw = run_media([
        "ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path),
    ], cancel=cancel)
    info = json.loads(raw)
    duration = float(info.get("format", {}).get("duration", 0))
    if not math.isfinite(duration) or duration <= 0:
        raise RuntimeError("Không xác định được thời lượng video.")
    if not any(s.get("codec_type") == "video" for s in info.get("streams", [])):
        raise RuntimeError("File tải về không có hình ảnh video.")
    return {"duration": duration, "has_audio": any(
        s.get("codec_type") == "audio" for s in info.get("streams", [])
    )}


def quiet_intervals(log: str, length: float) -> list[tuple[float, float]]:
    intervals = []
    start = None
    for match in re.finditer(r"silence_(start|end):\s*(-?\d+(?:\.\d+)?)", log):
        value = max(0.0, min(length, float(match[2])))
        if match[1] == "start":
            start = value
        elif start is not None:
            if value > start:
                intervals.append((start, value))
            start = None
    if start is not None and start < length:
        intervals.append((start, length))
    return intervals


def find_cut(
    path: Path, target: float, window: float, noise_db: float, min_silence: float,
    *, cancel: Cancellation | None = None,
) -> dict:
    info = probe_video(path, cancel=cancel)
    duration = info["duration"]
    if duration <= target:
        return {"seconds": duration, "source_duration": duration, "reason": "Video ngắn hơn mốc cắt: giữ toàn bộ."}
    if not info["has_audio"]:
        return {"seconds": target, "source_duration": duration, "reason": "Video không có âm thanh: cắt đúng mốc."}
    start = max(0.0, target - window)
    length = min(duration, target + window) - start
    log = run_media([
        "ffmpeg", "-hide_banner", "-nostdin", "-ss", str(start), "-i", str(path),
        "-t", str(length), "-map", "0:a:0", "-vn",
        "-af", f"silencedetect=noise={noise_db}dB:d={min_silence}", "-f", "null", "-",
    ], cancel=cancel)
    candidates = [start + (a + b) / 2 for a, b in quiet_intervals(log, length) if b - a >= min_silence]
    if not candidates:
        raise RuntimeError(
            f"Không tìm được khoảng lặng ≥ {min_silence:g}s dưới {noise_db:g} dB "
            f"trong ±{window:g}s quanh mốc cắt. Hãy tăng vùng tìm hoặc điều chỉnh ngưỡng dB."
        )
    cut = min(candidates, key=lambda value: abs(value - target))
    return {
        "seconds": round(cut, 3), "source_duration": duration,
        "reason": f"Giữa khoảng lặng dưới {noise_db:g} dB, dài ít nhất {min_silence:g}s.",
    }


def cut_video(source: Path, output: Path, seconds: float, *, cancel: Cancellation | None = None) -> None:
    # Re-encode rather than stream-copy: copying can move the cut to a keyframe.
    run_media([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(source),
        "-t", str(seconds), "-map", "0:v:0", "-map", "0:a:0?",
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-threads", "2",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", str(output),
    ], timeout=7200, cancel=cancel)
    actual = probe_video(output, cancel=cancel)["duration"]
    if abs(actual - seconds) > 1:
        raise RuntimeError("Thời lượng file đã cắt không khớp với điểm cắt đã chọn.")
