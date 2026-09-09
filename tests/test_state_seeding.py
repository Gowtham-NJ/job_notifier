import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main
import db


ROOT = Path(__file__).resolve().parents[1]


class StateSeedingTests(unittest.TestCase):
    def test_new_portal_seeds_existing_matches_then_only_posts_new_eligible_jobs(self):
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            source = {
                "company": "New Academic Portal",
                "source_type": "rss",
                "url": "https://example.org/jobs.rss",
                "enabled": True,
            }
            companies_path = temp / "companies.json"
            companies_path.write_text(json.dumps([source]), encoding="utf-8")
            state_path = temp / "state.json"
            old_source = "rss|Existing Portal|https://example.org/old.rss"
            state_path.write_text(json.dumps({
                "initialized": True,
                "state_schema": 2,
                "seeded_sources": [old_source],
            }), encoding="utf-8")
            existing = {
                "company": "Example University",
                "title": "Postdoc in Computational Chemistry",
                "description": "Molecular dynamics, DFT, Python and HPC. PhD required.",
                "location": "Prague",
                "url": "https://example.org/job/existing",
                "source": "rss",
            }
            new_job = dict(existing, url="https://example.org/job/new", title="Research Scientist in Computational Chemistry")
            phd_job = dict(existing, url="https://example.org/job/phd", title="Ph.D. Researcher in Computational Chemistry")
            experimental = dict(existing, url="https://example.org/job/experimental", title="Experimental Research Scientist")
            args = argparse.Namespace(
                profile=str(ROOT / "profile.json"), companies=str(companies_path),
                validate=False, sample=None, dry_run=False, post_existing=False, max_posts=None,
            )
            with (
                patch("main.STATE_PATH", state_path),
                patch("main.LOG_PATH", temp / "log.txt"),
                patch("db.DB_PATH", temp / "jobs.db"),
                patch("main.fetch_jobs", side_effect=[
                    [existing, phd_job, experimental],
                    [existing, new_job, phd_job, experimental],
                ]),
                patch("main.post_job") as post_job,
                patch("main.post_status"),
                patch("builtins.print"),
            ):
                self.assertEqual(main.run(args), 0)
                post_job.assert_not_called()
                self.assertTrue(db.job_exists(db.make_dedup_key(existing)))
                self.assertEqual(main.run(args), 0)
                post_job.assert_called_once()
                self.assertEqual(post_job.call_args.args[0]["url"], new_job["url"])
                self.assertFalse(db.job_exists(db.make_dedup_key(phd_job)))
                self.assertFalse(db.job_exists(db.make_dedup_key(experimental)))
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(set(state["seeded_sources"]), {old_source, main.source_key(source)})

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
            with patch("db.DB_PATH", db_path):
                database = db.connect()
                try:
                    catalog_count = database.execute("SELECT COUNT(*) FROM job_catalog").fetchone()[0]
                finally:
                    database.close()
            self.assertEqual(catalog_count, 1)


if __name__ == "__main__":
    unittest.main()
