from __future__ import annotations

import datetime as dt
import html as html_lib
import json
import re
import xml.etree.ElementTree as ET
from typing import Any, Iterable
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from filters import clean_text

MAX_JOBS_PER_SOURCE = 500
MAX_DESCRIPTION_CHARS = 30_000


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
            "User-Agent": "GowthamJobNotifier/2.0 (+personal non-commercial job alerts)",
            "Accept": "application/json, text/plain, text/html, application/xml, */*",
            "Accept-Language": "en-GB,en;q=0.9",
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
        "description": clean_text(description)[:MAX_DESCRIPTION_CHARS],
        "source": source,
    }


def _get_soup(url: str) -> BeautifulSoup:
    response = SESSION.get(url, timeout=30)
    response.raise_for_status()
    return BeautifulSoup(response.text, "lxml")


def _remove_noise(soup: BeautifulSoup) -> None:
    for tag in soup.select("script, style, noscript, svg, form, nav, footer, header"):
        tag.decompose()


def _page_text(soup: BeautifulSoup) -> str:
    copy = BeautifulSoup(str(soup), "lxml")
    _remove_noise(copy)
    main = copy.find("main") or copy.find("article") or copy.body or copy
    return clean_text(main.get_text(" ", strip=True))


def _nearest_card_text(anchor: Tag) -> str:
    for parent in anchor.parents:
        if not isinstance(parent, Tag):
            continue
        if parent.name not in {"article", "li", "tr", "section", "div"}:
            continue
        text = clean_text(parent.get_text(" ", strip=True))
        if 20 <= len(text) <= 5_000:
            return text
    return clean_text(anchor.get_text(" ", strip=True))


