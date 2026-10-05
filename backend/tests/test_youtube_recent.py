"""Hồi quy: đổi số ngày phải đổi kết quả; khung ngày rộng không bị cắt ở 25 video/kênh."""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.services import youtube_client


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code != 200:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeSession:
    """Giả uploads playlist: 60 video, mỗi video cách nhau 6 giờ, mới-nhất-trước."""

    def __init__(self, now):
        self.now = now
        self.published = [
            (now - timedelta(hours=6 * i)).strftime("%Y-%m-%dT%H:%M:%SZ")
            for i in range(60)
        ]

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def get(self, url, params=None):
        params = params or {}
        if "playlistItems" in url:
            max_results = int(params.get("maxResults", 50))
            start = int(params.get("pageToken", "0"))
            items = [
                {"contentDetails": {"videoId": f"vid{i:03d}", "videoPublishedAt": self.published[i]}}
                for i in range(start, min(start + max_results, len(self.published)))
            ]
            payload = {"items": items}
            if start + max_results < len(self.published):
                payload["nextPageToken"] = str(start + max_results)
            return _FakeResponse(payload)
        if url.rstrip("/").endswith("/videos"):
            out = []
            for vid in params.get("id", "").split(","):
                if not vid.startswith("vid"):
                    continue
                idx = int(vid[3:])
                out.append({
                    "id": vid,
                    "snippet": {
                        "channelId": "UCtest", "channelTitle": "Test",
                        "title": vid, "description": "", "tags": [],
                        "publishedAt": self.published[idx],
                        "thumbnails": {"medium": {"url": "http://img"}},
                    },
                    "contentDetails": {"duration": "PT1M"},
                    "statistics": {"viewCount": "1", "likeCount": "0"},
                    "status": {"privacyStatus": "public"},
                })
            return _FakeResponse({"items": out})
        if "channels" in url:
            return _FakeResponse({
                "items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UUtest"}}}],
            })
        return _FakeResponse({}, status_code=404)


class RecentVideosDaysTests(unittest.TestCase):
    def _recent(self, days):
        now = datetime.now(timezone.utc)
        with patch.object(
            youtube_client.httpx, "Client",
            side_effect=lambda **_: _FakeSession(now),
        ):
            return youtube_client.recent_videos("token", "", ["UCtest"], days=days)

    def test_wider_window_returns_more_videos(self):
        one = self._recent(1)   # cutoff 24h → video 0-3 (0, 6, 12, 18h)
        two = self._recent(2)   # cutoff 48h → video 0-7
        seven = self._recent(7)  # cutoff 168h → video 0-27
        self.assertEqual(len(one), 4)
        self.assertEqual(len(two), 8)
        self.assertEqual(len(seven), 28)
        self.assertTrue(all(
            datetime.fromisoformat(v["published_at"].replace("Z", "+00:00"))
            >= datetime.now(timezone.utc) - timedelta(days=1, minutes=5)
            for v in one
        ))

    def test_no_truncation_at_25_per_channel(self):
        # Bản cũ giới hạn 25 video/kênh nên days=7 chỉ trả 25 thay vì 28.
        seven = self._recent(7)
        self.assertEqual(len(seven), 28)
        self.assertEqual(seven[0]["video_id"], "vid000")


if __name__ == "__main__":
    unittest.main()
