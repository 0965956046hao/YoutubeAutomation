"""Offline API checks for analysis output language selection."""

import json
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import analyze


class AnalysisLanguageTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(analyze.router)
        self.client = TestClient(app)

    def test_title_generation_uses_selected_language_and_defaults_to_vietnamese(self):
        for language, expected in ((None, "tiếng Việt"), ("vi", "tiếng Việt"), ("en", "tiếng Anh")):
            with self.subTest(language=language):
                payload = {"title": "Original title"}
                if language is not None:
                    payload["language"] = language
                raw = json.dumps({"translation": "Translated title", "options": ["Suggested title"]})
                with patch.object(analyze.store, "load_config", return_value={}), patch(
                    "app.services.gemini.generate_with_fallback", return_value=(raw, "test-model")
                ) as generate:
                    response = self.client.post("/analyze/title-ai", json=payload)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["language"], language or "vi")
                self.assertIn(f"sang {expected}", generate.call_args.args[1])
                self.assertIn(f"options phải viết bằng {expected}", generate.call_args.args[1])

    def test_unsupported_language_is_rejected_before_generation(self):
        with patch("app.services.gemini.generate_with_fallback") as generate:
            response = self.client.post(
                "/analyze/title-ai", json={"title": "Original title", "language": "fr"}
            )
        self.assertEqual(response.status_code, 422)
        generate.assert_not_called()