def _iter_json_objects(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        graph = value.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                yield from _iter_json_objects(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_json_objects(item)


def _json_ld_job(soup: BeautifulSoup, fallback_company: str, fallback_url: str) -> dict[str, str] | None:
    for script in soup.select('script[type="application/ld+json"]'):
        raw = script.string or script.get_text()
        if not raw.strip():
            continue
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        for item in _iter_json_objects(payload):
            item_type = item.get("@type")
            types = item_type if isinstance(item_type, list) else [item_type]
            if not any(str(value).casefold() == "jobposting" for value in types):
                continue

            organization = item.get("hiringOrganization") or {}
            company = organization.get("name") if isinstance(organization, dict) else organization

            location_parts: list[str] = []
            locations = item.get("jobLocation") or []
            if isinstance(locations, dict):
                locations = [locations]
            for location in locations if isinstance(locations, list) else []:
                if not isinstance(location, dict):
                    continue
                address = location.get("address") or {}
                if isinstance(address, str):
                    location_parts.append(address)
                elif isinstance(address, dict):
                    country = address.get("addressCountry")
                    if isinstance(country, dict):
                        country = country.get("name") or country.get("addressCountry")
                    values = [
                        address.get("addressLocality"),
                        address.get("addressRegion"),
                        country,
                    ]
                    location_parts.append(", ".join(str(value) for value in values if value))

            remote = item.get("jobLocationType")
            if remote and "telecommute" in str(remote).casefold():
                location_parts.append("Remote")

            return _job(
                str(company or fallback_company),
                item.get("title") or item.get("name"),
                "; ".join(part for part in location_parts if part),
                item.get("url") or fallback_url,
                item.get("description"),
                "json-ld",
            )
    return None


def _heading_text(soup: BeautifulSoup, names: tuple[str, ...] = ("h1",)) -> str:
    for name in names:
        heading = soup.find(name)
        if heading:
            text = clean_text(heading.get_text(" ", strip=True))
            if text:
                return text
    return ""


def _parse_pipe_metadata(text: str, title: str) -> tuple[str, str]:
    remainder = text.replace(title, "", 1).strip(" |-–—")
    parts = [clean_text(part) for part in remainder.split("|") if clean_text(part)]
    parts = [
        part
        for part in parts
        if not re.search(r"\b(?:ago|today|yesterday|updated|deadline|apply)\b", part, re.I)
    ]
    if not parts:
        return "", ""
    company = parts[0]
    location = ", ".join(parts[1:3]) if len(parts) > 1 else ""
    return company, location


def _parse_date_prefix(title: str) -> dt.date | None:
    match = re.match(r"\s*(\d{2})[.-](\d{2})[.-](\d{2})\b", title)
    if not match:
        return None
    year, month, day = (int(value) for value in match.groups())
    year += 2000
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None


def _is_within_age(date_value: dt.date | None, max_age_days: int | None) -> bool:
    if date_value is None or not max_age_days:
        return True
    return (dt.datetime.now(dt.timezone.utc).date() - date_value).days <= max_age_days


# ---------------------------------------------------------------------------
# Structured company job boards
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# RSS/Atom
# ---------------------------------------------------------------------------


def parse_rss_xml(xml_text: str, company: str, base_url: str = "") -> list[dict[str, str]]:
    root = ET.fromstring(xml_text)
    jobs: list[dict[str, str]] = []

    for item in root.findall(".//item"):
        title = item.findtext("title", default="")
        link = item.findtext("link", default="")
        description = item.findtext("description", default="")
        jobs.append(_job(company, title, "", urljoin(base_url, link), description, "rss"))

    if jobs:
        return jobs[:MAX_JOBS_PER_SOURCE]

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


# ---------------------------------------------------------------------------
# Academic/community boards
# ---------------------------------------------------------------------------


def _detail_or_fallback(
    url: str,
    fallback_company: str,
    fallback_title: str,
    fallback_location: str,
    fallback_description: str,
    source_name: str,
) -> dict[str, str]:
    soup = _get_soup(url)
    structured = _json_ld_job(soup, fallback_company, url)
    if structured:
        structured["source"] = source_name
        if not structured["title"]:
            structured["title"] = fallback_title
        if not structured["company"]:
            structured["company"] = fallback_company
        if not structured["location"]:
            structured["location"] = fallback_location
        return structured

    return _job(
        fallback_company,
        _heading_text(soup, ("h1", "h2")) or fallback_title,
        fallback_location,
        url,
        _page_text(soup) or fallback_description,
        source_name,
    )


def fetch_scholarshipdb_jobs(source: dict[str, Any], company: str) -> list[dict[str, str]]:
    listing_urls = source.get("urls") or [source["url"]]
    max_details = int(source.get("max_detail_pages", 30))
    candidates: dict[str, tuple[str, str, str, str]] = {}

    for listing_url in listing_urls:
        soup = _get_soup(str(listing_url))
        for anchor in soup.select("a[href]"):
            href = urljoin(str(listing_url), anchor.get("href", ""))
            path = urlparse(href).path
            if not re.search(r"/(?:jobs|scholarships)-in-[^/]+/", path, re.I):
                continue
            title = clean_text(anchor.get_text(" ", strip=True))
            if len(title) < 8 or title.casefold() in {"apply", "see advertisement", "read more"}:
                continue
            card = _nearest_card_text(anchor)
            listed_company, listed_location = _parse_pipe_metadata(card, title)
            candidates[href] = (title, listed_company or company, listed_location, card)

    jobs: list[dict[str, str]] = []
    for url, (title, listed_company, location, card) in list(candidates.items())[:max_details]:
        try:
            soup = _get_soup(url)
            detail_text = _page_text(soup)
            if re.search(r"\bSTATUS:\s*EXPIRED\b", detail_text, re.I):
                continue
            structured = _json_ld_job(soup, listed_company, url)
            if structured:
                structured["source"] = "scholarshipdb"
                if not structured["location"]:
                    structured["location"] = location
                jobs.append(structured)
                continue

            detail_title = _heading_text(soup, ("h1",)) or title
            headings = [clean_text(tag.get_text(" ", strip=True)) for tag in soup.find_all("h2")]
            detail_company = listed_company
            detail_location = location
            if headings:
                candidate_heading = next(
                    (value for value in headings if value and "scholarshipdb" not in value.casefold()),
                    "",
                )
                if candidate_heading:
                    if "," in candidate_heading:
                        detail_company, detail_location = candidate_heading.rsplit(",", 1)
                    else:
                        detail_company = candidate_heading
            jobs.append(
                _job(
                    detail_company or company,
                    detail_title,
                    detail_location,
                    url,
                    detail_text or card,
                    "scholarshipdb",
                )
            )
        except requests.RequestException:
            jobs.append(_job(listed_company, title, location, url, card, "scholarshipdb"))

    return jobs[:MAX_JOBS_PER_SOURCE]


def fetch_findapostdoc_jobs(source: dict[str, Any], company: str) -> list[dict[str, str]]:
    listing_url = source["url"]
    max_details = int(source.get("max_detail_pages", 50))
    soup = _get_soup(listing_url)
    candidates: dict[str, tuple[str, str]] = {}

    for anchor in soup.select("a[href]"):
        href = urljoin(listing_url, anchor.get("href", ""))
        if not re.search(r"/search/Job-Details\.aspx\?[^#]*\bjobcode=\d+", href, re.I):
            continue
        title = clean_text(anchor.get_text(" ", strip=True))
        if len(title) < 8:
            continue
        candidates[href] = (title, _nearest_card_text(anchor))

    jobs: list[dict[str, str]] = []
    for url, (title, card) in list(candidates.items())[:max_details]:
        try:
            detail = _get_soup(url)
            text = _page_text(detail)
            if "application date has expired" in text.casefold():
                continue
            structured = _json_ld_job(detail, company, url)
            if structured:
                structured["source"] = "findapostdoc"
                jobs.append(structured)
                continue

            detail_title = _heading_text(detail, ("h1",)) or title
            company_heading = ""
            for heading in detail.find_all(["h2", "h3"]):
                value = clean_text(heading.get_text(" ", strip=True))
                if value and not re.search(r"postdoc|job details|back to results", value, re.I):
                    company_heading = value
                    break
            location_match = re.search(
                r"\bLocation\s*:\s*(.{2,120}?)(?:\bDeadline\s*:|\bSalary\s*:|\bContact\s*:|$)",
                text,
                re.I,
            )
            jobs.append(
                _job(
                    company_heading or company,
                    detail_title,
                    location_match.group(1) if location_match else "",
                    url,
                    text or card,
                    "findapostdoc",
                )
            )
        except requests.RequestException:
            jobs.append(_job(company, title, "", url, card, "findapostdoc"))

    return jobs[:MAX_JOBS_PER_SOURCE]


def fetch_researchjobs_cz_jobs(source: dict[str, Any], company: str) -> list[dict[str, str]]:
    listing_urls = source.get("urls") or [source["url"]]
    max_details = int(source.get("max_detail_pages", 40))
    candidates: dict[str, tuple[str, str]] = {}

    for listing_url in listing_urls:
        soup = _get_soup(str(listing_url))
        for anchor in soup.select("a[href]"):
            href = urljoin(str(listing_url), anchor.get("href", ""))
            parsed = urlparse(href)
            if parsed.netloc not in {"researchjobs.cz", "www.researchjobs.cz"}:
                continue
            if not re.fullmatch(r"/job/[^/]+/", parsed.path):
                continue
            title = clean_text(anchor.get_text(" ", strip=True))
            if len(title) < 8:
                continue
            candidates[href] = (title, _nearest_card_text(anchor))

    jobs: list[dict[str, str]] = []
    for url, (title, card) in list(candidates.items())[:max_details]:
        try:
            detail = _get_soup(url)
            text = _page_text(detail)
            if re.search(r"no more available|inzerát je již neplatný", text, re.I):
                continue
            structured = _json_ld_job(detail, company, url)
            if structured:
                structured["source"] = "researchjobs.cz"
                jobs.append(structured)
                continue

            detail_title = _heading_text(detail, ("h1",)) or title
            detail_company = company
            location = "Czech Republic"
            h1 = detail.find("h1")
            metadata_list = h1.find_next("ul") if h1 else None
            if metadata_list:
                items = [clean_text(item.get_text(" ", strip=True)) for item in metadata_list.find_all("li")]
                items = [item for item in items if item]
                if len(items) >= 2:
                    detail_company = items[1]
                if len(items) >= 3:
                    location = f"{items[2]}, Czech Republic"
            jobs.append(
                _job(detail_company, detail_title, location, url, text or card, "researchjobs.cz")
            )
        except requests.RequestException:
            jobs.append(_job(company, title, "Czech Republic", url, card, "researchjobs.cz"))

    return jobs[:MAX_JOBS_PER_SOURCE]


def fetch_ccl_jobs(source: dict[str, Any], company: str) -> list[dict[str, str]]:
    listing_url = source["url"]
    max_details = int(source.get("max_detail_pages", 35))
    max_age_days = source.get("max_age_days")
    max_age = int(max_age_days) if max_age_days is not None else None
    soup = _get_soup(listing_url)
    candidates: dict[str, str] = {}

    for anchor in soup.select("a[href]"):
        href = urljoin(listing_url, anchor.get("href", ""))
        if not re.search(r"/cca/jobs/joblist/mess\d+\.shtml$", urlparse(href).path, re.I):
            continue
        raw_title = clean_text(anchor.get_text(" ", strip=True))
        if not _is_within_age(_parse_date_prefix(raw_title), max_age):
            continue
        title = re.sub(r"^\s*\d{2}[.-]\d{2}[.-]\d{2}\s*", "", raw_title)
        if len(title) >= 8:
            candidates[href] = title

    jobs: list[dict[str, str]] = []
    for url, title in list(candidates.items())[:max_details]:
        try:
            detail = _get_soup(url)
            text = _page_text(detail)
            line_text = detail.get_text("\n", strip=True)
            subject_match = re.search(r"^\s*Subject:\s*([^\r\n]+)", line_text, re.I | re.M)
            detail_title = clean_text(subject_match.group(1)) if subject_match else title
            detail_title = re.sub(r"^\s*\d{2}[.-]\d{2}[.-]\d{2}\s*", "", detail_title)
            jobs.append(_job(company, detail_title, "", url, text, "ccl.net"))
        except requests.RequestException:
            jobs.append(_job(company, title, "", url, title, "ccl.net"))

    return jobs[:MAX_JOBS_PER_SOURCE]


def _charmm_detail(url: str, company: str, expiry_grace_days: int) -> dict[str, str] | None:
    soup = _get_soup(url)
    structured = _json_ld_job(soup, company, url)
    if structured:
        structured["source"] = "charmm-gui"
        return structured

    text = _page_text(soup)
    match = re.search(
        r"\bTitle\s+(?P<title>.+?)\s+\bDate\s+(?P<date>\d{4}-\d{2}-\d{2})\s+"
        r"\bLocation\s+(?P<location>.+?)\s+\bDescription\s+(?P<description>.+)",
        text,
        re.I | re.S,
    )
    if not match:
        return None
    try:
        posted = dt.date.fromisoformat(match.group("date"))
    except ValueError:
        posted = None
    if posted is not None:
        today = dt.datetime.now(dt.timezone.utc).date()
        if posted < today - dt.timedelta(days=expiry_grace_days):
            return None

    description = re.split(
        r"\b(?:Post New Job|Jobs and Events List|Subscribe to Mailing List|Contact info)\b",
        match.group("description"),
        maxsplit=1,
        flags=re.I,
    )[0]
    return _job(
        company,
        match.group("title"),
        match.group("location"),
        url,
        description,
        "charmm-gui",
    )


def fetch_charmm_gui_jobs(source: dict[str, Any], company: str) -> list[dict[str, str]]:
    listing_url = source["url"]
    max_details = int(source.get("max_detail_pages", 50))
    expiry_grace_days = int(source.get("expiry_grace_days", 3))
    soup = _get_soup(listing_url)
    links: list[str] = []

    for anchor in soup.select("a[href]"):
        href = urljoin(listing_url, anchor.get("href", ""))
        query = parse_qs(urlparse(href).query)
        if query.get("doc") != ["jobs"] or query.get("view") != ["single"]:
            continue
        if not query.get("id") or not str(query["id"][0]).isdigit():
            continue
        row = anchor.find_parent("tr")
        row_text = clean_text(row.get_text(" ", strip=True)) if row else ""
        date_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", row_text)
        if date_match:
            try:
                end_date = dt.date.fromisoformat(date_match.group(1))
            except ValueError:
                end_date = None
            if end_date is not None:
                today = dt.datetime.now(dt.timezone.utc).date()
                if end_date < today - dt.timedelta(days=expiry_grace_days):
                    continue
        if href not in links:
            links.append(href)

    jobs: list[dict[str, str]] = []
    for url in links[:max_details]:
        try:
            job = _charmm_detail(url, company, expiry_grace_days)
            if job:
                jobs.append(job)
        except requests.RequestException:
            continue
    return jobs[:MAX_JOBS_PER_SOURCE]


# ---------------------------------------------------------------------------
# Broad academic/public aggregators
# ---------------------------------------------------------------------------


def _extract_location_from_text(text: str, default: str = "") -> str:
    patterns = (
        r"\bWork Locations?\s*:\s*Number of offers:\s*\d+\s*,\s*(.+?)(?:\bResearch Field\b|\bResearcher Profile\b|\bFunding Programme\b|\bApplication Deadline\b|$)",
        r"\bLocation\s*:\s*(.+?)(?:\bSalary\b|\bHours\b|\bContract Type\b|\bPlaced On\b|\bCloses\b|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I | re.S)
        if match:
            return clean_text(match.group(1))[:300]
    return default


def fetch_euraxess_jobs(source: dict[str, Any], company: str) -> list[dict[str, str]]:
    base_url = str(source["url"])
    pages = max(1, min(int(source.get("pages", 5)), 20))
    candidates: dict[str, tuple[str, str, str]] = {}

    for page in range(pages):
        separator = "&" if "?" in base_url else "?"
        listing_url = base_url if page == 0 else f"{base_url}{separator}page={page}"
        soup = _get_soup(listing_url)
        for anchor in soup.select("a[href]"):
            href = urljoin(listing_url, anchor.get("href", ""))
            if not re.fullmatch(r"https?://(?:www\.)?euraxess\.ec\.europa\.eu/jobs/\d+/?", href, re.I):
                continue
            title = clean_text(anchor.get_text(" ", strip=True))
            if len(title) < 8:
                continue
            card = _nearest_card_text(anchor)
            location = _extract_location_from_text(card)
            candidates[href] = (title, location, card)

    return [
        _job(company, title, location, url, card, "euraxess")
        for url, (title, location, card) in list(candidates.items())[:MAX_JOBS_PER_SOURCE]
    ]


def _fetch_keyword_board_details(
    source: dict[str, Any],
    company: str,
    link_pattern: str,
    source_name: str,
    default_location: str = "",
) -> list[dict[str, str]]:
    listing_urls = source.get("urls") or [source["url"]]
    max_details = int(source.get("max_detail_pages", 35))
    candidates: dict[str, tuple[str, str, str]] = {}

    for listing_url in listing_urls:
        soup = _get_soup(str(listing_url))
        for anchor in soup.select("a[href]"):
            href = urljoin(str(listing_url), anchor.get("href", ""))
            if not re.search(link_pattern, urlparse(href).path, re.I):
                continue
            title = clean_text(anchor.get_text(" ", strip=True))
            if len(title) < 8 or title.casefold() in {"apply", "read more", "save"}:
                continue
            card = _nearest_card_text(anchor)
            candidates[href] = (title, _extract_location_from_text(card, default_location), card)

        # Some modern boards embed vacancy URLs in JSON/script data rather than anchors.
        if source_name == "academictransfer":
            for href in _extract_embedded_paths(
                soup,
                str(listing_url),
                r"(?:https?://(?:www\.)?academictransfer\.com)?/en/jobs/\d+/[^\"'<>?#]+/?",
            ):
                candidates.setdefault(href, ("Academic vacancy", default_location, ""))

    jobs: list[dict[str, str]] = []
    for url, (title, location, card) in list(candidates.items())[:max_details]:
        try:
            jobs.append(
                _detail_or_fallback(url, company, title, location, card, source_name)
            )
        except requests.RequestException:
            jobs.append(_job(company, title, location, url, card, source_name))
    return jobs[:MAX_JOBS_PER_SOURCE]


def fetch_academictransfer_jobs(source: dict[str, Any], company: str) -> list[dict[str, str]]:
    return _fetch_keyword_board_details(
        source,
        company,
        r"^/en/jobs/\d+/[^/]+/?$",
        "academictransfer",
        "Netherlands",
    )


def fetch_jobs_ac_uk_jobs(source: dict[str, Any], company: str) -> list[dict[str, str]]:
    return _fetch_keyword_board_details(
        source,
        company,
        r"^/job/[A-Z0-9]+(?:/[^/]+)?/?$",
        "jobs.ac.uk",
        "United Kingdom",
    )


def _string_value(value: Any) -> str:
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, dict):
        for key in ("name", "title", "value", "description"):
            if value.get(key):
                return clean_text(value[key])
    if isinstance(value, list):
        return ", ".join(filter(None, (_string_value(item) for item in value)))
    return clean_text(value)


def fetch_jobbnorge_jobs(source: dict[str, Any], company: str) -> list[dict[str, str]]:
    response = SESSION.get(source["url"], timeout=30)
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict):
        items = payload.get("jobs") or payload.get("data") or payload.get("results") or []
    else:
        items = payload
    if not isinstance(items, list):
        return []

    jobs: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = item.get("title") or item.get("jobTitle") or item.get("positionTitle")
        url = item.get("link") or item.get("url") or item.get("applyUrl")
        employer = _string_value(item.get("employer") or item.get("company") or company)
        location = _string_value(
            item.get("location")
            or item.get("municipality")
            or item.get("city")
            or item.get("county")
        )
        if location and "norway" not in location.casefold():
            location = f"{location}, Norway"
        elif not location:
            location = "Norway"
        description = item.get("summary") or item.get("description") or item.get("jobScope") or ""
        if title and url:
            jobs.append(_job(employer or company, title, location, url, description, "jobbnorge"))
    return jobs[:MAX_JOBS_PER_SOURCE]


def fetch_arbeitnow_jobs(source: dict[str, Any], company: str) -> list[dict[str, str]]:
    pages = max(1, min(int(source.get("pages", 5)), 20))
    jobs: list[dict[str, str]] = []
    for page in range(1, pages + 1):
        response = SESSION.get(source["url"], params={"page": page}, timeout=30)
        response.raise_for_status()
        payload = response.json()
        items = payload.get("data", []) if isinstance(payload, dict) else []
        if not isinstance(items, list) or not items:
            break
        for item in items:
            if not isinstance(item, dict):
                continue
            location = item.get("location") or ""
            if item.get("remote") and "remote" not in str(location).casefold():
                location = f"{location}, Remote" if location else "Remote"
            description_parts = [
                item.get("description") or "",
                " ".join(item.get("tags") or []) if isinstance(item.get("tags"), list) else "",
                " ".join(item.get("job_types") or []) if isinstance(item.get("job_types"), list) else "",
            ]
            jobs.append(
                _job(
                    item.get("company_name") or company,
                    item.get("title"),
                    location,
                    item.get("url") or item.get("slug"),
                    " ".join(description_parts),
                    "arbeitnow",
                )
            )
        if isinstance(payload, dict) and page >= int(payload.get("last_page") or pages):
            break
    return jobs[:MAX_JOBS_PER_SOURCE]


# ---------------------------------------------------------------------------
# Additional official scientific and research-software boards
# ---------------------------------------------------------------------------


_DISCOVERY_TERMS = (
    "computational", "molecular", "chemistry", "chemical", "biophysics",
    "biophysical", "simulation", "modelling", "modeling", "quantum",
    "electronic structure", "materials", "soft matter", "surface science",
    "scientific software", "research software", "software engineer", "hpc",
    "high-performance computing", "bioinformatics", "structural biology",
    "protein", "drug discovery", "machine learning", "artificial intelligence",
    "theoretical", "physical chemistry", "nanoscience", "nanotechnology",
)


def _discovery_relevant(*values: Any) -> bool:
    text = clean_text(" ".join(str(value or "") for value in values)).casefold()
    return any(term in text for term in _DISCOVERY_TERMS)


def _unique_jobs(jobs: list[dict[str, str]]) -> list[dict[str, str]]:
    """Remove exact cross-page duplicates while preserving source order."""
    seen: set[tuple[str, str, str, str]] = set()
    unique: list[dict[str, str]] = []
    for job in jobs:
        key = (
            clean_text(job.get("company")).casefold(),
            clean_text(job.get("title")).casefold(),
            clean_text(job.get("location")).casefold(),
            str(job.get("url") or "").rstrip("/").casefold(),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(job)
    return unique[:MAX_JOBS_PER_SOURCE]


def _extract_embedded_paths(
    soup: BeautifulSoup,
    listing_url: str,
    path_pattern: str,
) -> list[str]:
    """Find job URLs embedded in script/JSON attributes as well as normal anchors."""
    candidates: list[str] = []
    raw = html_lib.unescape(str(soup)).replace("\\/", "/")
    regex = re.compile(path_pattern, re.I)

    for match in regex.finditer(raw):
        value = match.group(0).strip('"\'<> ,')
        url = urljoin(listing_url, value)
        if url not in candidates:
            candidates.append(url)
    return candidates


def _text_between_labels(text: str, start: str, end_labels: tuple[str, ...]) -> str:
    start_match = re.search(re.escape(start) + r"\s*", text, re.I)
    if not start_match:
        return ""
    end = len(text)
    for label in end_labels:
        match = re.search(r"\s*" + re.escape(label) + r"\s*", text[start_match.end():], re.I)
        if match:
            end = min(end, start_match.end() + match.start())
    return clean_text(text[start_match.end():end])


def fetch_molssi_jobs(source: dict[str, Any], company: str) -> list[dict[str, str]]:
    soup = _get_soup(str(source["url"]))
    heading = next(
        (
            tag
            for tag in soup.find_all(["h2", "h3", "h4"])
            if "active job posts" in clean_text(tag.get_text(" ", strip=True)).casefold()
        ),
        None,
    )
    listing = heading.find_next(["ul", "ol"]) if heading else soup.find(["ul", "ol"])
    if not listing:
        return []

    max_age_days = int(source.get("max_age_days", 550))
    jobs: list[dict[str, str]] = []
    for item in listing.find_all("li", recursive=False) or listing.find_all("li"):
        full_text = clean_text(item.get_text(" ", strip=True))
        if len(full_text) < 12:
            continue

        date_match = re.search(
            r"\((\d{1,2}\s+[A-Za-z]+\s+\d{4}|\d{1,2}\s+[A-Za-z]+,?\s+\d{4})\)\s*$",
            full_text,
        )
        posted_date = None
        if date_match:
            for fmt in ("%d %B %Y", "%d %b %Y", "%d %B, %Y", "%d %b, %Y"):
                try:
                    posted_date = dt.datetime.strptime(date_match.group(1), fmt).date()
                    break
                except ValueError:
                    continue
        if not _is_within_age(posted_date, max_age_days):
            continue

        first_line = date_match and full_text[: date_match.start()].strip() or full_text
        first_line = re.split(r"\b(?:LOCATION|OFFICE LOCATION|HOW TO APPLY)\b", first_line, maxsplit=1, flags=re.I)[0]
        parts = [clean_text(part) for part in first_line.split(",") if clean_text(part)]
        title = parts[0] if parts else first_line
        listed_company = parts[1] if len(parts) > 1 else company
        location = ", ".join(parts[2:4]) if len(parts) > 2 else ""
        anchor = item.find("a", href=True)
        url = urljoin(str(source["url"]), anchor.get("href", "")) if anchor else str(source["url"])
        jobs.append(_job(listed_company, title, location, url, full_text, "molssi"))
    return _unique_jobs(jobs)


def fetch_cecam_jobs(source: dict[str, Any], company: str) -> list[dict[str, str]]:
    listing_url = str(source["url"])
    max_details = int(source.get("max_detail_pages", 80))
    soup = _get_soup(listing_url)
    candidates: dict[str, tuple[str, str]] = {}
    for anchor in soup.select("a[href]"):
        href = urljoin(listing_url, anchor.get("href", ""))
        if not re.search(r"/careers-details/[^/?#]+/?$", urlparse(href).path, re.I):
            continue
        card = _nearest_card_text(anchor)
        card_parent = anchor.find_parent(["article", "section", "div", "li"])
        heading = card_parent.find(["h2", "h3", "h4"]) if card_parent else None
        title = clean_text(heading.get_text(" ", strip=True)) if heading else ""
        if not title or title.casefold() in {"read more", "careers"}:
            detail_title = clean_text(anchor.get("title", ""))
            title = detail_title if len(detail_title) >= 8 else card[:300]
        candidates[href] = (title, card)

    jobs: list[dict[str, str]] = []
    for url, (title, card) in list(candidates.items())[:max_details]:
        try:
            jobs.append(_detail_or_fallback(url, company, title, "", card, "cecam"))
        except requests.RequestException:
            jobs.append(_job(company, title, "", url, card, "cecam"))
    return _unique_jobs(jobs)


def _academicjobsonline_detail(url: str, fallback_company: str, fallback_title: str) -> dict[str, str] | None:
    soup = _get_soup(url)
    text = _page_text(soup)
    if re.search(r"\b(?:position closed|listing expired|deadline\s+\d{4}/\d{2}/\d{2}.*passed)\b", text, re.I):
        return None
    deadline_match = re.search(r"Appl Deadline:\s*(\d{4}/\d{2}/\d{2})", text, re.I)
    if deadline_match:
        try:
            deadline = dt.datetime.strptime(deadline_match.group(1), "%Y/%m/%d").date()
            if deadline < dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=2):
                return None
        except ValueError:
            pass
    company = _heading_text(soup, ("h2", "h3")) or fallback_company
    title = _text_between_labels(text, "Position Title:", ("Position Type:",)) or fallback_title
    location = _text_between_labels(text, "Position Location:", ("Subject Area:", "Appl Deadline:"))
    description = _text_between_labels(text, "Position Description:", ("Contact:", "Postal Mail:", "Web Page:")) or text
    return _job(company, title, location, url, description, "academicjobsonline")


def fetch_academicjobsonline_jobs(source: dict[str, Any], company: str) -> list[dict[str, str]]:
    listing_url = str(source["url"])
    max_details = int(source.get("max_detail_pages", 180))
    soup = _get_soup(listing_url)
    candidates: dict[str, tuple[str, str]] = {}

    for anchor in soup.select("a[href]"):
        href = urljoin(listing_url, anchor.get("href", ""))
        if not re.fullmatch(r"https?://(?:www\.)?academicjobsonline\.org/ajo/jobs/\d+/?", href, re.I):
            continue
        row = anchor.find_parent("li") or anchor.parent
        row_text = clean_text(row.get_text(" ", strip=True)) if isinstance(row, Tag) else clean_text(anchor.get_text())
        title = re.sub(r"^\[[^\]]+\]\s*", "", row_text).strip()
        heading = anchor.find_previous("h3")
        listed_company = clean_text(heading.get_text(" ", strip=True)) if heading else company
        title = title or clean_text(anchor.get_text())
        if not _discovery_relevant(title, listed_company):
            continue
        candidates[href] = (title, listed_company)

    jobs: list[dict[str, str]] = []
    for url, (title, listed_company) in list(candidates.items())[:max_details]:
        try:
            detail = _academicjobsonline_detail(url, listed_company, title)
            if detail:
                jobs.append(detail)
        except requests.RequestException:
            jobs.append(_job(listed_company, title, "", url, title, "academicjobsonline"))
    return _unique_jobs(jobs)


def _iscb_detail(
    url: str,
    fallback_company: str,
    fallback_title: str,
    fallback_location: str,
) -> dict[str, str] | None:
    soup = _get_soup(url)
    title = _heading_text(soup, ("h1",)) or fallback_title
    text = _page_text(soup)
    if "posting expired" in title.casefold() or "posting expired" in text[:500].casefold():
        return None
    description = _text_between_labels(text, "Description", ("Qualifications", "Start date", "How to Apply", "Contact")) or text
    return _job(fallback_company, title, fallback_location, url, description, "iscb")


def fetch_iscb_jobs(source: dict[str, Any], company: str) -> list[dict[str, str]]:
    base_url = str(source["url"])
    pages = max(1, min(int(source.get("pages", 4)), 20))
    max_details = int(source.get("max_detail_pages", 160))
    candidates: dict[str, tuple[str, str, str]] = {}

    for page in range(1, pages + 1):
        separator = "&" if "?" in base_url else "?"
        soup = _get_soup(f"{base_url}{separator}page={page}")
        for anchor in soup.select("a[href]"):
            href = urljoin(base_url, anchor.get("href", ""))
            if not re.search(r"/jobs/view/\d+/?$", urlparse(href).path, re.I):
                continue
            row = anchor.find_parent("tr")
            cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["td", "th"])] if row else []
            if len(cells) >= 5:
                location, title, listed_company = cells[1], cells[2], cells[4]
            else:
                card = _nearest_card_text(anchor)
                title = clean_text(anchor.get("title", "")) or clean_text(anchor.get_text(" ", strip=True))
                listed_company, location = company, ""
                if title.casefold() in {"view", "details"}:
                    title = card
            if not _discovery_relevant(title, listed_company):
                continue
            candidates[href] = (title, listed_company or company, location)

    jobs: list[dict[str, str]] = []
    for url, (title, listed_company, location) in list(candidates.items())[:max_details]:
        try:
            detail = _iscb_detail(url, listed_company, title, location)
            if detail:
                jobs.append(detail)
        except requests.RequestException:
            jobs.append(_job(listed_company, title, location, url, title, "iscb"))
    return _unique_jobs(jobs)


