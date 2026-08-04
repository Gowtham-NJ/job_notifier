import unittest

from matching import find_matching_jobs, score_catalog_job


USER = {
    "science_fields": "Immunology, molecular biology",
    "skills": "Flow cytometry, Python, cell culture",
    "target_roles": "Postdoc, research scientist",
    "preferred_locations": "Germany, Netherlands",
    "work_mode": "Hybrid",
}


class PersonalizedMatchingTests(unittest.TestCase):
    def test_relevant_job_scores_with_explainable_reasons(self):
        job = {
            "title": "Postdoc in Immunology",
            "description": "Flow cytometry and cell culture research.",
            "location": "Berlin, Germany - Hybrid",
        }
        match = score_catalog_job(job, USER)
        self.assertIsNotNone(match)
        self.assertGreaterEqual(match.score, 15)
        self.assertTrue(any("target role" in reason for reason in match.reasons))
        self.assertTrue(any("preferred location" in reason for reason in match.reasons))

    def test_irrelevant_science_job_is_rejected(self):
        job = {
            "title": "Quantum Materials Engineer",
            "description": "Condensed matter physics and semiconductor fabrication.",
            "location": "Tokyo",
        }
        self.assertIsNone(score_catalog_job(job, USER))

    def test_best_match_ranks_first_and_limit_is_respected(self):
        jobs = [
            {
                "title": "Research Scientist in Immunology",
                "description": "Flow cytometry and cell culture",
                "location": "Amsterdam, Netherlands - Hybrid",
            },
            {
                "title": "Postdoc in Molecular Biology",
                "description": "Laboratory research",
                "location": "Canada",
            },
            {
                "title": "Research Scientist in Neuroscience",
                "description": "Python data analysis",
                "location": "France",
            },
        ]
        matches = find_matching_jobs(USER, jobs, limit=2)
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].job["title"], "Research Scientist in Immunology")


if __name__ == "__main__":
    unittest.main()
