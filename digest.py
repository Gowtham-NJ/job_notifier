from __future__ import annotations

import argparse
import datetime as dt
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from db import (
    delivered_job_keys,
    init_db,
    list_catalog_jobs,
    list_digest_users,
    record_digest_run,
)
from matching import PersonalizedMatch, find_matching_jobs
from notifiers import TELEGRAM_API_ROOT, _post_json, validate_telegram_config


def local_schedule_status(user: dict[str, Any], now_utc: dt.datetime) -> tuple[bool, str]:
    try:
        timezone = ZoneInfo(str(user["digest_timezone"]))
        hour, minute = (int(part) for part in str(user["digest_time"]).split(":", 1))
        local_now = now_utc.astimezone(timezone)
        scheduled = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    except (KeyError, TypeError, ValueError, ZoneInfoNotFoundError):
        return False, ""
    local_date = local_now.date().isoformat()
    already_ran = user.get("digest_last_run_local_date") == local_date
    return local_now >= scheduled and not already_ran, local_date


def _vacancy_fingerprint(match: PersonalizedMatch) -> str:
    job = match.job
    value = "|".join(
        str(job.get(field) or "") for field in ("company", "title", "location")
    ).casefold()
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def select_new_matches(
    matches: list[PersonalizedMatch], delivered: set[str], limit: int = 5
) -> tuple[list[PersonalizedMatch], list[str]]:
    groups: dict[str, list[PersonalizedMatch]] = {}
    for match in matches:
        groups.setdefault(_vacancy_fingerprint(match), []).append(match)
    selected: list[PersonalizedMatch] = []
    delivery_keys: list[str] = []
    for group in groups.values():
        keys = [str(match.job.get("dedup_key") or "") for match in group]
        if any(key in delivered for key in keys):
            continue
        selected.append(group[0])
        delivery_keys.extend(key for key in keys if key)
        if len(selected) >= limit:
            break
    return selected, delivery_keys


def format_digest(user: dict[str, Any], matches: list[PersonalizedMatch], test: bool = False) -> str:
    heading = "TEST DIGEST" if test else "Your daily science job digest"
    sections = [f"🔬 {heading}, {str(user.get('name') or 'there')[:80]}!"]
    for index, match in enumerate(matches, start=1):
        job = match.job
        lines = [
            f"{index}. {str(job.get('title') or 'Untitled role')[:180]}",
            f"{str(job.get('company') or 'Unknown organization')[:120]} · "
            f"{str(job.get('location') or 'Location not supplied')[:140]}",
            "Why: " + ("; ".join(match.reasons[:3]) or "science profile match"),
        ]
        if job.get("url"):
            lines.append(str(job["url"])[:500])
        sections.append("\n".join(lines))
    return "\n\n".join(sections)[:4000]


def run_digest(
    *,
    send: bool = False,
    test_user_id: int | None = None,
    now_utc: dt.datetime | None = None,
) -> dict[str, int]:
    init_db()
    now = now_utc or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)
    users = list_digest_users(test_user_id)
    jobs = list_catalog_jobs()
    token = validate_telegram_config()[0] if send else ""
    stats = {"considered": len(users), "due": 0, "sent": 0, "matches": 0}

    for user in users:
        is_test = test_user_id is not None
        due, local_date = local_schedule_status(user, now)
        if not is_test and not due:
            continue
        stats["due"] += 1
        all_matches = find_matching_jobs(user, jobs, limit=len(jobs))
        delivered = set() if is_test else delivered_job_keys(int(user["telegram_user_id"]))
        matches, delivery_keys = select_new_matches(all_matches, delivered, limit=5)
        stats["matches"] += len(matches)
        if not matches:
            if not is_test and send:
                record_digest_run(int(user["telegram_user_id"]), [], local_date)
            print(f"User {user['telegram_user_id']}: no new matches")
            continue

        message = format_digest(user, matches, test=is_test)
        if not send:
            print(f"DRY-RUN user={user['telegram_user_id']} matches={len(matches)}\n{message}\n")
            continue

        _post_json(
            f"{TELEGRAM_API_ROOT}/bot{token}/sendMessage",
            {"chat_id": user["chat_id"], "text": message},
        )
        stats["sent"] += 1
        if not is_test:
            record_digest_run(int(user["telegram_user_id"]), delivery_keys, local_date)
    return stats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run personalized Telegram job digests")
    parser.add_argument("--send", action="store_true", help="Actually send messages; default is dry-run")
    parser.add_argument(
        "--test-user",
        type=int,
        help="Preview or explicitly send one immediate test digest without recording delivery",
    )
    return parser


if __name__ == "__main__":
    arguments = build_parser().parse_args()
    results = run_digest(send=arguments.send, test_user_id=arguments.test_user)
    mode = "SEND" if arguments.send else "DRY-RUN"
    print(f"{mode} summary: {results}")
