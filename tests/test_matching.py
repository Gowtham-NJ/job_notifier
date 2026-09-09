import unittest

from matching import find_matching_jobs, score_catalog_job


USER = {
    "science_fields": "Immunology, molecular biology",
    "skills": "Flow cytometry, Python, cell culture",
    "target_roles": "Postdoc, research scientist",
    "preferred_locations": "Germany, Netherlands",
    "work_mode": "Hybrid",
}

COMPUTATIONAL_USER = {
    "science_fields": "Computational chemistry, biophysics",
    "skills": "Molecular dynamics, DFT, Python",
    "target_roles": "Postdoc, research scientist",
    "preferred_locations": "Worldwide",
    "work_mode": "Any",
    "career_stage": "PhD",
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

    def test_doctoral_training_does_not_match_postdoc_preferences(self):
        for title in (
            "PhD Researcher in Computational Chemistry",
            "Ph.D. position in molecular simulation",
            "Doctoral researcher in computational biophysics",
            "PhD candidate in Computational Chemistry",
        ):
            with self.subTest(title=title):
                self.assertIsNone(
                    score_catalog_job(
                        {
                            "title": title,
                            "description": "Molecular dynamics, DFT and Python.",
                            "location": "Germany",
                        },
                        COMPUTATIONAL_USER,
                    )
                )

    def test_doctoral_training_description_is_excluded(self):
        self.assertIsNone(
            score_catalog_job(
                {
                    "title": "Research Assistant in Computational Chemistry",
                    "description": "You will enroll in a PhD programme and develop molecular dynamics simulations in Python.",
                },
                COMPUTATIONAL_USER,
            )
        )

    def test_explicit_doctoral_preferences_still_receive_doctoral_jobs(self):
        job = {
            "title": "PhD Researcher in Computational Chemistry",
            "description": "Molecular dynamics, DFT and Python.",
        }
        for roles in ("PhD", "Ph.D. position", "P.h.D. position", "Doctoral researcher", "DPhil", "Studentship"):
            with self.subTest(roles=roles):
                self.assertIsNotNone(
                    score_catalog_job(job, dict(COMPUTATIONAL_USER, target_roles=roles))
                )

    def test_postdoctoral_and_negative_preferences_do_not_opt_in_to_phd_jobs(self):
        job = {
            "title": "PhD Researcher in Computational Chemistry",
            "description": "Molecular dynamics, DFT and Python.",
        }
        for roles in (
            "Postdoctoral researcher",
            "Post-doctoral researcher",
            "Post–doctoral researcher",
            "Post doctoral fellow",
            "Research scientist, no PhD positions",
            "Research scientist for PhD holders",
        ):
            with self.subTest(roles=roles):
                self.assertIsNone(
                    score_catalog_job(job, dict(COMPUTATIONAL_USER, target_roles=roles))
                )

    def test_experimental_roles_do_not_match_computational_preferences(self):
        for job in (
            {
                "title": "Postdoc in Experimental Biophysics",
                "description": "Primarily experimental. Computational chemistry collaborators provide molecular dynamics, DFT and Python analysis.",
            },
            {
                "title": "Research Scientist in Structural Biology",
                "description": "Perform protein purification, cell culture, microscopy and biochemical assays. Collaborate with computational chemistry and molecular dynamics teams.",
            },
            {
                "title": "Postdoc in Computational Chemistry",
                "description": "Collaborate with computational chemistry teams and perform protein purification, cell culture and microscopy.",
            },
            {
                "title": "Postdoc in Computational Chemistry",
                "description": "In collaboration with experimental teams, you will conduct organic synthesis and protein purification.",
            },
        ):
            with self.subTest(title=job["title"]):
                self.assertIsNone(score_catalog_job(job, COMPUTATIONAL_USER))

    def test_computational_postdoc_requiring_phd_and_experimental_collaboration_is_retained(self):
        self.assertIsNotNone(
            score_catalog_job(
                {
                    "title": "Postdoctoral Fellow in Computational Chemistry",
                    "description": "PhD required. Develop molecular dynamics simulations in collaboration with experimental chemists.",
                },
                COMPUTATIONAL_USER,
            )
        )

    def test_experimental_job_is_retained_for_experimental_user_with_python_skill(self):
        self.assertIsNotNone(
            score_catalog_job(
                {
                    "title": "Postdoc in Experimental Immunology",
                    "description": "Primarily experimental role using flow cytometry, cell culture and Python.",
                },
                USER,
            )
        )

    def test_computational_work_with_experimental_data_is_retained(self):
        for description in (
            "You will compare molecular dynamics simulations with experimental measurements.",
            "You will analyze cryo-EM data using molecular dynamics and Python.",
            "Experience with microscopy data analysis is desirable. Develop molecular dynamics simulation software.",
        ):
            with self.subTest(description=description):
                self.assertIsNotNone(
                    score_catalog_job(
                        {
                            "title": "Research Scientist in Computational Chemistry",
                            "description": description,
                        },
                        COMPUTATIONAL_USER,
                    )
                )

    def test_doctorate_as_required_qualification_is_retained(self):
        for description in (
            "This position requires a PhD in computational chemistry. You will run molecular dynamics simulations.",
            "You will complete a PhD before the starting date and conduct molecular dynamics simulations.",
        ):
            with self.subTest(description=description):
                self.assertIsNotNone(
                    score_catalog_job(
                        {
                            "title": "Postdoctoral Researcher in Computational Chemistry",
                            "description": description,
                        },
                        COMPUTATIONAL_USER,
                    )
                )

    def test_experimental_data_analysis_titles_are_retained(self):
        for title in (
            "Research Scientist in Cryo-EM Data Analysis",
            "Postdoc in Microscopy Image Analysis",
        ):
            with self.subTest(title=title):
                self.assertIsNotNone(
                    score_catalog_job(
                        {
                            "title": title,
                            "description": "Analyze structural biology data with molecular dynamics and Python.",
                        },
                        COMPUTATIONAL_USER,
                    )
                )

    def test_computational_target_role_triggers_filter_even_with_broad_science_field(self):
        self.assertIsNone(
            score_catalog_job(
                {
                    "title": "Research Scientist in Experimental Biophysics",
                    "description": "Primarily experimental work using Python.",
                },
                dict(COMPUTATIONAL_USER, science_fields="Biophysics", target_roles="Computational scientist"),
            )
        )


if __name__ == "__main__":
    unittest.main()
