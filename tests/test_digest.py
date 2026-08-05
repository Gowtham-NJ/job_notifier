import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import db
from digest import local_schedule_status, run_digest, select_new_matches
from matching import PersonalizedMatch


class DigestTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(db, "DB_PATH", Path(self.temporary.name) / "test.db")
        self.db_patch.start()
        db.init_db()
        db.start_user_onboarding(101, 202)
        db.save_user_name(101, 202, "Maya")
        db.save_user_fields(101, "Immunology")
        db.save_user_skills(101, "Flow cytometry")
        db.confirm_user_profile(101)
        db.save_target_roles(101, "Research scientist")
        db.save_preferred_locations(101, "Europe")
        db.save_work_mode(101, "Hybrid")
        db.confirm_job_preferences(101)
        db.save_digest_time(101, "08:30")
        db.save_digest_timezone(101, "Europe/Prague")
        db.confirm_digest_schedule(101)
        db.save_catalog_jobs(
            [
                {
                    "company": "Example Institute",
                    "title": "Research Scientist in Immunology",
                    "location": "Europe - Hybrid",
                    "url": "https://example.org/job/1",
                    "source": "example",
                    "description": "Flow cytometry research",
                }
            ]
        )

    def tearDown(self):
        self.db_patch.stop()
        self.temporary.cleanup()

    def test_due_check_uses_user_timezone_and_local_date(self):
        user = db.get_bot_user(101)
        due, local_date = local_schedule_status(
            user, dt.datetime(2026, 8, 4, 6, 30, tzinfo=dt.timezone.utc)
        )
        self.assertTrue(due)
        self.assertEqual(local_date, "2026-08-04")

    @patch("digest._post_json")
    def test_default_dry_run_never_sends_or_records(self, post):
        result = run_digest(
            now_utc=dt.datetime(2026, 8, 4, 6, 30, tzinfo=dt.timezone.utc)
        )
        post.assert_not_called()
        self.assertEqual(result["matches"], 1)
        self.assertFalse(db.delivered_job_keys(101))

    @patch("digest.validate_telegram_config", return_value=("123:test", "202"))
    @patch("digest._post_json")
    def test_scheduled_send_records_delivery_and_prevents_repeat(self, post, _validate):
        now = dt.datetime(2026, 8, 4, 6, 30, tzinfo=dt.timezone.utc)
        first = run_digest(send=True, now_utc=now)
        second = run_digest(send=True, now_utc=now)
        self.assertEqual(first["sent"], 1)
        self.assertEqual(second["due"], 0)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(len(db.delivered_job_keys(101)), 1)

    @patch("digest.validate_telegram_config", return_value=("123:test", "202"))
    @patch("digest._post_json")
    def test_single_user_test_send_does_not_record_delivery(self, post, _validate):
        result = run_digest(send=True, test_user_id=101)
        self.assertEqual(result["sent"], 1)
        post.assert_called_once()
        self.assertFalse(db.delivered_job_keys(101))

    def test_duplicate_vacancy_urls_are_collapsed_and_all_keys_recordable(self):
        first = PersonalizedMatch(
            job={
                "dedup_key": "url-a",
                "company": "Example Institute",
                "title": "Postdoc in Immunology",
                "location": "Prague",
            },
            score=10,
            reasons=("target role",),
        )
        second = PersonalizedMatch(
            job={
                "dedup_key": "url-b",
                "company": "Example Institute",
                "title": "Postdoc in Immunology",
                "location": "Prague",
            },
            score=9,
            reasons=("target role",),
        )
        selected, keys = select_new_matches([first, second], set())
        self.assertEqual(len(selected), 1)
        self.assertEqual(set(keys), {"url-a", "url-b"})
        selected_again, _ = select_new_matches([first, second], {"url-b"})
        self.assertEqual(selected_again, [])


if __name__ == "__main__":
    unittest.main()
