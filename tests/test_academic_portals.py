import json
import unittest
from unittest.mock import patch

import requests
from bs4 import BeautifulSoup

import academic_portals
from config import validate_companies
from sources import fetch_jobs


def page(text):
    return BeautifulSoup(text, "lxml")


def detail(title="Postdoc in Computational Chemistry"):
    return page('<script type="application/ld+json">' + json.dumps({
        "@type": "JobPosting", "title": title,
        "description": "PhD required. Develop molecular dynamics and DFT simulations.",
        "hiringOrganization": {"name": "Example University"},
        "jobLocation": {"address": {"addressLocality": "Prague", "addressCountry": "Czechia"}},
    }) + '</script><aside>PhD studentship in experimental chemistry</aside>')


class AcademicPortalTests(unittest.TestCase):
    @patch("academic_portals.time.sleep")
    @patch("academic_portals._get_soup", return_value=detail())
    @patch("academic_portals.fetch_rss_jobs")
    def test_science_feed_deduplicates_tracking_urls_and_reads_full_details(self, rss, get, sleep):
        url = "https://jobs.sciencecareers.org/job/123/postdoc/"
        rss.side_effect = [[{"url": url + "?TrackID=9"}], [
            {"url": url + "?utm_source=other"}, {"url": "https://other.example/job/123/postdoc/"},
        ]]
        source = {"company": "Science Careers", "source_type": "sciencecareers",
                  "url": "https://jobs.sciencecareers.org/jobsrss/", "urls": ["feed-a", "feed-b"]}
        validate_companies([source])
        jobs = fetch_jobs(source)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["url"], url)
        self.assertEqual(jobs[0]["company"], "Example University")
        self.assertEqual(jobs[0]["location"], "Prague, Czechia")
        self.assertEqual(jobs[0]["source"], "sciencecareers")
        self.assertNotIn("studentship", jobs[0]["description"])
        get.assert_called_once_with(url)

    @patch("academic_portals.time.sleep")
    @patch("academic_portals._get_soup")
    def test_university_listing_deduplicates_and_respects_detail_limit_and_delay(self, get, sleep):
        listing = page('''<a class="job-details-link" href="/jobs/123-postdoc">Postdoc</a>
          <a class="job-details-link" href="/jobs/123-postdoc?ref=other">Postdoc</a>
          <a class="job-details-link" href="/jobs/456-scientist">Scientist</a>
          <a href="/jobs/123/apply">Apply</a>''')
        get.side_effect = [listing, listing, detail()]
        source = {"company": "University Positions", "source_type": "universitypositions",
                  "url": "https://universitypositions.eu/jobs", "max_detail_pages": 1,
                  "urls": ["https://universitypositions.eu/jobs?query=a", "https://universitypositions.eu/jobs?query=b"]}
        validate_companies([source])
        jobs = fetch_jobs(source)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["url"], "https://universitypositions.eu/jobs/123-postdoc/")
        self.assertEqual(jobs[0]["source"], "universitypositions")
        self.assertEqual(get.call_count, 3)
        self.assertEqual(sleep.call_count, 2)
        self.assertTrue(all(call.args == (1,) for call in sleep.call_args_list))

    @patch("academic_portals._get_soup", return_value=page("<main>Sorry, we couldn’t find any matches for your search.</main>"))
    def test_empty_university_search_is_valid(self, get):
        self.assertEqual(academic_portals.fetch_universitypositions_jobs(
            {"url": "https://universitypositions.eu/jobs"}, "University Positions"), [])

    @patch("academic_portals._get_soup", return_value=page("<main>Verify you are human</main>"))
    def test_challenge_page_does_not_silently_seed_source(self, get):
        with self.assertRaises(ValueError):
            academic_portals.fetch_universitypositions_jobs(
                {"url": "https://universitypositions.eu/jobs"}, "University Positions")

    @patch("academic_portals.time.sleep")
    @patch("academic_portals._get_soup", return_value=page("<main>Not a vacancy</main>"))
    @patch("academic_portals.fetch_rss_jobs", return_value=[{"url": "https://jobs.sciencecareers.org/job/1/postdoc/"}])
    def test_missing_detail_does_not_match_truncated_feed_or_sidebar(self, rss, get, sleep):
        with self.assertRaises(ValueError):
            academic_portals.fetch_sciencecareers_jobs({"url": "feed"}, "Science Careers")

    @patch("academic_portals.time.sleep")
    @patch("academic_portals._get_soup")
    @patch("academic_portals.fetch_rss_jobs", return_value=[{"url": "https://jobs.sciencecareers.org/job/1/postdoc/"}])
    def test_withdrawn_job_is_skipped_but_access_errors_propagate(self, rss, get, sleep):
        for status in (404, 410, 403):
            response = requests.Response()
            response.status_code = status
            get.side_effect = requests.HTTPError(response=response)
            with self.subTest(status=status):
                if status == 403:
                    with self.assertRaises(requests.HTTPError):
                        academic_portals.fetch_sciencecareers_jobs({"url": "feed"}, "Science Careers")
                else:
                    self.assertEqual(academic_portals.fetch_sciencecareers_jobs({"url": "feed"}, "Science Careers"), [])
