import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup

from sources import (
    _json_ld_job,
    fetch_ccl_jobs,
    fetch_charmm_gui_jobs,
    fetch_findapostdoc_jobs,
    fetch_researchjobs_cz_jobs,
    fetch_scholarshipdb_jobs,
)


def soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


class AcademicSourceTests(unittest.TestCase):
    def test_scholarshipdb_parser(self):
        listing = soup(
            '''<main><article>
            <a href="/jobs-in-Czech/Test-Computational-Chemistry=abc">Postdoctoral Fellow in Computational Chemistry</a>
            <p>IOCB Prague | Prague | Czech Republic | 2 hours ago</p>
            </article></main>'''
        )
        detail = soup(
            '''<main><h1>Postdoctoral Fellow in Computational Chemistry</h1>
            <h2>IOCB Prague, Czech Republic</h2>
            <p>Develop molecular dynamics, DFT and machine-learning methods.</p></main>'''
        )
        source = {
            "url": "https://scholarshipdb.net/scholarships?q=computational-chemistry",
            "max_detail_pages": 5,
        }
        with patch("sources._get_soup", side_effect=[listing, detail]):
            jobs = fetch_scholarshipdb_jobs(source, "ScholarshipDB")
        self.assertEqual(len(jobs), 1)
        self.assertIn("Computational Chemistry", jobs[0]["title"])
        self.assertEqual(jobs[0]["source"], "scholarshipdb")
        self.assertIn("molecular dynamics", jobs[0]["description"].lower())

    def test_findapostdoc_parser(self):
        listing = soup(
            '''<main><article>
            <a href="/search/Job-Details.aspx?jobcode=12345">Research Fellow in Theoretical Chemistry</a>
            </article></main>'''
        )
        detail = soup(
            '''<main><h1>Research Fellow in Theoretical Chemistry</h1>
            <h2>Charles University</h2>
            <p>Location: Prague, Czech Republic Deadline: 31 August 2026</p>
            <p>Electronic structure and DFT research.</p></main>'''
        )
        source = {"url": "https://www.findapostdoc.com/?PP=50", "max_detail_pages": 5}
        with patch("sources._get_soup", side_effect=[listing, detail]):
            jobs = fetch_findapostdoc_jobs(source, "FindAPostDoc")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["company"], "Charles University")
        self.assertIn("Prague", jobs[0]["location"])

    def test_researchjobs_cz_parser(self):
        listing = soup(
            '''<main><article>
            <a href="https://www.researchjobs.cz/job/postdoctoral-fellow-computational-chemistry/">
            Postdoctoral Fellow in Computational Chemistry</a>
            </article></main>'''
        )
        detail = soup(
            '''<main><h1>Postdoctoral Fellow in Computational Chemistry</h1>
            <ul><li>Full-time</li><li>IOCB Prague</li><li>Hlavní město Praha</li></ul>
            <p>Quantum chemistry, molecular simulations and scientific programming.</p></main>'''
        )
        source = {
            "url": "https://www.researchjobs.cz/kategorie-prace/c/?language=en",
            "max_detail_pages": 5,
        }
        with patch("sources._get_soup", side_effect=[listing, detail]):
            jobs = fetch_researchjobs_cz_jobs(source, "ResearchJobs.cz")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["company"], "IOCB Prague")
        self.assertIn("Czech Republic", jobs[0]["location"])

    def test_ccl_parser(self):
        listing = soup(
            '''<main><a href="/cca/jobs/joblist/mess0069534.shtml">
            26.07.09 Postdoc in Computational Materials Science</a></main>'''
        )
        detail = soup(
            '''<main><p>From: jobs at ccl.net</p>
            <p>Subject: Postdoc in Computational Materials Science</p>
            <p>Density functional theory and molecular dynamics experience required.</p></main>'''
        )
        source = {"url": "https://server.ccl.net/jobs/", "max_detail_pages": 5}
        with patch("sources._get_soup", side_effect=[listing, detail]):
            jobs = fetch_ccl_jobs(source, "CCL.NET Jobs")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["source"], "ccl.net")
        self.assertIn("Computational Materials", jobs[0]["title"])

    def test_charmm_gui_parser(self):
        listing = soup(
            '''<table><tr><td>2099-12-31</td><td>
            <a href="/?doc=jobs&amp;view=single&amp;id=999">Postdoc in Computational Biophysics</a>
            </td><td>Vienna, Austria</td></tr></table>'''
        )
        detail = soup(
            '''<main><h2>Title</h2><p>Postdoc in Computational Biophysics</p>
            <h2>Date</h2><p>2099-12-31</p>
            <h2>Location</h2><p>Vienna, Austria</p>
            <h2>Description</h2><p>Molecular dynamics, GROMACS and free-energy simulations.</p>
            <h2>How to Apply</h2><p>Apply online.</p></main>'''
        )
        source = {
            "url": "https://charmm-gui.org/?doc=jobs&view=list",
            "max_detail_pages": 5,
            "expiry_grace_days": 3,
        }
        with patch("sources._get_soup", side_effect=[listing, detail]):
            jobs = fetch_charmm_gui_jobs(source, "CHARMM-GUI Jobs")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["location"], "Vienna, Austria")
        self.assertIn("Molecular dynamics", jobs[0]["description"])

    def test_json_ld_country_object(self):
        page = soup(
            '''<script type="application/ld+json">{
              "@context": "https://schema.org", "@type": "JobPosting",
              "title": "Postdoctoral Researcher", "description": "DFT",
              "hiringOrganization": {"name": "Example Institute"},
              "jobLocation": {"address": {
                "addressLocality": "Prague",
                "addressCountry": {"name": "Czech Republic"}
              }}
            }</script>'''
        )
        job = _json_ld_job(page, "Fallback", "https://example.org/job")
        self.assertIsNotNone(job)
        self.assertEqual(job["location"], "Prague, Czech Republic")


