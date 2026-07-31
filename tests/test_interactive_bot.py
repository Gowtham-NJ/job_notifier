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
        reply = reply_for_update(update("  Maya  Patel "))
        self.assertIn("Nice to meet you, Maya Patel", reply[1])
        user = db.get_bot_user(101)
        self.assertEqual(user["name"], "Maya Patel")
        self.assertEqual(user["onboarding_state"], "awaiting_fields")

    def test_returning_user_gets_personal_greeting(self):
        reply_for_update(update("/start"))
        reply_for_update(update("Maya"))
        self.assertIn("Welcome back, Maya", reply_for_update(update("/start"))[1])

    def test_phase_one_user_continues_with_fields(self):
        db.start_user_onboarding(101, 202)
        db.save_user_name(101, 202, "Maya")
        connection = db.connect()
        try:
            connection.execute(
                "UPDATE bot_users SET onboarding_state = 'complete' WHERE telegram_user_id = 101"
            )
            connection.commit()
        finally:
            connection.close()
        self.assertIn("Which scientific fields", reply_for_update(update("/start"))[1])
        self.assertEqual(db.get_bot_user(101)["onboarding_state"], "awaiting_fields")

    def test_science_profile_is_collected_and_confirmed(self):
        reply_for_update(update("/start"))
        reply_for_update(update("Maya"))
        self.assertIn("skills", reply_for_update(update("Immunology and molecular biology"))[1])
        summary = reply_for_update(update("Flow cytometry, cell culture, Python"))[1]
        self.assertIn("Immunology and molecular biology", summary)
        self.assertIn("Flow cytometry, cell culture, Python", summary)
        self.assertEqual(reply_for_update(update("yes"))[1], "Your science profile is saved! ✅")
        self.assertEqual(db.get_bot_user(101)["onboarding_state"], "complete")

    def test_non_science_field_is_rejected(self):
        reply_for_update(update("/start"))
        reply_for_update(update("Maya"))
        reply = reply_for_update(update("retail sales and marketing"))[1]
        self.assertIn("only for science-related jobs", reply)
        self.assertEqual(db.get_bot_user(101)["onboarding_state"], "awaiting_fields")

    def test_no_restarts_field_and_skill_collection(self):
        reply_for_update(update("/start"))
        reply_for_update(update("Maya"))
        reply_for_update(update("Bioinformatics"))
        reply_for_update(update("Python and RNA sequencing"))
        self.assertIn("Which scientific fields", reply_for_update(update("no"))[1])
        user = db.get_bot_user(101)
        self.assertIsNone(user["science_fields"])
        self.assertIsNone(user["skills"])

    def test_non_message_update_is_ignored(self):
        self.assertIsNone(reply_for_update({"update_id": 2}))


if __name__ == "__main__":
    unittest.main()
