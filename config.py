from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """Raised when a JSON configuration file is invalid."""


def load_json(path: str | Path) -> Any:
    file_path = Path(path)
    try:
        with file_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise ConfigError(f"Configuration file not found: {file_path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"Invalid JSON in {file_path} at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc


def validate_profile(profile: dict[str, Any]) -> None:
    required = {
        "minimum_score",
        "high_priority_score",
        "location_mode",
        "title_core_terms",
        "title_role_terms",
        "method_terms",
        "domain_terms",
        "hard_negative_title_terms",
        "preferred_location_terms",
    }
    missing = sorted(required - profile.keys())
    if missing:
        raise ConfigError(f"profile.json is missing required keys: {', '.join(missing)}")

    if profile["location_mode"] not in {"all", "preferred_or_remote"}:
        raise ConfigError("location_mode must be 'all' or 'preferred_or_remote'")

    minimum_score = profile["minimum_score"]
    high_priority_score = profile["high_priority_score"]
    if not isinstance(minimum_score, int) or not isinstance(high_priority_score, int):
        raise ConfigError("minimum_score and high_priority_score must be integers")
    if high_priority_score < minimum_score:
        raise ConfigError("high_priority_score must be >= minimum_score")


def validate_companies(companies: list[dict[str, Any]]) -> None:
    supported = {"greenhouse", "lever", "smartrecruiters", "workday", "rss"}
    if not isinstance(companies, list):
        raise ConfigError("companies.json must contain a JSON list")

    for index, company in enumerate(companies):
        if not isinstance(company, dict):
            raise ConfigError(f"companies.json entry {index} is not an object")
        for key in ("company", "source_type"):
            if not company.get(key):
                raise ConfigError(f"companies.json entry {index} is missing '{key}'")
        if company["source_type"] not in supported:
            raise ConfigError(
                f"Unsupported source_type '{company['source_type']}' for {company['company']}"
            )
        if company["source_type"] == "rss":
            if not company.get("url"):
                raise ConfigError(f"RSS source {company['company']} requires 'url'")
        elif not company.get("token"):
            raise ConfigError(f"Source {company['company']} requires 'token'")