def fetch_society_rse_jobs(source: dict[str, Any], company: str) -> list[dict[str, str]]:
    listing_url = str(source["url"])
    max_details = int(source.get("max_detail_pages", 100))
    soup = _get_soup(listing_url)
    candidates: dict[str, tuple[str, str]] = {}
    for anchor in soup.select("a[href]"):
        href = urljoin(listing_url, anchor.get("href", ""))
        if not re.search(r"/job/[^/?#]+/?$", urlparse(href).path, re.I):
            continue
        title = clean_text(anchor.get_text(" ", strip=True))
        card = _nearest_card_text(anchor)
        if len(title) < 8 or title.casefold() in {"read more", "apply"}:
            heading = anchor.find_parent(["article", "li", "div"])
            heading = heading.find(["h2", "h3", "h4"]) if heading else None
            title = clean_text(heading.get_text(" ", strip=True)) if heading else card[:250]
        candidates[href] = (title, card)

    jobs: list[dict[str, str]] = []
    for url, (title, card) in list(candidates.items())[:max_details]:
        try:
            jobs.append(_detail_or_fallback(url, company, title, "", card, "society-rse"))
        except requests.RequestException:
            jobs.append(_job(company, title, "", url, card, "society-rse"))
    return _unique_jobs(jobs)


