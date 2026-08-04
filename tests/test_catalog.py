import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import catalog
import db


SCIENCE_JOB = {
    "company": "Example Institute",
    "title": "Research Scientist in Immunology",
    "location": "Prague",
    "url": "https://example.org/jobs/1",
    "source": "example",
    "description": "Flow cytometry and molecular biology research.",
    "_source_key": "rss|Example Institute|https://example.org/jobs.rss",
}


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(db, "DB_PATH", Path(self.temporary.name) / "test.db")
        self.db_patch.start()
        db.init_db()

    def tearDown(self):
        self.db_patch.stop()
        self.temporary.cleanup()

    def test_science_gate_accepts_science_and_rejects_marketing(self):
        self.assertTrue(catalog.is_science_job(SCIENCE_JOB))
        self.assertFalse(
            catalog.is_science_job(
                {"title": "Sales Manager", "description": "Enterprise account marketing"}
            )
        )

    def test_catalog_upsert_preserves_one_row_and_refreshes_description(self):
        self.assertEqual(db.save_catalog_jobs([SCIENCE_JOB]), 1)
        self.assertEqual(
            db.save_catalog_jobs([dict(SCIENCE_JOB, description="Updated immunology details")]), 1
        )
        connection = db.connect()
        try:
            rows = connection.execute("SELECT * FROM job_catalog").fetchall()
        finally:
            connection.close()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["description"], "Updated immunology details")

    @patch("catalog.save_catalog_jobs")
    def test_non_persistent_catalog_filter_never_writes(self, save_catalog_jobs):
        self.assertEqual(catalog.catalog_science_jobs([SCIENCE_JOB], persist=False), 1)
        save_catalog_jobs.assert_not_called()


if __name__ == "__main__":
    unittest.main()
