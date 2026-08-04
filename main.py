from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from catalog import catalog_science_jobs
from config import ConfigError, load_json, validate_companies, validate_profile
from db import init_db, job_exists, make_dedup_key, save_job
from filters import MatchResult, clean_text, evaluate_job
from notifiers import post_job, post_status, validate_telegram_config, validate_telegram_connection
from sources import fetch_jobs

STATE_PATH = Path("bot_state.json")
LOG_PATH = Path("run_log.txt")


def log(message: str) -> None:
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} | {message}\n")


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"initialized": False}
    try:
        with STATE_PATH.open("r", encoding="utf-8") as handle:
            state = json.load(handle)
        return state if isinstance(state, dict) else {"initialized": False}
    except (OSError, json.JSONDecodeError):
        return {"initialized": False}


def save_state(state: dict[str, Any]) -> None:
    temporary = STATE_PATH.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)
    temporary.replace(STATE_PATH)


def source_key(source: dict[str, Any]) -> str:
    """Stable identifier used to seed newly added sources without notification flooding."""
    source_type = str(source.get("source_type", "")).strip()
    company = str(source.get("company", "")).strip()
    identity = source.get("token") or source.get("url") or company
    return f"{source_type}|{company}|{identity}"


def runtime_fingerprint(job: dict[str, Any]) -> str:
    """Collapse exact duplicate listings whose tracking URLs differ."""
    fields = (
        job.get("company", ""),
        job.get("title", ""),
        job.get("location", ""),
    )
    normalized = [
        re.sub(r"[^a-z0-9]+", " ", clean_text(value).casefold()).strip()
        for value in fields
    ]
    return "|".join(normalized)


def _load_sample(path: str) -> list[dict[str, Any]]:
    data = load_json(path)
    if not isinstance(data, list):
        raise ConfigError("Sample file must contain a JSON list of jobs")
    return data


def _print_match(job: dict[str, Any], match: MatchResult, prefix: str) -> None:
    print(
        f"{prefix:9} score={match.score:>2} priority={match.priority:<8} "
        f"{job.get('company', '')} | {job.get('title', '')} | {job.get('location', '')}"
    )
    for reason in match.reasons[:5]:
        print(f"           - {reason}")


def _seed_jobs(
    evaluated: list[tuple[dict[str, Any], MatchResult, str]],
    allowed_source_keys: set[str] | None = None,
) -> int:
    count = 0
    for job, match, dedup_key in evaluated:
        job_source_key = str(job.get("_source_key", ""))
        if allowed_source_keys is not None and job_source_key not in allowed_source_keys:
            continue
        if not job_exists(dedup_key):
            save_job(job, dedup_key, match.score, match.priority)
            count += 1
    return count