def fetch_max_planck_jobs(source: dict[str, Any], company: str) -> list[dict[str, str]]:
    listing_url = str(source["url"])
    max_details = int(source.get("max_detail_pages", 160))
    soup = _get_soup(listing_url)
    candidates: dict[str, tuple[str, str, str]] = {}
    for anchor in soup.select("a[href]"):
        href = urljoin(listing_url, anchor.get("href", ""))
        if not re.fullmatch(r"https?://(?:www\.)?mpg\.de/\d+/[^/?#]+/?", href, re.I):
            continue
        card = _nearest_card_text(anchor)
        if not re.search(r"\b(?:20\d{2}|Max Planck Institute)\b", card, re.I):
            continue
        title = clean_text(anchor.get_text(" ", strip=True))
        if len(title) < 8:
            parent = anchor.find_parent(["article", "li", "div"])
            heading = parent.find(["h2", "h3", "h4"]) if parent else None
            title = clean_text(heading.get_text(" ", strip=True)) if heading else card[:250]
        parent = anchor.find_parent(["article", "li", "section", "div"])
        metadata = [
            clean_text(tag.get_text(" ", strip=True))
            for tag in parent.find_all(["p", "span", "div"], recursive=True)
        ] if parent else []
        institute_line = next(
            (value for value in metadata if "max planck institute" in value.casefold()),
            "",
        )
        listed_company = institute_line.rsplit(",", 1)[0].strip() if institute_line else company
        location = institute_line.rsplit(",", 1)[1].strip() if "," in institute_line else "Germany"
        if not _discovery_relevant(title, listed_company):
            continue
        candidates[href] = (title, listed_company, location)

    jobs: list[dict[str, str]] = []
    for url, (title, listed_company, location) in list(candidates.items())[:max_details]:
        try:
            jobs.append(_detail_or_fallback(url, listed_company, title, location, title, "max-planck"))
        except requests.RequestException:
            jobs.append(_job(listed_company, title, location, url, title, "max-planck"))
    return _unique_jobs(jobs)


