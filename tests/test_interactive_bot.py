import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import db
from interactive_bot import reply_for_update


def update(text: str, user_id: int = 101, chat_id: int = 202) -> dict:
    return {
        "update_id": 1,
        "message": {
            "text": text,
            "from": {"id": user_id},
            "chat": {"id": chat_id, "type": "private"},
        },
    }


class InteractiveBotTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(db, "DB_PATH", Path(self.temporary.name) / "test.db")
        self.db_patch.start()
        db.init_db()

    def tearDown(self):
        self.db_patch.stop()
        self.temporary.cleanup()

    def test_start_asks_for_name_and_saves_state(self):
        self.assertEqual(reply_for_update(update("/start")), (202, "Hello! 👋 What should I call you?"))
        self.assertEqual(db.get_bot_user(101)["onboarding_state"], "awaiting_name")

    def test_name_is_saved_and_greeted(self):
        reply_for_update(update("/start"))
        self.assertEqual(reply_for_update(update("  Maya  Patel ")), (202, "Nice to meet you, Maya Patel! 🎉"))
        user = db.get_bot_user(101)
        self.assertEqual(user["name"], "Maya Patel")
        self.assertEqual(user["onboarding_state"], "complete")

    def test_returning_user_gets_personal_greeting(self):
        reply_for_update(update("/start"))
        reply_for_update(update("Maya"))
        self.assertEqual(reply_for_update(update("/start")), (202, "Welcome back, Maya! 👋"))

    def test_non_message_update_is_ignored(self):
        self.assertIsNone(reply_for_update({"update_id": 2}))


if __name__ == "__main__":
    unittest.main()
