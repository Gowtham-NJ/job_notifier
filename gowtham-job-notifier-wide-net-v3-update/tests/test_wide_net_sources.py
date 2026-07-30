import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup

from sources import (
    fetch_academicjobsonline_jobs,
    fetch_academictransfer_jobs,
    fetch_cecam_jobs,
    fetch_iscb_jobs,
    fetch_inria_jobs,
    fetch_leibniz_jobs,
    fetch_max_planck_jobs,
    fetch_molssi_jobs,
    fetch_society_rse_jobs,
    fetch_tyc_jobs,
    fetch_helmholtz_ai_jobs,
    fetch_embl_partner_jobs,
)


def soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


class WideNetSourceTests(unittest.TestCase):
    def test_molssi_parser(self):
        listing = soup(
            '''<main><h3>Active Job Posts</h3><ul>
            <li><a href="https://example.org/job">Research Software Engineer, Example Lab, Remote (full time) (01 July 2026)</a>
            Molecular simulation, Python, GROMACS and scientific software development.</li>
            </ul></main>'''
        )
        source = {"url": "https://molssi.org/jobs/", "max_age_days": 550}
        with patch("sources._get_soup", return_value=listing):
            jobs = fetch_molssi_jobs(source, "MolSSI")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["company"], "Example Lab")
        self.assertIn("Research Software Engineer", jobs[0]["title"])

    def test_cecam_parser(self):
        listing = soup(
            '''<main><article><h3>Postdoc in Molecular Simulation</h3>
            <p>Posted on: Jul 20, 2026</p>
            <a href="/careers-details/postdoc-molecular-simulation">READ MORE</a></article></main>'''
        )
        detail = soup(
            '''<main><h1>Postdoc in Molecular Simulation</h1>
            <p>Molecular dynamics, QM/MM and high-performance computing.</p></main>'''
        )
        source = {"url": "https://www.cecam.org/careers", "max_detail_pages": 5}
        with patch("sources._get_soup", side_effect=[listing, detail]):
            jobs = fetch_cecam_jobs(source, "CECAM Careers")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["source"], "cecam")
        self.assertIn("Molecular Simulation", jobs[0]["title"])

    def test_academicjobsonline_parser(self):
        listing = soup(
            '''<main><h3>Example University, Department of Chemistry</h3><ol>
            <li>[<a href="/ajo/jobs/32290">POSTDOC</a>] Postdoctoral Researcher in Computational Chemistry</li>
            </ol></main>'''
        )
        detail = soup(
            '''<main><h2>Example University, Department of Chemistry</h2>
            <p>Position Title: Postdoctoral Researcher in Computational Chemistry</p>
            <p>Position Type: Postdoctoral</p>
            <p>Position Location: Vienna, Austria</p>
            <p>Subject Area: Chemistry</p>
            <p>Position Description: Molecular dynamics and electronic structure calculations.</p>
            <p>Contact: PI</p></main>'''
        )
        source = {"url": "https://academicjobsonline.org/ajo/jobs?all=1", "max_detail_pages": 5}
        with patch("sources._get_soup", side_effect=[listing, detail]):
            jobs = fetch_academicjobsonline_jobs(source, "AcademicJobsOnline")
        self.assertEqual(len(jobs), 1)
        self.assertIn("Vienna", jobs[0]["location"])
        self.assertEqual(jobs[0]["source"], "academicjobsonline")

    def test_iscb_parser(self):
        listing = soup(
            '''<table><tr><td>July 22, 2026</td><td>Germany Berlin</td>
            <td>Postdoctoral Fellow in Structural Bioinformatics</td><td>Full Time</td>
            <td>Example Institute</td><td><a href="/jobs/view/9999">View</a></td></tr></table>'''
        )
        detail = soup(
            '''<main><h1>Postdoctoral Fellow in Structural Bioinformatics</h1>
            <p>Example Institute</p><p>Germany Berlin</p>
            <h3>Description</h3><p>Protein modelling, molecular dynamics and machine learning.</p>
            <h3>Qualifications</h3><p>PhD required.</p></main>'''
        )
        source = {"url": "https://careers.iscb.org/jobs", "pages": 1, "max_detail_pages": 5}
        with patch("sources._get_soup", side_effect=[listing, detail]):
            jobs = fetch_iscb_jobs(source, "ISCB")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["company"], "Example Institute")
        self.assertIn("Germany", jobs[0]["location"])

    def test_society_rse_parser(self):
        listing = soup(
            '''<main><article><h2><a href="/job/example-lab-research-software-engineer/">
            Research Software Engineer</a></h2><p>Example Lab, London</p></article></main>'''
        )
        detail = soup(
            '''<script type="application/ld+json">{
              "@context":"https://schema.org","@type":"JobPosting",
              "title":"Research Software Engineer","description":"Python, HPC and molecular simulation",
              "hiringOrganization":{"name":"Example Lab"},
              "jobLocation":{"address":{"addressLocality":"London","addressCountry":"United Kingdom"}}
            }</script>'''
        )
        source = {"url": "https://society-rse.org/?post_type=job_listing", "max_detail_pages": 5}
        with patch("sources._get_soup", side_effect=[listing, detail]):
            jobs = fetch_society_rse_jobs(source, "Society RSE")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["company"], "Example Lab")
        self.assertEqual(jobs[0]["source"], "society-rse")

    def test_max_planck_parser(self):
        listing = soup(
            '''<main><article><h3><a href="/26080138/astrochemistry-postdoctoral-positions-computational-chemistry">
            Astrochemistry Postdoctoral Positions on Computational Chemistry</a></h3>
            <p>July 28, 2026</p><p>Max Planck Institute for Astronomy, Heidelberg</p></article></main>'''
        )
        detail = soup(
            '''<main><h1>Astrochemistry Postdoctoral Positions on Computational Chemistry</h1>
            <p>Electronic structure, quantum chemistry and molecular dynamics.</p></main>'''
        )
        source = {"url": "https://www.mpg.de/jobboard", "max_detail_pages": 5}
        with patch("sources._get_soup", side_effect=[listing, detail]):
            jobs = fetch_max_planck_jobs(source, "Max Planck Society")
        self.assertEqual(len(jobs), 1)
        self.assertIn("Max Planck Institute", jobs[0]["company"])
        self.assertEqual(jobs[0]["source"], "max-planck")

    def test_leibniz_parser(self):
        listing = soup(
            '''<main><article><h3><a href="/en/careers/jobs/detail/job/show/Job/postdoc-computational-chemistry">
            Postdoctoral Researcher in Computational Chemistry</a></h3>
            <p>Leibniz Institute for Catalysis, Rostock</p></article></main>'''
        )
        detail = soup(
            '''<main><h1>Postdoctoral Researcher in Computational Chemistry</h1>
            <p>DFT, molecular dynamics and catalyst modelling.</p></main>'''
        )
        source = {"url": "https://www.leibniz-gemeinschaft.de/en/careers/jobs", "max_detail_pages": 5}
        with patch("sources._get_soup", side_effect=[listing, detail]):
            jobs = fetch_leibniz_jobs(source, "Leibniz Association")
        self.assertEqual(len(jobs), 1)
        self.assertIn("Leibniz Institute", jobs[0]["company"])
        self.assertEqual(jobs[0]["source"], "leibniz")

    def test_academictransfer_embedded_url_fallback(self):
        listing = soup(
            '''<html><script>window.__DATA__={"url":"/en/jobs/363009/postdoc-theoretical-chemistry/"};</script></html>'''
        )
        detail = soup(
            '''<script type="application/ld+json">{
              "@context":"https://schema.org","@type":"JobPosting",
              "title":"Postdoc in Theoretical Chemistry","description":"DFT and molecular simulation",
              "hiringOrganization":{"name":"TU Delft"},
              "jobLocation":{"address":{"addressLocality":"Delft","addressCountry":"Netherlands"}}
            }</script>'''
        )
        source = {"url": "https://www.academictransfer.com/en/jobs/", "max_detail_pages": 5}
        with patch("sources._get_soup", side_effect=[listing, detail]):
            jobs = fetch_academictransfer_jobs(source, "AcademicTransfer")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["company"], "TU Delft")

    def test_inria_parser(self):
        listing = soup(
            """<main><article><h2><a href="/public/classic/en/offres/2026-10281">
            Post-Doctoral Research Visit F/M Advanced HPC frameworks for real-time simulation</a></h2>
            <p>Town/city : Rennes</p><p>Inria Team : I4S</p>
            <p>Deadline to apply : 2099-09-15</p></article></main>"""
        )
        detail = soup(
            """<main><h1>Post-Doctoral Research Visit F/M Advanced HPC frameworks for real-time simulation</h1>
            <p>Scientific software, MPI and high-performance computing.</p></main>"""
        )
        source = {"url": "https://jobs.inria.fr/public/classic/en/offres", "max_detail_pages": 5}
        with patch("sources._get_soup", side_effect=[listing, detail]):
            jobs = fetch_inria_jobs(source, "Inria")
        self.assertEqual(len(jobs), 1)
        self.assertIn("Rennes", jobs[0]["location"])
        self.assertEqual(jobs[0]["source"], "inria")

    def test_tyc_parser(self):
        listing = soup(
            """<main><article><h2>Atomistic Modelling of Materials and Interfaces</h2>
            <p>Institution: King's College London</p><p>Application deadline: 30 April 2099</p>
            <a href="https://example.org/tyc-job">Apply</a></article></main>"""
        )
        source = {"url": "https://thomasyoungcentre.org/opportunities/jobs/"}
        with patch("sources._get_soup", return_value=listing):
            jobs = fetch_tyc_jobs(source, "Thomas Young Centre")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["company"], "King's College London")

    def test_helmholtz_ai_parser(self):
        listing = soup(
            """<main><h3>Forschungszentrum Jülich</h3><ul><li>
            <a href="https://example.org/job">Postdoc in Scientific Machine Learning for Molecular Simulation</a>
            </li></ul></main>"""
        )
        source = {"url": "https://www.helmholtz.ai/latest/careers/"}
        with patch("sources._get_soup", return_value=listing):
            jobs = fetch_helmholtz_ai_jobs(source, "Helmholtz AI")
        self.assertEqual(len(jobs), 1)
        self.assertIn("Jülich", jobs[0]["company"])

    def test_embl_partner_parser(self):
        listing = soup(
            """<main><h2>Nordic EMBL Partnership</h2>
            <h3>Postdoctoral researcher in structural bioinformatics</h3>
            <p>FIMM, Helsinki, Finland</p><p>Deadline: 16 August 2099</p>
            <p><a href="https://example.org/embl-partner-job">Apply</a></p></main>"""
        )
        source = {"url": "https://www.embl.org/careers/partners/"}
        with patch("sources._get_soup", return_value=listing):
            jobs = fetch_embl_partner_jobs(source, "EMBL Partner Opportunities")
        self.assertEqual(len(jobs), 1)
        self.assertIn("structural bioinformatics", jobs[0]["title"].lower())


if __name__ == "__main__":
    unittest.main()
