import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

from notifiers import (
    _discord_payload,
    _slack_payload,
    _telegram_text,
    validate_telegram_config,
    validate_telegram_connection,
    _safe_error,
)


JOB = {
    "title": "Postdoc in Computational Chemistry",
    "company": "Example University",
    "location": "Vienna, Austria",
    "url": "https://example.org/job/1",
    "source": "example",
}
MATCH = SimpleNamespace(
    priority="high",
    score=18,
    seniority="postdoc",
    reasons=("molecular dynamics (+1)", "DFT (+1)"),
)


class NotifierTests(unittest.TestCase):
    def test_slack_payload_has_button(self):
        payload = _slack_payload(JOB, MATCH)
        self.assertEqual(payload["blocks"][-1]["type"], "actions")

    def test_discord_payload_has_embed(self):
        payload = _discord_payload(JOB, MATCH)
        self.assertEqual(payload["embeds"][0]["url"], JOB["url"])

    def test_telegram_payload_has_clickable_link(self):
        text = _telegram_text(JOB, MATCH)
        self.assertIn("<a href=", text)
        self.assertIn("Computational Chemistry", text)

    def test_telegram_config_requires_both_values(self):
        with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": ""}, clear=False):
            with self.assertRaisesRegex(ValueError, "TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID"):
                validate_telegram_config()

    def test_telegram_config_rejects_bad_chat_id(self):
        with patch.dict(
            "os.environ",
            {"TELEGRAM_BOT_TOKEN": "123456:valid_token", "TELEGRAM_CHAT_ID": "@channel"},
            clear=False,
        ):
            with self.assertRaisesRegex(ValueError, "numeric"):
                validate_telegram_config()

    @patch("notifiers.requests.get")
    def test_telegram_connection_check_does_not_send(self, get):
        get.side_effect = [
            Mock(status_code=200, json=lambda: {"ok": True, "result": {"username": "jobs_bot"}}),
            Mock(status_code=200, json=lambda: {"ok": True, "result": {"id": 42}}),
        ]
        with patch.dict(
            "os.environ",
            {"TELEGRAM_BOT_TOKEN": "123456:valid_token", "TELEGRAM_CHAT_ID": "42"},
            clear=False,
        ):
            result = validate_telegram_connection()
        self.assertIn("@jobs_bot", result)
        self.assertEqual(get.call_count, 2)

    def test_errors_redact_telegram_token(self):
        token = "123456:do_not_log_this"
        with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": token}, clear=False):
            message = _safe_error(f"request failed at /bot{token}/sendMessage")
        self.assertNotIn(token, message)
        self.assertIn("[REDACTED]", message)


if __name__ == "__main__":
    unittest.main()