def run(args: argparse.Namespace) -> int:
    catalog_only = getattr(args, "catalog_only", False)
    if catalog_only and (args.dry_run or args.sample):
        raise ConfigError("--catalog-only cannot be combined with --dry-run or --sample")
    profile = load_json(args.profile)
    companies = load_json(args.companies)
    validate_profile(profile)
    validate_companies(companies)

    enabled_sources = [source for source in companies if source.get("enabled", True) is not False]
    if args.validate:
        validate_telegram_config()
        disabled = len(companies) - len(enabled_sources)
        print(
            f"Configuration valid: {len(enabled_sources)} enabled sources, {disabled} disabled, "
            f"profile '{profile.get('profile_name', 'unnamed')}'"
        )
        return 0

    if getattr(args, "check_telegram", False):
        print(validate_telegram_connection())
        return 0

    init_db()
    state = load_state()
    source_errors: list[str] = []
    fetched_jobs: list[dict[str, Any]] = []
    successful_source_keys: set[str] = set()

    if args.sample:
        fetched_jobs = _load_sample(args.sample)
        for job in fetched_jobs:
            job["_source_key"] = "sample"
        print(f"Loaded {len(fetched_jobs)} sample jobs")
    else:
        for source in enabled_sources:
            company = source["company"]
            key = source_key(source)
            try:
                jobs = fetch_jobs(source)
                for job in jobs:
                    job["_source_key"] = key
                fetched_jobs.extend(jobs)
                successful_source_keys.add(key)
                print(f"{company}: fetched {len(jobs)} jobs")
                log(f"FETCH | {company} | count={len(jobs)}")
            except Exception as exc:  # isolate a broken careers site from the full run
                error = f"{company}: {exc}"
                source_errors.append(error)
                print(f"WARNING: {error}", file=sys.stderr)
                log(f"ERROR | {error}")

    persist_catalog = catalog_only or (not args.dry_run and not args.sample)
    catalogued = catalog_science_jobs(fetched_jobs, persist=persist_catalog)
    if persist_catalog:
        print(f"Science catalogue: stored or refreshed {catalogued} jobs")
        log(f"CATALOG | count={catalogued}")
    if catalog_only:
        print("Catalogue-only run complete; no notifications or notifier state changes were made.")
        return 0

    evaluated: list[tuple[dict[str, Any], MatchResult, str]] = []
    runtime_seen: set[str] = set()
    runtime_seen_fingerprints: set[str] = set()
    for job in fetched_jobs:
        match = evaluate_job(job, profile)
        if not match.matched:
            continue
        dedup_key = make_dedup_key(job)
        fingerprint = runtime_fingerprint(job)
        if dedup_key in runtime_seen or fingerprint in runtime_seen_fingerprints:
            continue
        runtime_seen.add(dedup_key)
        runtime_seen_fingerprints.add(fingerprint)
        evaluated.append((job, match, dedup_key))

    evaluated.sort(
        key=lambda item: (
            -item[1].score,
            item[0].get("company", ""),
            item[0].get("title", ""),
        )
    )

    now = dt.datetime.now(dt.timezone.utc).isoformat()
    initial_mode = profile.get("initial_run_mode", "seed")
    first_real_run = not args.dry_run and not args.sample and not state.get("initialized", False)
    legacy_state_upgrade = (
        not args.dry_run
        and not args.sample
        and state.get("initialized", False)
        and "seeded_sources" not in state
    )
    should_seed_first_run = first_real_run and initial_mode == "seed" and not args.post_existing

    if should_seed_first_run or legacy_state_upgrade:
        stored = _seed_jobs(evaluated)
        state.update(
            {
                "initialized": True,
                "initialized_at": state.get("initialized_at", now),
                "last_run_at": now,
                "seeded_sources": sorted(successful_source_keys),
                "state_schema": 2,
            }
        )
        save_state(state)
        if legacy_state_upgrade:
            message = (
                "Notifier state upgraded safely: synchronized current matches and registered "
                f"{len(successful_source_keys)} sources without posting existing jobs."
            )
            log(f"STATE_UPGRADE | stored={stored} | sources={len(successful_source_keys)}")
        else:
            message = (
                f"Job notifier initialized: stored {stored} existing matching jobs "
                "without posting them."
            )
            log(f"SEED | matches={stored} | sources={len(successful_source_keys)}")
        print(message)
        if os.getenv("POST_RUN_SUMMARY", "false").casefold() == "true":
            post_status(message)
        return 0

    # Each newly added source is seeded once. This prevents an established notifier from
    # treating every pre-existing vacancy on a newly configured board as a new alert.
    unseeded_source_keys: set[str] = set()
    newly_seeded_jobs = 0
    if not args.dry_run and not args.sample:
        already_seeded = set(state.get("seeded_sources", []))
        unseeded_source_keys = successful_source_keys - already_seeded
        if unseeded_source_keys:
            newly_seeded_jobs = _seed_jobs(evaluated, unseeded_source_keys)
            state["seeded_sources"] = sorted(already_seeded | unseeded_source_keys)
            print(
                f"Seeded {len(unseeded_source_keys)} newly added source(s): "
                f"stored {newly_seeded_jobs} existing matching jobs without posting."
            )
            log(
                f"SOURCE_SEED | sources={len(unseeded_source_keys)} | "
                f"matches={newly_seeded_jobs}"
            )

    new_matches = [
        item
        for item in evaluated
        if not job_exists(item[2])
        and (args.dry_run or str(item[0].get("_source_key", "")) not in unseeded_source_keys)
    ]
    max_posts = args.max_posts or int(profile.get("max_posts_per_run", 25))
    posted = 0

    for job, match, dedup_key in new_matches[:max_posts]:
        if args.dry_run:
            _print_match(job, match, "DRY-RUN")
            continue

        try:
            post_job(job, match)
            save_job(job, dedup_key, match.score, match.priority)
            posted += 1
            _print_match(job, match, "POSTED")
            log(
                f"POST | score={match.score} | priority={match.priority} | "
                f"{job.get('company')} | {job.get('title')} | {job.get('location')}"
            )
        except Exception as exc:
            print(f"ERROR posting {job.get('title')}: {exc}", file=sys.stderr)
            log(f"POST_ERROR | {job.get('company')} | {job.get('title')} | {exc}")

    if not args.dry_run:
        seeded_sources = set(state.get("seeded_sources", [])) | successful_source_keys
        state.update(
            {
                "initialized": True,
                "initialized_at": state.get("initialized_at", now),
                "last_run_at": now,
                "last_fetched": len(fetched_jobs),
                "last_matched": len(evaluated),
                "last_posted": posted,
                "seeded_sources": sorted(seeded_sources),
                "state_schema": 2,
            }
        )
        save_state(state)

    print("\nRun summary")
    print(f"Fetched:       {len(fetched_jobs)}")
    print(f"Profile match: {len(evaluated)}")
    print(f"New matches:   {len(new_matches)}")
    print(f"Posted:        {posted if not args.dry_run else 0}")
    print(f"Source errors: {len(source_errors)}")
    print(f"Science jobs:  {catalogued}")
    if newly_seeded_jobs:
        print(f"Seeded:        {newly_seeded_jobs}")

    if not args.dry_run and os.getenv("POST_RUN_SUMMARY", "false").casefold() == "true":
        post_status(
            f"Job notifier run complete: {len(fetched_jobs)} fetched, "
            f"{len(evaluated)} matched, {posted} posted, {len(source_errors)} source errors."
        )

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Telegram job notifier tailored to a configurable research profile"
    )
    parser.add_argument("--profile", default="profile.json", help="Path to profile JSON")
    parser.add_argument("--companies", default="companies.json", help="Path to source list JSON")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print matching jobs without Telegram posts or DB changes"
    )
    parser.add_argument("--sample", help="Read jobs from a local JSON file instead of fetching career sites")
    parser.add_argument("--validate", action="store_true", help="Validate configuration and exit")
    parser.add_argument(
        "--check-telegram",
        action="store_true",
        help="Verify the Telegram bot and chat configuration without sending a message",
    )
    parser.add_argument(
        "--post-existing",
        action="store_true",
        help="Post matching jobs on the first real run instead of seeding them",
    )
    parser.add_argument("--max-posts", type=int, help="Override max_posts_per_run")
    parser.add_argument(
        "--catalog-only",
        action="store_true",
        help="Refresh the shared science catalogue without matching, posting, or state changes",
    )
    return parser


if __name__ == "__main__":
    try:
        raise SystemExit(run(build_parser().parse_args()))
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
