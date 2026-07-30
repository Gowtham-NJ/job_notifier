import unittest

from main import runtime_fingerprint, source_key


class MainTests(unittest.TestCase):
    def test_source_key_is_stable(self):
        source = {
            "company": "ResearchJobs.cz",
            "source_type": "researchjobs_cz",
            "url": "https://www.researchjobs.cz/jobs/",
        }
        self.assertEqual(
            source_key(source),
            "researchjobs_cz|ResearchJobs.cz|https://www.researchjobs.cz/jobs/",
        )

    def test_runtime_fingerprint_ignores_tracking_url(self):
        first = {
            "source": "ccl.net",
            "company": "CCL.NET Jobs",
            "title": "Postdoc in Computational Chemistry",
            "location": "",
            "url": "https://example.org/a",
        }
        second = dict(first, url="https://example.org/b", source="jobrxiv")
        self.assertEqual(runtime_fingerprint(first), runtime_fingerprint(second))


if __name__ == "__main__":
    unittest.main()
