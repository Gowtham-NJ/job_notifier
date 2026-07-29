from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from filters import clean_text

MAX_JOBS_PER_SOURCE = 500


def _build_session() -> requests.Session:
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.7,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST"}),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(
        {
            "User-Agent": "GowthamJobNotifier/1.0 (+https://github.com/)",
            "Accept": "application/json, text/plain, text/html, application/xml, */*",
        }
    )
    return session


SESSION = _build_session()


def _job(
    company: str,
    title: Any,
    location: Any,
    url: Any,
    description: Any,
    source: str,
) -> dict[str, str]:
    return {
        "company": clean_text(company),
        "title": clean_text(title),
        "location": clean_text(location),
        "url": str(url or "").strip(),
        "description": clean_text(description),
        "source": source,
    }


def fetch_greenhouse_jobs(token: str, company: str) -> list[dict[str, str]]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
    response = SESSION.get(url, timeout=30)
    response.raise_for_status()
    jobs: list[dict[str, str]] = []

    for item in response.json().get("jobs", []):
        location = (item.get("location") or {}).get("name", "")
        jobs.append(
            _job(
                company,
                item.get("title"),
                location,
                item.get("absolute_url"),
                item.get("content"),
                "greenhouse",
            )
        )
    return jobs[:MAX_JOBS_PER_SOURCE]


def fetch_lever_jobs(token: str, company: str) -> list[dict[str, str]]:
    url = f"https://api.lever.co/v0/postings/{token}?mode=json"
    response = SESSION.get(url, timeout=30)
    response.raise_for_status()
    jobs: list[dict[str, str]] = []

    for item in response.json():
        categories = item.get("categories") or {}
        description_parts = [
            item.get("descriptionPlain") or item.get("description") or "",
            item.get("additionalPlain") or item.get("additional") or "",
        ]
        jobs.append(
            _job(
                company,
                item.get("text"),
                categories.get("location", ""),
                item.get("hostedUrl") or item.get("applyUrl"),
                " ".join(str(part) for part in description_parts if part),
                "lever",
            )
        )
    return jobs[:MAX_JOBS_PER_SOURCE]


def _slugify(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.casefold())).strip("-")


def fetch_smartrecruiters_jobs(token: str, company: str) -> list[dict[str, str]]:
    jobs: list[dict[str, str]] = []
    offset = 0
    limit = 100

    while len(jobs) < MAX_JOBS_PER_SOURCE:
        url = f"https://api.smartrecruiters.com/v1/companies/{token}/postings"
        response = SESSION.get(url, params={"limit": limit, "offset": offset}, timeout=30)
        response.raise_for_status()
        postings = response.json().get("content", [])
        if not postings:
            break

        for item in postings:
            location_data = item.get("location") or {}
            location = ", ".join(
                str(value).strip()
                for value in (
                    location_data.get("city"),
                    location_data.get("region"),
                    location_data.get("country"),
                )
                if value
            )
            title = clean_text(item.get("name"))
            job_id = str(item.get("id") or "").strip()
            job_url = item.get("postingUrl") or item.get("applyUrl")
            if not job_url and job_id:
                job_url = f"https://jobs.smartrecruiters.com/{token}/{job_id}-{_slugify(title)}"
            jobs.append(_job(company, title, location, job_url, "", "smartrecruiters"))

        if len(postings) < limit:
            break
        offset += limit

    return jobs[:MAX_JOBS_PER_SOURCE]


def _strip_locale_prefix(path: str) -> str:
    parts = [part for part in path.strip("/").split("/") if part]
    if parts and re.fullmatch(r"[a-z]{2}-[A-Z]{2}", parts[0]):
        parts = parts[1:]
    return "/".join(parts)


def _workday_candidates(base_url: str) -> tuple[str, str, list[str]]:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Invalid Workday URL: {base_url}")

    host = parsed.netloc
    site_path = parsed.path.strip("/")
    path_no_locale = _strip_locale_prefix(site_path)
    parts = [part for part in path_no_locale.split("/") if part]

    tenants = [host.split(".")[0]]
    site_candidates = [path_no_locale]
    if len(parts) >= 3 and parts[0].casefold() == "recruiting":
        tenants.insert(0, parts[1])
        site_candidates.insert(0, "/".join(parts[2:]))

    candidates: list[str] = []
    for tenant in tenants:
        for site in site_candidates:
            if tenant and site:
                candidates.append(f"https://{host}/wday/cxs/{tenant}/{site}/jobs")
    return host, site_path, list(dict.fromkeys(candidates))


