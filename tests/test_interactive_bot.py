import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import db
from interactive_bot import infer_cv_profile, process_update, reply_for_update


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

    def test_cv_command_requests_pdf(self):
        self.assertIn("Upload your CV", reply_for_update(update("/cv"))[1])

    @patch(
        "interactive_bot.extract_pdf_text",
        return_value="Maya Patel\nPhD in Immunology\nFlow cytometry, cell culture, Python",
    )
    @patch("interactive_bot.requests.get")
    def test_pdf_cv_is_downloaded_and_profile_is_inferred(self, get, extract):
        metadata = unittest.mock.Mock()
        metadata.json.return_value = {"result": {"file_path": "documents/cv.pdf"}}
        downloaded = unittest.mock.Mock(content=b"%PDF-test")
        get.side_effect = [metadata, downloaded]
        pdf_update = {
            "message": {
                "from": {"id": 101},
                "chat": {"id": 202},
                "document": {
                    "file_id": "safe-file-id",
                    "file_name": "cv.pdf",
                    "mime_type": "application/pdf",
                    "file_size": 1000,
                },
            }
        }
        response = process_update(pdf_update, "test-token")
        self.assertIn("Name: Maya Patel", response[1])
        self.assertIn("Fields: Immunology", response[1])
        self.assertIn("Flow cytometry", response[1])
        self.assertIn("Current/recent career stage: PhD", response[1])
        self.assertIn("raw text were not saved", response[1])
        extract.assert_called_once_with(b"%PDF-test")
        self.assertEqual(db.get_bot_user(101)["onboarding_state"], "awaiting_cv_confirmation")

    def test_cv_draft_can_be_confirmed(self):
        db.save_cv_profile_draft(
            101, 202, "Maya Patel", "Immunology", "Flow cytometry, Python", "PhD"
        )
        self.assertIn("saved", reply_for_update(update("yes"))[1])
        user = db.get_bot_user(101)
        self.assertEqual(user["name"], "Maya Patel")
        self.assertEqual(user["science_fields"], "Immunology")
        self.assertEqual(user["skills"], "Flow cytometry, Python")
        self.assertEqual(user["career_stage"], "PhD")
        self.assertEqual(user["onboarding_state"], "complete")
        self.assertIsNone(user["cv_draft_fields"])

    def test_rejected_cv_draft_uses_manual_flow(self):
        db.save_cv_profile_draft(
            101, 202, "Maya Patel", "Immunology", "Flow cytometry", "PhD"
        )
        self.assertIn("What should I call you", reply_for_update(update("no"))[1])
        self.assertEqual(db.get_bot_user(101)["onboarding_state"], "awaiting_name")

    def test_cv_profile_inference_is_deterministic(self):
        draft = infer_cv_profile(
            "Alex Morgan\nPostdoctoral researcher in molecular biology and bioinformatics. "
            "Experienced with RNA-seq, CRISPR, Python, and machine learning."
        )
        self.assertEqual(draft["name"], "Alex Morgan")
        self.assertIn("Molecular biology", draft["fields"])
        self.assertIn("Bioinformatics", draft["fields"])
        self.assertIn("RNA sequencing", draft["skills"])
        self.assertEqual(draft["career_stage"], "Postdoctoral")

    def test_non_pdf_cv_is_rejected(self):
        file_update = {
            "message": {
                "from": {"id": 101},
                "chat": {"id": 202},
                "document": {
                    "file_id": "file-id",
                    "file_name": "cv.docx",
                    "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "file_size": 1000,
                },
            }
        }
        self.assertIn("as a PDF", process_update(file_update, "test-token")[1])

    def test_oversized_pdf_is_rejected_before_download(self):
        file_update = {
            "message": {
                "from": {"id": 101},
                "chat": {"id": 202},
                "document": {
                    "file_id": "file-id",
                    "file_name": "cv.pdf",
                    "mime_type": "application/pdf",
                    "file_size": 9 * 1024 * 1024,
                },
            }
        }
        self.assertIn("smaller than 8 MB", process_update(file_update, "test-token")[1])


if __name__ == "__main__":
    unittest.main()
