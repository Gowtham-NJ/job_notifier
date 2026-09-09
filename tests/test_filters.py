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

    def test_applied_llm_role_is_blocked(self):
        result = evaluate_job(
            {
                "title": "Research Scientist, Applied LLMs",
                "description": "Drug discovery, NumPy, SciPy and computational chemistry context.",
                "location": "London, UK",
            },
            PROFILE,
        )
        self.assertFalse(result.matched)

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

    def test_doctoral_title_variants_are_hard_exclusions(self):
        for title in (
            "PhD Researcher in Computational Chemistry",
            "PhD Research Assistant in Computational Chemistry",
            "Ph.D. position in Molecular Simulation",
            "P.h.D. Fellow in Computational Biophysics",
            "Doctoral researcher in Computational Chemistry",
            "Doctoral Research Fellow in Molecular Simulation",
            "Pre-doctoral Fellow in Computational Chemistry",
            "Fully funded PhD: Computational Chemistry",
            "PhD (f/m/d) in Computational Chemistry",
            "PhD – Computational Biophysics",
            "PhD Candidate in Computational Chemistry",
            "Doctoral Studentship in Molecular Simulation",
        ):
            with self.subTest(title=title):
                match = evaluate_job({
                    "title": title,
                    "description": "Molecular dynamics, DFT, QM/MM, Python, HPC and computational chemistry.",
                    "location": "Germany - Remote",
                }, PROFILE)
                self.assertFalse(match.matched)
                self.assertIn("doctoral", match.reasons[0])

    def test_doctoral_enrolment_in_generic_role_is_excluded(self):
        for description in (
            "You will enroll in a Ph.D. programme and develop molecular dynamics simulations.",
            "The successful candidate must register for a doctoral degree in computational chemistry.",
            "Applicants must be enrolled in a doctoral programme in computational chemistry.",
            "This position is a fully funded PhD in computational chemistry.",
            "We are seeking a doctoral researcher for molecular dynamics and DFT.",
        ):
            with self.subTest(description=description):
                self.assertFalse(evaluate_job({
                    "title": "Research Assistant in Computational Chemistry",
                    "description": description,
                }, PROFILE).matched)

    def test_phd_qualifications_and_postdoctoral_fellowships_are_retained(self):
        for title in (
            "Postdoctoral Fellowship in Computational Chemistry",
            "Post-doctoral Fellowship in Computational Chemistry",
            "Post doctoral Fellow in Computational Chemistry",
            "Computational Chemistry Expert (PhD)",
            "Research Scientist (PhD) in Computational Chemistry",
            "PhD-level Research Scientist in Computational Chemistry",
            "International Research Scientist in Computational Chemistry",
        ):
            with self.subTest(title=title):
                self.assertTrue(evaluate_job({
                    "title": title,
                    "description": "This position requires a PhD. Develop molecular dynamics simulations and supervise PhD students.",
                }, PROFILE).matched)

    def test_experimental_roles_cannot_outscore_exclusion(self):
        for title, description in (
            ("Postdoc in Experimental Biophysics", "Molecular dynamics, DFT, Python and HPC with computational chemistry collaborators."),
            ("Scientist in Computational Chemistry", "This is primarily experimental work. Molecular dynamics, DFT, Python and HPC."),
            ("Research Scientist in Structural Biology", "Perform protein purification, cell culture and microscopy. Collaborate with computational chemistry and molecular dynamics teams."),
            ("Scientist in Molecular Biophysics", "Flow cytometry research."),
            ("Postdoc in Molecular Biophysics", "You will perform cell culture and analyze data using molecular dynamics."),
            ("Scientist in Computational Chemistry", "Collaborate with computational chemistry teams and perform protein purification, cell culture and microscopy."),
            ("Scientist in Computational Chemistry", "In collaboration with experimental teams, you will conduct organic synthesis and protein purification."),
        ):
            with self.subTest(title=title, description=description):
                result = evaluate_job({"title": title, "description": description}, PROFILE)
                self.assertFalse(result.matched)
                self.assertTrue(any("experimental" in reason for reason in result.reasons))

    def test_computational_collaborations_and_experimental_data_are_retained(self):
        for description in (
            "PhD required. Develop molecular dynamics simulations with experimental collaborators.",
            "You will collaborate with colleagues who perform cell culture and protein purification.",
            "You will analyze cryo-EM data using molecular dynamics and Python.",
            "You will compare molecular dynamics simulations with experimental measurements.",
            "Experience with microscopy data analysis is desirable. Develop molecular dynamics software.",
            "This is not a wet-lab role. Use molecular dynamics and DFT.",
        ):
            with self.subTest(description=description):
                self.assertTrue(evaluate_job({
                    "title": "Postdoctoral Fellow in Computational Chemistry",
                    "description": description,
                }, PROFILE).matched)

    def test_analysis_of_experimental_data_in_title_is_retained(self):
        for title in ("Research Scientist in Cryo-EM Data Analysis", "Postdoc in Microscopy Image Analysis"):
            with self.subTest(title=title):
                self.assertTrue(evaluate_job({
                    "title": title,
                    "description": "Develop computational chemistry models using molecular dynamics and Python.",
                    "location": "Germany",
                }, PROFILE).matched)

    def test_exclusion_switches_are_explicit_booleans(self):
        job = {
            "title": "Doctoral Researcher in Computational Chemistry",
            "description": "Molecular dynamics, DFT and HPC.",
        }
        self.assertTrue(evaluate_job(job, dict(PROFILE, exclude_doctoral_training=False)).matched)
        experimental = dict(job, title="Postdoc in Experimental Biophysics")
        self.assertTrue(evaluate_job(experimental, dict(PROFILE, exclude_experimental_roles=False)).matched)


if __name__ == "__main__":
    unittest.main()