if __name__ == "__main__":
    unittest.main()

class BroadSourceTests(unittest.TestCase):
    def test_euraxess_parser(self):
        listing = soup(
            '''<main><article>
            <a href="/jobs/457010">Postdoctoral Researcher in Computational Chemistry</a>
            <p>JOB Sweden Example University Posted on: 30 July 2026</p>
            <p>Work Locations: Number of offers: 1, Sweden, Uppsala</p>
            <p>Molecular dynamics and QM/MM simulations.</p>
            <p>Research Field: Chemistry</p>
            </article></main>'''
        )
        source = {"url": "https://euraxess.ec.europa.eu/jobs/search", "pages": 1}
        with patch("sources._get_soup", return_value=listing):
            from sources import fetch_euraxess_jobs
            jobs = fetch_euraxess_jobs(source, "EURAXESS")
        self.assertEqual(len(jobs), 1)
        self.assertIn("Sweden", jobs[0]["location"])
        self.assertEqual(jobs[0]["source"], "euraxess")

    def test_academictransfer_parser(self):
        listing = soup(
            '''<main><article>
            <a href="/en/jobs/363009/postdoc-in-physical-and-theoretical-chemistry/">
            Postdoc in Physical and Theoretical Chemistry</a>
            <p>Electronic structure and molecular simulations. Published today Delft</p>
            </article></main>'''
        )
        detail = soup(
            '''<script type="application/ld+json">{
              "@context":"https://schema.org","@type":"JobPosting",
              "title":"Postdoc in Physical and Theoretical Chemistry",
              "description":"Electronic structure and molecular simulations",
              "hiringOrganization":{"name":"TU Delft"},
              "jobLocation":{"address":{"addressLocality":"Delft","addressCountry":"Netherlands"}}
            }</script>'''
        )
        source = {"url": "https://www.academictransfer.com/en/jobs/", "max_detail_pages": 5}
        with patch("sources._get_soup", side_effect=[listing, detail]):
            from sources import fetch_academictransfer_jobs
            jobs = fetch_academictransfer_jobs(source, "AcademicTransfer")
        self.assertEqual(jobs[0]["company"], "TU Delft")
        self.assertIn("Netherlands", jobs[0]["location"])

    def test_jobs_ac_uk_parser(self):
        listing = soup(
            '''<main><article>
            <a href="/job/DRV016/postdoctoral-researcher">Postdoctoral Researcher</a>
            <p>Large-scale molecular dynamics and computational biophysics. Location: London</p>
            </article></main>'''
        )
        detail = soup(
            '''<main><h1>Postdoctoral Researcher</h1>
            <h2>Birkbeck, University of London</h2>
            <p>Location: London Salary: competitive</p>
            <p>Molecular dynamics, structural biology and Python.</p></main>'''
        )
        source = {"url":"https://www.jobs.ac.uk/search/?keywords=molecular+dynamics","max_detail_pages":5}
        with patch("sources._get_soup", side_effect=[listing, detail]):
            from sources import fetch_jobs_ac_uk_jobs
            jobs = fetch_jobs_ac_uk_jobs(source, "jobs.ac.uk")
        self.assertEqual(len(jobs), 1)
        self.assertIn("Postdoctoral", jobs[0]["title"])
        self.assertEqual(jobs[0]["source"], "jobs.ac.uk")

    def test_jobbnorge_api_parser(self):
        class Response:
            def raise_for_status(self):
                return None
            def json(self):
                return {"jobs": [{
                    "title":"Postdoctoral Fellow in Molecular Simulation",
                    "link":"https://www.jobbnorge.no/en/available-jobs/job/1",
                    "employer":"University of Oslo",
                    "municipality":"Oslo",
                    "summary":"Molecular dynamics and DFT"
                }]}
        with patch("sources.SESSION.get", return_value=Response()):
            from sources import fetch_jobbnorge_jobs
            jobs = fetch_jobbnorge_jobs({"url":"https://publicapi.jobbnorge.no/v3/Jobs"}, "Jobbnorge")
        self.assertEqual(jobs[0]["company"], "University of Oslo")
        self.assertEqual(jobs[0]["location"], "Oslo, Norway")

    def test_arbeitnow_api_parser(self):
        class Response:
            def raise_for_status(self):
                return None
            def json(self):
                return {"data": [{
                    "title":"Computational Chemist",
                    "company_name":"Example Bio",
                    "location":"Berlin",
                    "remote":False,
                    "url":"https://example.org/job/1",
                    "description":"Molecular dynamics and Python",
                    "tags":["chemistry"],
                    "job_types":["full-time"]
                }], "last_page":1}
        with patch("sources.SESSION.get", return_value=Response()):
            from sources import fetch_arbeitnow_jobs
            jobs = fetch_arbeitnow_jobs({"url":"https://www.arbeitnow.com/api/job-board-api","pages":1}, "Arbeitnow")
        self.assertEqual(jobs[0]["company"], "Example Bio")
        self.assertEqual(jobs[0]["source"], "arbeitnow")
