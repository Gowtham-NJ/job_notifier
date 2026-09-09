"""Public academic boards with structured vacancy details."""

from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests

from sources import _get_soup, _json_ld_job, fetch_rss_jobs


def _canonical_job_url(url: str, host: str, pattern: str) -> str | None:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or parts.netloc.casefold() != host:
        return None
    if not re.fullmatch(pattern, parts.path):
        return None
    return urlunsplit(("https", host, parts.path.rstrip("/") + "/", "", ""))


def _structured_details(
    urls: list[str], company: str, source_name: str, limit: int, delay: float,
) -> list[dict[str, str]]:
    jobs = []
    for url in urls[:limit]:
        time.sleep(delay)
        try:
            soup = _get_soup(url)
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code in {404, 410}:
                continue  # Withdrawn between the feed and detail requests.
            raise
        job = _json_ld_job(soup, company, url)
        if not job or not job["title"] or not job["description"]:
            # Do not treat a challenge page or changed markup as a successfully
            # seeded source, or score truncated descriptions without role duties.
            raise ValueError(f"{source_name}: missing structured vacancy details at {url}")
        job["url"] = url
        job["source"] = source_name
        jobs.append(job)
    return jobs


def fetch_sciencecareers_jobs(source: dict[str, Any], company: str) -> list[dict[str, str]]:
    urls: dict[str, None] = {}
    for feed_url in source.get("urls") or [source["url"]]:
        for job in fetch_rss_jobs(feed_url, company):
            url = _canonical_job_url(job["url"], "jobs.sciencecareers.org", r"/job/\d+/[^/]+/?")
            if url:
                urls[url] = None
    return _structured_details(
        list(urls), company, "sciencecareers", int(source.get("max_detail_pages", 60)), 0.25,
    )


def fetch_universitypositions_jobs(source: dict[str, Any], company: str) -> list[dict[str, str]]:
    urls: dict[str, None] = {}
    for index, listing_url in enumerate(source.get("urls") or [source["url"]]):
        if index:
            time.sleep(1)  # The public listing's robots.txt requests one second.
        soup = _get_soup(listing_url)
        anchors = soup.select("a.job-details-link[href]")
        if not anchors and not re.search(
            r"no (?:jobs|results)(?: found)?|couldn[’']t find any matches for your search",
            soup.get_text(" "), re.I,
        ):
            raise ValueError("universitypositions: no recognized listings or empty-results message")
        for anchor in anchors:
            url = _canonical_job_url(
                urljoin(listing_url, anchor["href"]), "universitypositions.eu", r"/jobs/\d+-[^/]+/?",
            )
            if url:
                urls[url] = None
    return _structured_details(
        list(urls), company, "universitypositions", int(source.get("max_detail_pages", 40)), 1,
    )
