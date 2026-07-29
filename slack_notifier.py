from __future__ import annotations

import os
import time
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()


def _webhook_for(priority: str) -> str:
    all_webhook = os.getenv("SLACK_WEBHOOK_ALL", "").strip()
    high_webhook = (
        os.getenv("SLACK_WEBHOOK_HIGH", "").strip()
        or os.getenv("SLACK_WEBHOOK_FRESHER", "").strip()  # backwards-compatible alias
    )

    if priority == "high" and high_webhook:
        return high_webhook
    if all_webhook:
        return all_webhook
    raise ValueError("No Slack webhook configured. Set SLACK_WEBHOOK_ALL and optionally SLACK_WEBHOOK_HIGH.")


def build_job_payload(job: dict[str, Any], match: Any) -> dict[str, Any]:
    priority_emoji = ":rotating_light:" if match.priority == "high" else ":microscope:"
    location = job.get("location") or "Location not supplied"
    reasons = "; ".join(match.reasons[:4]) or "Matched configured profile"
    source = job.get("source") or "unknown"
    url = job.get("url") or ""

    return {
        "text": f"{priority_emoji} {job.get('title', 'New job')} at {job.get('company', '')}",
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{priority_emoji} {job.get('title', 'New job')}",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Company*\n{job.get('company', '')}"},
                    {"type": "mrkdwn", "text": f"*Location*\n{location}"},
                    {"type": "mrkdwn", "text": f"*Match score*\n{match.score} ({match.priority})"},
                    {"type": "mrkdwn", "text": f"*Seniority signal*\n{match.seniority}"},
                ],
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Why it matched*\n{reasons}"},
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"Source: {source}"},
                ],
            },
            *(
                [
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "Open job"},
                                "url": url,
                            }
                        ],
                    }
                ]
                if url
                else []
            ),
        ],
    }


def _post(webhook: str, payload: dict[str, Any], retries: int = 3) -> None:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.post(webhook, json=payload, timeout=20)
            if response.status_code == 200:
                return
            if response.status_code not in {429, 500, 502, 503, 504}:
                raise RuntimeError(
                    f"Slack returned HTTP {response.status_code}: {response.text[:300]}"
                )
            last_error = RuntimeError(
                f"Slack transient error HTTP {response.status_code}: {response.text[:300]}"
            )
        except requests.RequestException as exc:
            last_error = exc

        if attempt < retries:
            time.sleep(2 * attempt)

    raise RuntimeError(f"Slack notification failed after {retries} attempts: {last_error}")


def post_job(job: dict[str, Any], match: Any) -> None:
    _post(_webhook_for(match.priority), build_job_payload(job, match))


def post_status(message: str) -> None:
    webhook = os.getenv("SLACK_WEBHOOK_ALL", "").strip()
    if webhook:
        _post(webhook, {"text": message})