def _post_workday(api_url: str, base_url: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    origin = f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}"
    response = SESSION.post(
        api_url,
        json=payload,
        headers={
            "Content-Type": "application/json",
            "Origin": origin,
            "Referer": base_url.rstrip("/") + "/",
        },
        timeout=30,
    )
    response.raise_for_status()
    try:
        data = response.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def fetch_workday_jobs(token: str, company: str) -> list[dict[str, str]]:
    host, site_path, candidates = _workday_candidates(token)
    probe = {"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""}
    api_url = None

    for candidate in candidates:
        try:
            data = _post_workday(candidate, token, probe)
            if data and "jobPostings" in data:
                api_url = candidate
                break
        except requests.RequestException:
            continue

    if not api_url:
        raise RuntimeError(f"Could not discover a Workday API endpoint for {company}")

    jobs: list[dict[str, str]] = []
    offset = 0
    limit = 20
    while len(jobs) < MAX_JOBS_PER_SOURCE:
        payload = {"appliedFacets": {}, "limit": limit, "offset": offset, "searchText": ""}
        data = _post_workday(api_url, token, payload)
        postings = (data or {}).get("jobPostings", [])
        if not postings:
            break

        for item in postings:
            external_path = str(item.get("externalPath") or "").lstrip("/")
            job_url = f"https://{host}/{site_path}/{external_path}" if external_path else token
            bullet_fields = item.get("bulletFields") or []
            description = " ".join(bullet_fields) if isinstance(bullet_fields, list) else ""
            jobs.append(
                _job(
                    company,
                    item.get("title"),
                    item.get("locationsText") or item.get("location"),
                    job_url,
                    description,
                    "workday",
                )
            )

        if len(postings) < limit:
            break
        offset += limit

    return jobs[:MAX_JOBS_PER_SOURCE]


def parse_rss_xml(xml_text: str, company: str, base_url: str = "") -> list[dict[str, str]]:
    root = ET.fromstring(xml_text)
    jobs: list[dict[str, str]] = []

    # RSS 2.0
    for item in root.findall(".//item"):
        title = item.findtext("title", default="")
        link = item.findtext("link", default="")
        description = item.findtext("description", default="")
        jobs.append(_job(company, title, "", urljoin(base_url, link), description, "rss"))

    if jobs:
        return jobs[:MAX_JOBS_PER_SOURCE]

    # Atom
    namespace = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.findall(".//atom:entry", namespace):
        title = entry.findtext("atom:title", default="", namespaces=namespace)
        summary = entry.findtext("atom:summary", default="", namespaces=namespace)
        content = entry.findtext("atom:content", default="", namespaces=namespace)
        link_element = entry.find("atom:link", namespace)
        link = link_element.get("href", "") if link_element is not None else ""
        jobs.append(_job(company, title, "", urljoin(base_url, link), summary or content, "rss"))

    return jobs[:MAX_JOBS_PER_SOURCE]


def fetch_rss_jobs(url: str, company: str) -> list[dict[str, str]]:
    response = SESSION.get(url, timeout=30)
    response.raise_for_status()
    return parse_rss_xml(response.text, company, url)


def fetch_jobs(source: dict[str, Any]) -> list[dict[str, str]]:
    source_type = source["source_type"]
    company = source["company"]
    if source_type == "greenhouse":
        return fetch_greenhouse_jobs(source["token"], company)
    if source_type == "lever":
        return fetch_lever_jobs(source["token"], company)
    if source_type == "smartrecruiters":
        return fetch_smartrecruiters_jobs(source["token"], company)
    if source_type == "workday":
        return fetch_workday_jobs(source["token"], company)
    if source_type == "rss":
        return fetch_rss_jobs(source["url"], company)
    raise ValueError(f"Unsupported source_type: {source_type}")
