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
    token_sources = {"greenhouse", "lever", "smartrecruiters", "workday"}
    url_sources = {
        "rss",
        "scholarshipdb",
        "findapostdoc",
        "researchjobs_cz",
        "ccl",
        "charmm_gui",
        "euraxess",
        "academictransfer",
        "jobs_ac_uk",
        "jobbnorge",
        "arbeitnow",
        "molssi",
        "cecam",
        "academicjobsonline",
        "iscb",
        "society_rse",
        "max_planck",
        "leibniz",
        "inria",
        "tyc",
        "helmholtz_ai",
        "embl_partners",
        "restricted",
    }
    supported = token_sources | url_sources

    if not isinstance(companies, list):
        raise ConfigError("companies.json must contain a JSON list")

    for index, source in enumerate(companies):
        if not isinstance(source, dict):
            raise ConfigError(f"companies.json entry {index} is not an object")
        for key in ("company", "source_type"):
            if not source.get(key):
                raise ConfigError(f"companies.json entry {index} is missing '{key}'")

        source_type = source["source_type"]
        company = source["company"]
        if source_type not in supported:
            raise ConfigError(f"Unsupported source_type '{source_type}' for {company}")

        if source_type in token_sources and not source.get("token"):
            raise ConfigError(f"Source {company} requires 'token'")
        if source_type in url_sources and not source.get("url"):
            raise ConfigError(f"Source {company} requires 'url'")

        if source_type == "restricted" and source.get("enabled", True) is not False:
            raise ConfigError(
                f"Restricted source {company} must remain disabled; set \"enabled\": false"
            )

        if "max_detail_pages" in source:
            value = source["max_detail_pages"]
            if not isinstance(value, int) or value < 1 or value > 200:
                raise ConfigError(
                    f"Source {company} max_detail_pages must be an integer from 1 to 200"
                )