def fetch_leibniz_jobs(source: dict[str, Any], company: str) -> list[dict[str, str]]:
    listing_url = str(source["url"])
    max_details = int(source.get("max_detail_pages", 160))
    soup = _get_soup(listing_url)
    candidates: dict[str, tuple[str, str, str]] = {}
    for anchor in soup.select("a[href]"):
        href = urljoin(listing_url, anchor.get("href", ""))
        if not re.search(r"/en/careers/jobs/detail/job/show/Job/[^/?#]+/?$", urlparse(href).path, re.I):
            continue
        card = _nearest_card_text(anchor)
        title = clean_text(anchor.get_text(" ", strip=True))
        if len(title) < 8 or title.casefold() in {"details", "read more"}:
            parent = anchor.find_parent(["article", "li", "div"])
            heading = parent.find(["h2", "h3", "h4"]) if parent else None
            title = clean_text(heading.get_text(" ", strip=True)) if heading else card[:250]
        parent = anchor.find_parent(["article", "li", "section", "div"])
        metadata = [
            clean_text(tag.get_text(" ", strip=True))
            for tag in parent.find_all(["p", "span", "div"], recursive=True)
        ] if parent else []
        listed_company = next(
            (value for value in metadata if value and value != title and len(value) < 350),
            company,
        )
        location = listed_company.rsplit(",", 1)[-1].strip() if "," in listed_company else "Germany"
        if not _discovery_relevant(title, listed_company):
            continue
        candidates[href] = (title, listed_company, location)

    jobs: list[dict[str, str]] = []
    for url, (title, listed_company, location) in list(candidates.items())[:max_details]:
        try:
            jobs.append(_detail_or_fallback(url, listed_company, title, location, title, "leibniz"))
        except requests.RequestException:
            jobs.append(_job(listed_company, title, location, url, title, "leibniz"))
    return _unique_jobs(jobs)



