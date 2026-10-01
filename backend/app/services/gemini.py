"""Gọi Gemini API (REST, không cần thêm lib) để dịch + gợi ý tiêu đề."""

import httpx

DEFAULT_MODEL = "gemini-3.1-flash-lite"
FALLBACK_MODELS = ["gemini-3.1-flash-lite", "gemini-2.5-flash"]


def _call(api_key: str, prompt: str, model: str, timeout: int) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    try:
        r = httpx.post(
            url,
            params={"key": api_key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.9, "maxOutputTokens": 1024},
            },
            timeout=timeout,
        )
    except Exception as e:
        raise RuntimeError(f"Không gọi được Gemini: {e}")
    if r.status_code != 200:
        raise RuntimeError(f"Gemini báo lỗi {r.status_code}: {r.text[:300]}")
    try:
        parts = r.json()["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts).strip()
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(f"Gemini trả về thiếu nội dung: {r.text[:300]}")


def generate(
    api_key: str,
    prompt: str,
    model: str = DEFAULT_MODEL,
    timeout: int = 90,
) -> str:
    text, _ = generate_with_fallback(api_key, prompt, model, timeout)
    return text


def generate_with_fallback(
    api_key: str,
    prompt: str,
    model: str = DEFAULT_MODEL,
    timeout: int = 90,
) -> tuple[str, str]:
    """Thử model yêu cầu, 404 (sai tên) thì tự rơi về model tồn tại. Trả (text, model đã dùng)."""
    if not api_key:
        raise RuntimeError("Chưa nhập Gemini API key. Vào tab Cấu hình để lưu.")
    candidates = [model or DEFAULT_MODEL]
    for fb in FALLBACK_MODELS:
        if fb not in candidates:
            candidates.append(fb)
    last_err: Exception | None = None
    for m in candidates:
        try:
            return _call(api_key, prompt, m, timeout), m
        except RuntimeError as e:
            if "404" not in str(e):
                raise
            last_err = e
    raise last_err or RuntimeError("Gemini: không có model nào dùng được.")
