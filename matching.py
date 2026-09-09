from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from eligibility import doctoral_training_reason, experimental_role_reason


_DOCTORAL_TARGET_RE = re.compile(r"\b(?:p[.\s-]*h[.\s-]*d\.?|doctoral|doctorate|dphil|studentships?)\b")
_COMPUTATIONAL_PREFERENCE_RE = re.compile(
    r"\b(?:computational|theoretical|simulation|simulations|bioinformatics|cheminformatics)\b"
    r"|\b(?:molecular|atomistic|biophysical) model(?:l?ing|ler|er)\b"
    r"|\b(?:scientific computing|research software|scientific software|quantum chemistry|"
    r"electronic structure|in silico)\b"
)


@dataclass(frozen=True)
class PersonalizedMatch:
    job: dict[str, Any]
    score: int
    reasons: tuple[str, ...]


def _normalize(value: Any) -> str:
    return re.sub(r"[^a-z0-9+#.-]+", " ", str(value or "").casefold()).strip()


def _preferences(value: Any) -> list[str]:
    parts = re.split(r"[,;/\n]|\band\b", str(value or ""), flags=re.IGNORECASE)
    normalized = [_normalize(part) for part in parts]
    return [part for part in normalized if len(part) >= 2]


def _matched_terms(terms: list[str], text: str) -> list[str]:
    return [term for term in terms if term in text]


def _wants_doctoral_training(user: dict[str, Any]) -> bool:
    # A current PhD or a mention in the skills does not request another doctorate.
    roles = unicodedata.normalize("NFKC", str(user.get("target_roles") or "")).casefold()
    roles = re.sub(r"[‐‑‒–—−]", "-", roles)
    roles = re.sub(r"\bpost[\s-]*doctoral\b", "postdoctoral", roles)
    for role in _preferences(roles):
        if not _DOCTORAL_TARGET_RE.search(role):
            continue
        if re.search(r"\b(?:no|not|without|exclude|excluding|except)\b", role):
            continue
        if re.search(r"\b(?:required|holders?|completed)\b", role):
            continue
        return True
    return False


def _wants_computational_work(user: dict[str, Any]) -> bool:
    preferences = _normalize(
        f"{user.get('science_fields') or ''} {user.get('target_roles') or ''}"
    )
    return _COMPUTATIONAL_PREFERENCE_RE.search(preferences) is not None


def score_catalog_job(job: dict[str, Any], user: dict[str, Any]) -> PersonalizedMatch | None:
    # Apply exclusions before scoring, including to rows already in the catalogue.
    if not _wants_doctoral_training(user) and doctoral_training_reason(job):
        return None
    if _wants_computational_work(user) and experimental_role_reason(job):
        return None

    title = _normalize(job.get("title"))
    description = _normalize(job.get("description"))
    location = _normalize(job.get("location"))
    combined = f"{title} {description}"
    score = 0
    relevance_score = 0
    reasons: list[str] = []

    role_matches = _matched_terms(_preferences(user.get("target_roles")), title)
    if role_matches:
        points = min(12, 6 * len(role_matches))
        score += points
        relevance_score += points
        reasons.append("target role: " + ", ".join(role_matches[:2]))

    field_terms = _preferences(user.get("science_fields"))
    field_title = _matched_terms(field_terms, title)
    field_body = [term for term in _matched_terms(field_terms, description) if term not in field_title]
    if field_title:
        points = min(10, 5 * len(field_title))
        score += points
        relevance_score += points
        reasons.append("field in title: " + ", ".join(field_title[:2]))
    elif field_body:
        points = min(6, 2 * len(field_body))
        score += points
        relevance_score += points
        reasons.append("field: " + ", ".join(field_body[:2]))

    skill_matches = _matched_terms(_preferences(user.get("skills")), combined)
    if skill_matches:
        points = min(6, 2 * len(skill_matches))
        score += points
        relevance_score += points
        reasons.append("skills: " + ", ".join(skill_matches[:3]))

    if relevance_score < 4:
        return None

    preferred_locations = _preferences(user.get("preferred_locations"))
    anywhere = {"any", "anywhere", "worldwide", "global"}
    location_matches = [term for term in preferred_locations if term not in anywhere and term in location]
    if location_matches:
        score += 3
        reasons.append("preferred location")

    work_mode = _normalize(user.get("work_mode"))
    remote_signal = "remote" in f"{title} {location} {description}"
    hybrid_signal = "hybrid" in f"{title} {location} {description}"
    if work_mode == "remote":
        score += 2 if remote_signal else -2
        if remote_signal:
            reasons.append("remote")
    elif work_mode == "hybrid" and hybrid_signal:
        score += 2
        reasons.append("hybrid")
    elif work_mode == "on-site" and not remote_signal:
        score += 1

    return PersonalizedMatch(job=job, score=score, reasons=tuple(reasons))


def find_matching_jobs(
    user: dict[str, Any], jobs: list[dict[str, Any]], limit: int = 5
) -> list[PersonalizedMatch]:
    matches = [match for job in jobs if (match := score_catalog_job(job, user))]
    matches.sort(
        key=lambda match: (
            -match.score,
            str(match.job.get("title") or "").casefold(),
            str(match.job.get("company") or "").casefold(),
        )
    )
    return matches[:limit]