def _future_deadline_from_text(text: str) -> bool:
    match = re.search(
        r"(?:deadline(?: to apply)?|application deadline)\s*:?\s*(\d{4}-\d{2}-\d{2}|\d{1,2}\s+[A-Za-z]+\s+\d{4})",
        text,
        re.I,
    )
    if not match:
        return True
    for fmt in ("%Y-%m-%d", "%d %B %Y", "%d %b %Y"):
        try:
            deadline = dt.datetime.strptime(match.group(1), fmt).date()
            return deadline >= dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=2)
        except ValueError:
            continue
    return True


def fetch_inria_jobs(source: dict[str, Any], company: str) -> list[dict[str, str]]:
    listing_url = str(source["url"])
    max_details = int(source.get("max_detail_pages", 80))
    soup = _get_soup(listing_url)
    candidates: dict[str, tuple[str, str, str]] = {}
    for anchor in soup.select("a[href]"):
        href = urljoin(listing_url, anchor.get("href", ""))
        if not re.search(r"/public/classic/en/offres/20\d{2}-\d+/?$", urlparse(href).path, re.I):
            continue
        title = clean_text(anchor.get_text(" ", strip=True))
        card = _nearest_card_text(anchor)
        if not _future_deadline_from_text(card) or not _discovery_relevant(title, card):
            continue
        city_match = re.search(r"Town/city\s*:\s*(.+?)(?:Inria Team|Deadline|$)", card, re.I)
        location = clean_text(city_match.group(1)) + ", France" if city_match else "France"
        candidates[href] = (title, location, card)

    jobs: list[dict[str, str]] = []
    for url, (title, location, card) in list(candidates.items())[:max_details]:
        try:
            jobs.append(_detail_or_fallback(url, company, title, location, card, "inria"))
        except requests.RequestException:
            jobs.append(_job(company, title, location, url, card, "inria"))
    return _unique_jobs(jobs)


