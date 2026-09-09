import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import db
import main


ROOT = Path(__file__).resolve().parents[1]


class NotifierEligibilityTests(unittest.TestCase):
    def test_initialized_notifier_excludes_training_and_experiments_without_reposting(self):
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            profile_path = temp / "profile.json"
            companies_path = temp / "companies.json"
            state_path = temp / "bot_state.json"
            source = {
                "company": "Example Institute",
                "source_type": "greenhouse",
                "token": "example",
                "enabled": True,
            }
            seeded_sources = sorted([main.source_key(source), "greenhouse|Old Institute|old"])
            initialized_at = "2025-01-01T00:00:00+00:00"
            profile_path.write_text((ROOT / "profile.json").read_text(encoding="utf-8"), encoding="utf-8")
            companies_path.write_text(json.dumps([source]), encoding="utf-8")
            state_path.write_text(
                json.dumps({
                    "initialized": True,
                    "initialized_at": initialized_at,
                    "seeded_sources": seeded_sources,
                    "state_schema": 2,
                }),
                encoding="utf-8",
            )
            matching_description = (
                "Computational chemistry and computational biophysics, molecular dynamics, "
                "QM/MM, DFT, enhanced sampling, Python, GROMACS, Linux and HPC. "
            )

            def job(number, title, description=matching_description):
                return {
                    "company": source["company"],
                    "title": title,
                    "location": "Vienna, Austria",
                    "url": f"https://example.org/jobs/{number}",
                    "description": description,
                    "source": source["source_type"],
                }

            already_seen = job(1, "Research Scientist in Computational Chemistry")
            postdoc = job(
                2,
                "Postdoctoral Researcher in Computational Biophysics",
                matching_description + "A Ph.D. in chemistry is required. You will collaborate with experimental teams.",
            )
            fetched = [
                already_seen,
                job(3, "Ph.D. Position in Computational Chemistry"),
                job(4, "Doctoral Researcher in Computational Biophysics"),
                job(5, "Experimental Research Scientist"),
                job(
                    6,
                    "Computational Chemistry Research Scientist",
                    matching_description + "This is a primarily experimental role. You will perform cell culture and protein purification.",
                ),
                postdoc,
                dict(postdoc),
            ]
            args = argparse.Namespace(
                profile=str(profile_path),
                companies=str(companies_path),
                validate=False,
                sample=None,
                dry_run=False,
                post_existing=False,
                max_posts=None,
            )

            with (
                patch("main.STATE_PATH", state_path),
                patch("main.LOG_PATH", temp / "run_log.txt"),
                patch("db.DB_PATH", temp / "jobs.db"),
                patch.dict("os.environ", {"POST_RUN_SUMMARY": "false"}),
                patch("main.fetch_jobs", return_value=fetched) as fetch_jobs,
                patch("main.post_job") as post_job,
                patch("main.post_status") as post_status,
            ):
                db.init_db()
                db.save_job(already_seen, db.make_dedup_key(already_seen), 19, "high")
                connection = db.connect()
                try:
                    original_row = dict(connection.execute("SELECT * FROM jobs").fetchone())
                finally:
                    connection.close()

                self.assertEqual(main.run(args), 0)
                post_job.assert_called_once()
                self.assertEqual(post_job.call_args.args[0]["url"], postdoc["url"])
                self.assertTrue(post_job.call_args.args[1].matched)
                first_state = json.loads(state_path.read_text(encoding="utf-8"))
                self.assertEqual(first_state["last_posted"], 1)

                self.assertEqual(main.run(args), 0)
                post_job.assert_called_once()
                post_status.assert_not_called()
                self.assertEqual(fetch_jobs.call_count, 2)
                connection = db.connect()
                try:
                    rows = [dict(row) for row in connection.execute("SELECT * FROM jobs ORDER BY id")]
                finally:
                    connection.close()

            self.assertEqual(rows[0], original_row)
            self.assertEqual([row["url"] for row in rows], [already_seen["url"], postdoc["url"]])
            final_state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertTrue(final_state["initialized"])
            self.assertEqual(final_state["initialized_at"], initialized_at)
            self.assertEqual(final_state["seeded_sources"], seeded_sources)
            self.assertEqual(final_state["last_matched"], 2)
            self.assertEqual(final_state["last_posted"], 0)


if __name__ == "__main__":
    unittest.main()
