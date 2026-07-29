from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any

from config import ConfigError, load_json, validate_companies, validate_profile
from db import init_db, job_exists, make_dedup_key, save_job
from filters import MatchResult, evaluate_job
from slack_notifier import post_job, post_status
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


def run(args: argparse.Namespace) -> int:
    profile = load_json(args.profile)
    companies = load_json(args.companies)
    validate_profile(profile)
    validate_companies(companies)

    if args.validate:
        print(f"Configuration valid: {len(companies)} sources, profile '{profile.get('profile_name', 'unnamed')}'")
        return 0

    init_db()
    state = load_state()
    source_errors: list[str] = []
    fetched_jobs: list[dict[str, Any]] = []

    if args.sample:
        fetched_jobs = _load_sample(args.sample)
        print(f"Loaded {len(fetched_jobs)} sample jobs")
    else:
        for source in companies:
            if source.get("enabled", True) is False:
                continue
            company = source["company"]
            try:
                jobs = fetch_jobs(source)
                fetched_jobs.extend(jobs)
                print(f"{company}: fetched {len(jobs)} jobs")
                log(f"FETCH | {company} | count={len(jobs)}")
            except Exception as exc:  # isolate a broken careers site from the full run
                error = f"{company}: {exc}"
                source_errors.append(error)
                print(f"WARNING: {error}", file=sys.stderr)
                log(f"ERROR | {error}")

    evaluated: list[tuple[dict[str, Any], MatchResult, str]] = []
    runtime_seen: set[str] = set()
    for job in fetched_jobs:
        match = evaluate_job(job, profile)
        if not match.matched:
            continue
        dedup_key = make_dedup_key(job)
        if dedup_key in runtime_seen:
            continue
        runtime_seen.add(dedup_key)
        evaluated.append((job, match, dedup_key))

    evaluated.sort(key=lambda item: (-item[1].score, item[0].get("company", ""), item[0].get("title", "")))

    initial_mode = profile.get("initial_run_mode", "seed")
    first_real_run = not args.dry_run and not state.get("initialized", False)
    should_seed = first_real_run and initial_mode == "seed" and not args.post_existing

    if should_seed:
        for job, match, dedup_key in evaluated:
            save_job(job, dedup_key, match.score, match.priority)
        state.update(
            {
                "initialized": True,
                "initialized_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "last_run_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
        )
        save_state(state)
        message = f"Job notifier initialized: stored {len(evaluated)} existing matching jobs without posting them."
        print(message)
        log(f"SEED | matches={len(evaluated)}")
        if os.getenv("POST_RUN_SUMMARY", "false").casefold() == "true":
            post_status(message)
        return 0

    new_matches = [item for item in evaluated if not job_exists(item[2])]
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
        state.update(
            {
                "initialized": True,
                "last_run_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "last_fetched": len(fetched_jobs),
                "last_matched": len(evaluated),
                "last_posted": posted,
            }
        )
        save_state(state)

    print("\nRun summary")
    print(f"Fetched:       {len(fetched_jobs)}")
    print(f"Profile match: {len(evaluated)}")
    print(f"New matches:   {len(new_matches)}")
    print(f"Posted:        {posted if not args.dry_run else 0}")
    print(f"Source errors: {len(source_errors)}")

    if not args.dry_run and os.getenv("POST_RUN_SUMMARY", "false").casefold() == "true":
        post_status(
            f"Job notifier run complete: {len(fetched_jobs)} fetched, "
            f"{len(evaluated)} matched, {posted} posted, {len(source_errors)} source errors."
        )

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Slack job notifier tailored to a configurable research profile")
    parser.add_argument("--profile", default="profile.json", help="Path to profile JSON")
    parser.add_argument("--companies", default="companies.json", help="Path to source list JSON")
    parser.add_argument("--dry-run", action="store_true", help="Print matching jobs without Slack posts or DB changes")
    parser.add_argument("--sample", help="Read jobs from a local JSON file instead of fetching career sites")
    parser.add_argument("--validate", action="store_true", help="Validate configuration and exit")
    parser.add_argument("--post-existing", action="store_true", help="Post matching jobs on the first real run instead of seeding them")
    parser.add_argument("--max-posts", type=int, help="Override max_posts_per_run")
    return parser


if __name__ == "__main__":
    try:
        raise SystemExit(run(build_parser().parse_args()))
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