def fetch_tyc_jobs(source: dict[str, Any], company: str) -> list[dict[str, str]]:
    listing_url = str(source["url"])
    soup = _get_soup(listing_url)
    jobs: list[dict[str, str]] = []
    for heading in soup.find_all(["h2", "h3", "h4"]):
        title = clean_text(heading.get_text(" ", strip=True))
        if not title or title.casefold() in {"jobs", "opportunities"}:
            continue
        parent = heading.find_parent(["article", "li", "section", "div"]) or heading.parent
        card = clean_text(parent.get_text(" ", strip=True)) if isinstance(parent, Tag) else title
        if not _future_deadline_from_text(card) or not _discovery_relevant(title, card):
            continue
        institution_match = re.search(r"Institution\s*:\s*(.+?)(?:Application deadline|$)", card, re.I)
        listed_company = clean_text(institution_match.group(1)) if institution_match else company
        anchor = heading.find("a", href=True) or (parent.find("a", href=True) if isinstance(parent, Tag) else None)
        url = urljoin(listing_url, anchor.get("href", "")) if anchor else listing_url
        jobs.append(_job(listed_company, title, "United Kingdom", url, card, "thomas-young-centre"))
    return _unique_jobs(jobs)


def fetch_helmholtz_ai_jobs(source: dict[str, Any], company: str) -> list[dict[str, str]]:
    listing_url = str(source["url"])
    soup = _get_soup(listing_url)
    jobs: list[dict[str, str]] = []
    for anchor in soup.select("a[href]"):
        title = clean_text(anchor.get_text(" ", strip=True))
        href = urljoin(listing_url, anchor.get("href", ""))
        if len(title) < 8 or not _discovery_relevant(title):
            continue
        if urlparse(href).netloc.endswith("helmholtz.ai") and urlparse(href).path in {"", "/", "/latest/careers/"}:
            continue
        institution_heading = anchor.find_previous(["h2", "h3", "h4"])
        listed_company = clean_text(institution_heading.get_text(" ", strip=True)) if institution_heading else company
        card = _nearest_card_text(anchor)
        jobs.append(_job(listed_company, title, "Germany", href, card, "helmholtz-ai"))
    return _unique_jobs(jobs)


