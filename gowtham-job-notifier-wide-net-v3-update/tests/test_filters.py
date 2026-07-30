import json
import unittest
from pathlib import Path

from filters import evaluate_job


ROOT = Path(__file__).resolve().parents[1]
PROFILE = json.loads((ROOT / "profile.json").read_text(encoding="utf-8"))


class FilterTests(unittest.TestCase):
    def test_high_match(self):
        result = evaluate_job(
            {
                "title": "Postdoctoral Researcher in Computational Biophysics",
                "description": "Molecular dynamics, GROMACS, QM/MM, DFT, Python and HPC.",
                "location": "Vienna, Austria",
            },
            PROFILE,
        )
        self.assertTrue(result.matched)
        self.assertEqual(result.priority, "high")

    def test_sales_role_is_blocked(self):
        result = evaluate_job(
            {
                "title": "Account Manager, Strategic",
                "description": "Computational chemistry software",
                "location": "Germany",
            },
            PROFILE,
        )
        self.assertFalse(result.matched)

    def test_leadership_role_is_blocked(self):
        result = evaluate_job(
            {
                "title": "Team Leader, Computational Drug Design",
                "description": "Computational chemistry and molecular modeling",
                "location": "London, UK",
            },
            PROFILE,
        )
        self.assertFalse(result.matched)

    def test_worldwide_location_is_retained(self):
        result = evaluate_job(
            {
                "title": "Research Scientist, Molecular Dynamics",
                "description": "Computational chemistry and HPC",
                "location": "Toronto, Canada",
            },
            PROFILE,
        )
        self.assertTrue(result.matched)
        self.assertTrue(result.location_ok)

    def test_unknown_location_is_retained(self):
        result = evaluate_job(
            {
                "title": "Postdoctoral Fellow in Electron Transfer",
                "description": "Molecular dynamics, DFT, QM/MM and protein-metal interfaces",
                "location": "",
            },
            PROFILE,
        )
        self.assertTrue(result.matched)
        self.assertTrue(result.location_ok)

    def test_senior_role_priority_is_capped(self):
        job = {
            "title": "Principal Scientist, Computational Chemistry",
            "description": "Molecular dynamics, DFT, Python, GROMACS and drug discovery",
            "location": "Germany",
        }
        result = evaluate_job(job, PROFILE)
        self.assertTrue(result.matched)
        self.assertEqual(result.seniority, "senior")
        self.assertEqual(result.priority, "standard")


if __name__ == "__main__":
    unittest.main()
