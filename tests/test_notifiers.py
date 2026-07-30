import unittest
from types import SimpleNamespace

from notifiers import _discord_payload, _slack_payload, _telegram_text


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


if __name__ == "__main__":
    unittest.main()
