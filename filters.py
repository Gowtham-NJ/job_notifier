from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any


_SPACE_RE = re.compile(r"\s+")
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class MatchResult:
    matched: bool
    score: int
    priority: str
    seniority: str
    location_ok: bool
    reasons: tuple[str, ...]


def clean_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = _TAG_RE.sub(" ", text)
    return _SPACE_RE.sub(" ", text).strip()


def _normalise(value: Any) -> str:
    return clean_text(value).casefold()


def _contains(text: str, term: str) -> bool:
    needle = _normalise(term)
    if not needle:
        return False
    if len(needle) <= 3 and needle.replace("-", "").isalnum():
        return re.search(rf"(?<![\w-]){re.escape(needle)}(?![\w-])", text) is not None
    return needle in text


def _hits(text: str, terms: list[str]) -> list[str]:
    return [term for term in terms if _contains(text, term)]


def classify_seniority(title: str) -> str:
    text = _normalise(title)
    if any(_contains(text, term) for term in ["postdoc", "postdoctoral", "research fellow"]):
        return "postdoc"
    if any(_contains(text, term) for term in ["intern", "internship", "student"]):
        return "intern"
    if any(
        _contains(text, term)
        for term in ["director", "head of", "principal", "staff", "senior", "lead", "manager"]
    ):
        return "senior"
    if any(_contains(text, term) for term in ["junior", "early career", "graduate", "scientist i"]):
        return "early_career"
    return "unspecified"


def evaluate_job(job: dict[str, Any], profile: dict[str, Any]) -> MatchResult:
    title = _normalise(job.get("title"))
    description = _normalise(job.get("description"))
    location = _normalise(job.get("location"))

    if not title:
        return MatchResult(False, 0, "rejected", "unspecified", False, ("missing title",))

    hard_negative_hits = _hits(title, profile.get("hard_negative_title_terms", []))
    if hard_negative_hits:
        return MatchResult(
            False,
            -20,
            "rejected",
            classify_seniority(title),
            True,
            (f"blocked title: {', '.join(hard_negative_hits[:3])}",),
        )

    title_core = _hits(title, profile.get("title_core_terms", []))
    title_roles = _hits(title, profile.get("title_role_terms", []))
    title_methods = _hits(title, profile.get("method_terms", []))
    description_methods = _hits(description, profile.get("method_terms", []))
    title_domains = _hits(title, profile.get("domain_terms", []))
    description_domains = _hits(description, profile.get("domain_terms", []))
    background_hits = _hits(description, profile.get("background_terms", []))
    negative_description_hits = _hits(description, profile.get("negative_description_terms", []))
    seniority_penalties = _hits(title, profile.get("seniority_penalty_terms", []))

    score = 0
    reasons: list[str] = []

    if title_core:
        points = min(12, 6 * len(title_core))
        score += points
        reasons.append(f"core title: {', '.join(title_core[:3])} (+{points})")

    if title_roles:
        points = min(6, 3 * len(title_roles))
        score += points
        reasons.append(f"role type: {', '.join(title_roles[:2])} (+{points})")

    if title_methods:
        points = min(9, 3 * len(title_methods))
        score += points
        reasons.append(f"methods in title: {', '.join(title_methods[:3])} (+{points})")

    if description_methods:
        points = min(5, len(description_methods))
        score += points
        reasons.append(f"methods: {', '.join(description_methods[:5])} (+{points})")

    if title_domains:
        points = min(6, 3 * len(title_domains))
        score += points
        reasons.append(f"domain in title: {', '.join(title_domains[:2])} (+{points})")

    if description_domains:
        points = min(4, len(description_domains))
        score += points
        reasons.append(f"domain: {', '.join(description_domains[:4])} (+{points})")

    if background_hits:
        points = min(3, len(background_hits))
        score += points
        reasons.append(f"background fit: {', '.join(background_hits[:3])} (+{points})")

    if negative_description_hits:
        points = min(6, 2 * len(negative_description_hits))
        score -= points
        reasons.append(f"negative signals: {', '.join(negative_description_hits[:3])} (-{points})")

    if seniority_penalties:
        points = min(8, 4 * len(seniority_penalties))
        score -= points
        reasons.append(f"seniority penalty: {', '.join(seniority_penalties[:2])} (-{points})")

    location_mode = profile.get("location_mode", "all")
    remote_hits = _hits(location, profile.get("remote_terms", ["remote"]))
    preferred_location_hits = _hits(location, profile.get("preferred_location_terms", []))
    allow_unknown = bool(profile.get("allow_unknown_location", True))

    if location_mode == "all":
        location_ok = True
    elif not location:
        location_ok = allow_unknown
    else:
        location_ok = bool(remote_hits or preferred_location_hits)

    if remote_hits:
        score += 2
        reasons.append("remote-compatible location (+2)")
    elif preferred_location_hits:
        score += 2
        reasons.append(f"preferred location: {preferred_location_hits[0]} (+2)")
    elif not location and allow_unknown:
        reasons.append("location not supplied; retained for review")
    elif not location_ok:
        reasons.append("outside configured target locations")

    # A match must have a credible title signal. Description-only keyword noise is not enough.
    credible_title = bool(
        title_core
        or title_methods
        or title_domains
        or (title_roles and (description_methods or description_domains))
    )

    minimum_score = int(profile.get("minimum_score", 7))
    matched = credible_title and location_ok and score >= minimum_score
    high_threshold = int(profile.get("high_priority_score", 13))
    priority = "high" if matched and score >= high_threshold else "standard" if matched else "rejected"

    return MatchResult(
        matched=matched,
        score=score,
        priority=priority,
        seniority=classify_seniority(title),
        location_ok=location_ok,
        reasons=tuple(reasons),
    )
