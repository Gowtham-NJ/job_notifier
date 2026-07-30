import unittest

from sources import (
    parse_ashby_payload,
    parse_himalayas_payload,
    parse_jobicy_payload,
    parse_jobrxiv_html,
    parse_mathjobs_html,
    parse_recruitee_payload,
    parse_remotive_payload,
    parse_workable_payload,
)


class AdditionalSourceTests(unittest.TestCase):
    def test_ashby_parser(self):
        jobs = parse_ashby_payload(
            {
                "jobs": [
                    {
                        "title": "Computational Chemist",
                        "location": "Prague",
                        "isRemote": False,
                        "jobUrl": "https://jobs.example/1",
                        "descriptionPlain": "Molecular dynamics and DFT",
                    }
                ]
            },
            "Example AI",
        )
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["source"], "ashby")
        self.assertIn("Molecular dynamics", jobs[0]["description"])

    def test_recruitee_parser(self):
        jobs = parse_recruitee_payload(
            {
                "offers": [
                    {
                        "title": "Scientific Software Engineer",
                        "location": {"name": "Amsterdam"},
                        "careers_url": "https://example.recruitee.com/o/1",
                        "description": "Python, HPC and molecular simulation",
                    }
                ]
            },
            "Example Lab",
        )
        self.assertEqual(jobs[0]["location"], "Amsterdam")
        self.assertEqual(jobs[0]["source"], "recruitee")

    def test_workable_parser(self):
        jobs = parse_workable_payload(
            {
                "results": [
                    {
                        "title": "Research Scientist, Molecular Simulation",
                        "location": {"city": "Vienna", "country": "Austria"},
                        "url": "https://apply.workable.com/example/j/1",
                        "description": "QM/MM and DFT",
                    }
                ]
            },
            "Example Company",
        )
        self.assertIn("Vienna", jobs[0]["location"])
        self.assertEqual(jobs[0]["source"], "workable")

    def test_mathjobs_parser_filters_relevant_roles(self):
        html = '''<main><h3>Example University, Chemistry</h3><ol>
        <li><a href="/jobs/1234/POSTDOC">Postdoc in Computational Molecular Science</a></li>
        <li><a href="/jobs/1234/ALG">Professor of Pure Algebra</a></li>
        </ol></main>'''
        jobs = parse_mathjobs_html(html, "MathJobs", "https://www.mathjobs.org/jobs/list")
        self.assertEqual(len(jobs), 1)
        self.assertIn("Computational", jobs[0]["title"])

    def test_jobrxiv_parser(self):
        html = '''<article><h2><a href="https://jobrxiv.org/job/example-postdoc/">Postdoc in Computational Chemistry</a></h2>
        <p>Example Institute | Berlin, Germany | Molecular dynamics and electronic structure</p></article>'''
        jobs = parse_jobrxiv_html(html, "jobRxiv", "https://jobrxiv.org/job-tag/chemistry/")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["source"], "jobrxiv")

    def test_jobicy_parser(self):
        jobs = parse_jobicy_payload(
            {"jobs": [{"jobTitle": "Molecular Simulation Scientist", "companyName": "Remote Lab", "jobGeo": "Anywhere", "url": "https://jobicy.com/job/1", "jobDescription": "GROMACS and Python"}]},
            "Jobicy",
        )
        self.assertEqual(jobs[0]["company"], "Remote Lab")

    def test_himalayas_parser(self):
        jobs = parse_himalayas_payload(
            {"jobs": [{"title": "Scientific Computing Engineer", "company": {"name": "ComputeCo"}, "locationRestrictions": ["Europe"], "applicationLink": "https://himalayas.app/job/1", "description": "HPC and Python"}]},
            "Himalayas",
        )
        self.assertEqual(jobs[0]["location"], "Europe")
        self.assertEqual(jobs[0]["company"], "ComputeCo")

    def test_remotive_parser(self):
        jobs = parse_remotive_payload(
            {"jobs": [{"title": "Research Software Engineer", "company_name": "Remote Science", "candidate_required_location": "Worldwide", "url": "https://remotive.com/job/1", "description": "Scientific software and HPC"}]},
            "Remotive",
        )
        self.assertEqual(jobs[0]["source"], "remotive")


if __name__ == "__main__":
    unittest.main()
