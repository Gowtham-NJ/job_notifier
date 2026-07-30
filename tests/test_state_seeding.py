import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main


ROOT = Path(__file__).resolve().parents[1]


class StateSeedingTests(unittest.TestCase):
    def test_legacy_state_upgrade_does_not_post_existing_jobs(self):
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            profile_path = temp / "profile.json"
            companies_path = temp / "companies.json"
            state_path = temp / "bot_state.json"
            db_path = temp / "jobs.db"
            log_path = temp / "run_log.txt"

            profile_path.write_text((ROOT / "profile.json").read_text(encoding="utf-8"), encoding="utf-8")
            companies_path.write_text(
                json.dumps(
                    [
                        {
                            "company": "Example Institute",
                            "source_type": "greenhouse",
                            "token": "example",
                            "enabled": True,
                        }
                    ]
                ),
                encoding="utf-8",
            )
            state_path.write_text(json.dumps({"initialized": True}), encoding="utf-8")

            job = {
                "company": "Example Institute",
                "title": "Postdoctoral Researcher in Computational Biophysics",
                "location": "Vienna, Austria",
                "url": "https://example.org/jobs/1",
                "description": "Molecular dynamics, QM/MM, DFT, Python and HPC.",
                "source": "greenhouse",
            }
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
                patch("main.LOG_PATH", log_path),
                patch("db.DB_PATH", db_path),
                patch("main.fetch_jobs", return_value=[job]),
                patch("main.post_job") as post_job,
            ):
                result = main.run(args)

            self.assertEqual(result, 0)
            post_job.assert_not_called()
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["state_schema"], 2)
            self.assertEqual(len(state["seeded_sources"]), 1)
            self.assertTrue(db_path.exists())


if __name__ == "__main__":
    unittest.main()
