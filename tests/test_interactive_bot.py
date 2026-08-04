import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import db
from interactive_bot import (
    infer_cv_profile,
    normalize_digest_time,
    normalize_timezone,
    process_update,
    reply_for_update,
)


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
        self.assertIn("What science-related roles", reply_for_update(update("yes"))[1])
        self.assertEqual(db.get_bot_user(101)["onboarding_state"], "awaiting_target_roles")

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
        self.assertEqual(user["onboarding_state"], "awaiting_target_roles")
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

    def _create_confirmed_profile(self):
        db.start_user_onboarding(101, 202)
        db.save_user_name(101, 202, "Maya")
        db.save_user_fields(101, "Immunology")
        db.save_user_skills(101, "Flow cytometry")
        db.confirm_user_profile(101)

    def _create_complete_profile(self):
        self._create_confirmed_profile()
        db.save_target_roles(101, "Research scientist")
        db.save_preferred_locations(101, "Europe")
        db.save_work_mode(101, "Hybrid")
        db.confirm_job_preferences(101)

    def test_preferences_command_requires_science_profile(self):
        self.assertIn("create your science profile", reply_for_update(update("/preferences"))[1])

    def test_job_preferences_are_collected_and_confirmed(self):
        self._create_confirmed_profile()
        self.assertIn("countries, cities, or regions", reply_for_update(update("Postdoc and research scientist"))[1])
        self.assertIn("work arrangement", reply_for_update(update("Germany and Netherlands"))[1])
        summary = reply_for_update(update("hybrid"))[1]
        self.assertIn("Postdoc and research scientist", summary)
        self.assertIn("Germany and Netherlands", summary)
        self.assertIn("Hybrid", summary)
        self.assertIn("saved", reply_for_update(update("yes"))[1])
        user = db.get_bot_user(101)
        self.assertEqual(user["target_roles"], "Postdoc and research scientist")
        self.assertEqual(user["preferred_locations"], "Germany and Netherlands")
        self.assertEqual(user["work_mode"], "Hybrid")
        self.assertEqual(user["onboarding_state"], "complete")

    def test_invalid_work_mode_is_rejected(self):
        self._create_confirmed_profile()
        reply_for_update(update("Bioinformatician"))
        reply_for_update(update("Worldwide"))
        self.assertIn("remote, on-site, hybrid, or any", reply_for_update(update("sometimes"))[1])

    def test_rejected_preferences_restart_roles(self):
        self._create_confirmed_profile()
        reply_for_update(update("Research scientist"))
        reply_for_update(update("Anywhere"))
        reply_for_update(update("any"))
        self.assertIn("What science-related roles", reply_for_update(update("no"))[1])
        user = db.get_bot_user(101)
        self.assertIsNone(user["target_roles"])
        self.assertEqual(user["onboarding_state"], "awaiting_target_roles")

    def test_profile_command_shows_stored_data(self):
        self._create_complete_profile()
        response = reply_for_update(update("/profile"))[1]
        self.assertIn("Name: Maya", response)
        self.assertIn("Scientific fields: Immunology", response)
        self.assertIn("Target roles: Research scientist", response)
        self.assertIn("Work arrangement: Hybrid", response)

    def test_profile_command_handles_missing_user(self):
        self.assertIn("No profile is stored", reply_for_update(update("/profile"))[1])

    def test_profile_deletion_can_be_cancelled(self):
        self._create_complete_profile()
        self.assertIn("Type DELETE", reply_for_update(update("/delete_profile"))[1])
        self.assertIn("cancelled", reply_for_update(update("cancel"))[1])
        user = db.get_bot_user(101)
        self.assertEqual(user["onboarding_state"], "complete")
        self.assertEqual(user["name"], "Maya")

    def test_profile_deletion_requires_exact_confirmation(self):
        self._create_complete_profile()
        reply_for_update(update("/delete_profile"))
        self.assertIn("Type DELETE exactly", reply_for_update(update("delete"))[1])
        self.assertIsNotNone(db.get_bot_user(101))
        self.assertIn("permanently deleted", reply_for_update(update("DELETE"))[1])
        self.assertIsNone(db.get_bot_user(101))

    def test_jobs_command_requires_complete_preferences(self):
        self.assertIn("complete your science profile", reply_for_update(update("/jobs"))[1])

    def test_jobs_command_returns_ranked_catalog_results(self):
        self._create_complete_profile()
        db.save_catalog_jobs(
            [
                {
                    "company": "Example Institute",
                    "title": "Research Scientist in Immunology",
                    "location": "Europe - Hybrid",
                    "url": "https://example.org/jobs/immunology",
                    "source": "example",
                    "description": "Flow cytometry research.",
                }
            ]
        )
        response = reply_for_update(update("/jobs"))[1]
        self.assertIn("Top job matches for Maya", response)
        self.assertIn("Research Scientist in Immunology", response)
        self.assertIn("https://example.org/jobs/immunology", response)

    def test_schedule_is_collected_normalized_and_confirmed(self):
        self._create_complete_profile()
        self.assertIn("daily personalized", reply_for_update(update("/schedule"))[1])
        self.assertIn("local time", reply_for_update(update("yes"))[1])
        self.assertIn("timezone", reply_for_update(update("7:30 PM"))[1])
        summary = reply_for_update(update("Europe/Prague"))[1]
        self.assertIn("19:30", summary)
        self.assertIn("Europe/Prague", summary)
        self.assertIn("saved", reply_for_update(update("yes"))[1])
        user = db.get_bot_user(101)
        self.assertEqual(user["digest_enabled"], 1)
        self.assertEqual(user["digest_time"], "19:30")
        self.assertEqual(user["digest_timezone"], "Europe/Prague")

    def test_invalid_schedule_values_are_rejected(self):
        self._create_complete_profile()
        reply_for_update(update("/schedule"))
        reply_for_update(update("yes"))
        self.assertIn("valid time", reply_for_update(update("after dinner"))[1])
        reply_for_update(update("08:00"))
        self.assertIn("valid timezone", reply_for_update(update("Middle Earth"))[1])

    def test_pause_retains_schedule_and_profile_displays_it(self):
        self._create_complete_profile()
        db.save_digest_time(101, "08:00")
        db.save_digest_timezone(101, "Europe/Prague")
        db.confirm_digest_schedule(101)
        self.assertIn("paused", reply_for_update(update("/pause"))[1])
        user = db.get_bot_user(101)
        self.assertEqual(user["digest_enabled"], 0)
        self.assertEqual(user["digest_time"], "08:00")
        self.assertIn("Paused - daily at 08:00", reply_for_update(update("/profile"))[1])

    def test_time_and_timezone_normalizers(self):
        self.assertEqual(normalize_digest_time("7 PM"), "19:00")
        self.assertEqual(normalize_digest_time("07:15"), "07:15")
        self.assertIsNone(normalize_digest_time("tomorrow morning"))
        self.assertEqual(normalize_timezone("Prague"), "Europe/Prague")
        self.assertIsNone(normalize_timezone("Not/A_Real_Zone"))


if __name__ == "__main__":
    unittest.main()