def fetch_embl_partner_jobs(source: dict[str, Any], company: str) -> list[dict[str, str]]:
    listing_url = str(source["url"])
    soup = _get_soup(listing_url)
    jobs: list[dict[str, str]] = []
    for heading in soup.find_all(["h3", "h4", "h5"]):
        title = clean_text(heading.get_text(" ", strip=True))
        if not title or title.casefold().startswith("jobs at"):
            continue
        chunks: list[str] = []
        cursor = heading.find_next_sibling()
        anchor = heading.find("a", href=True)
        while cursor is not None and getattr(cursor, "name", None) not in {"h2", "h3", "h4", "h5"}:
            if isinstance(cursor, Tag):
                chunks.append(clean_text(cursor.get_text(" ", strip=True)))
                anchor = anchor or cursor.find("a", href=True)
            cursor = cursor.find_next_sibling()
        card = clean_text(" ".join(chunks))
        if "deadline" not in card.casefold() or not _future_deadline_from_text(card):
            continue
        if not _discovery_relevant(title, card):
            continue
        institution_heading = heading.find_previous(["h2", "h3"])
        listed_company = clean_text(institution_heading.get_text(" ", strip=True)) if institution_heading else company
        url = urljoin(listing_url, anchor.get("href", "")) if anchor else listing_url
        location_match = re.search(r"\b([A-Z][A-Za-zÀ-ÿ .'-]+,\s*(?:Finland|Norway|Sweden|Germany|United Kingdom|France|Italy|Spain))\b", card)
        location = clean_text(location_match.group(1)) if location_match else "Europe"
        jobs.append(_job(listed_company, title, location, url, card, "embl-partners"))
    return _unique_jobs(jobs)


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
    if source_type == "scholarshipdb":
        return fetch_scholarshipdb_jobs(source, company)
    if source_type == "findapostdoc":
        return fetch_findapostdoc_jobs(source, company)
    if source_type == "researchjobs_cz":
        return fetch_researchjobs_cz_jobs(source, company)
    if source_type == "ccl":
        return fetch_ccl_jobs(source, company)
    if source_type == "charmm_gui":
        return fetch_charmm_gui_jobs(source, company)
    if source_type == "euraxess":
        return fetch_euraxess_jobs(source, company)
    if source_type == "academictransfer":
        return fetch_academictransfer_jobs(source, company)
    if source_type == "jobs_ac_uk":
        return fetch_jobs_ac_uk_jobs(source, company)
    if source_type == "jobbnorge":
        return fetch_jobbnorge_jobs(source, company)
    if source_type == "arbeitnow":
        return fetch_arbeitnow_jobs(source, company)
    if source_type == "molssi":
        return fetch_molssi_jobs(source, company)
    if source_type == "cecam":
        return fetch_cecam_jobs(source, company)
    if source_type == "academicjobsonline":
        return fetch_academicjobsonline_jobs(source, company)
    if source_type == "iscb":
        return fetch_iscb_jobs(source, company)
    if source_type == "society_rse":
        return fetch_society_rse_jobs(source, company)
    if source_type == "max_planck":
        return fetch_max_planck_jobs(source, company)
    if source_type == "leibniz":
        return fetch_leibniz_jobs(source, company)
    if source_type == "inria":
        return fetch_inria_jobs(source, company)
    if source_type == "tyc":
        return fetch_tyc_jobs(source, company)
    if source_type == "helmholtz_ai":
        return fetch_helmholtz_ai_jobs(source, company)
    if source_type == "embl_partners":
        return fetch_embl_partner_jobs(source, company)
    if source_type == "restricted":
        raise RuntimeError(source.get("disabled_reason") or "Automated access is disabled for this source")
    raise ValueError(f"Unsupported source_type: {source_type}")
