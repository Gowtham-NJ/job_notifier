from __future__ import annotations

import html
import os
import time
from pathlib import Path
from typing import Any, Callable

import requests
from dotenv import load_dotenv

# Use an explicit path so python-dotenv also behaves predictably in tests and stdin scripts.
load_dotenv(Path(__file__).resolve().parent / ".env")

TRANSIENT_STATUS = {429, 500, 502, 503, 504}


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None, retries: int = 3) -> None:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=20)
            if 200 <= response.status_code < 300:
                return
            detail = response.text[:300]
            if response.status_code not in TRANSIENT_STATUS:
                raise RuntimeError(f"HTTP {response.status_code}: {detail}")
            last_error = RuntimeError(f"transient HTTP {response.status_code}: {detail}")
        except requests.RequestException as exc:
            last_error = exc
        if attempt < retries:
            time.sleep(2 * attempt)
    raise RuntimeError(f"notification failed after {retries} attempts: {last_error}")


def _post_form(url: str, payload: dict[str, Any], retries: int = 3) -> None:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.post(url, data=payload, timeout=20)
            if 200 <= response.status_code < 300:
                return
            detail = response.text[:300]
            if response.status_code not in TRANSIENT_STATUS:
                raise RuntimeError(f"HTTP {response.status_code}: {detail}")
            last_error = RuntimeError(f"transient HTTP {response.status_code}: {detail}")
        except requests.RequestException as exc:
            last_error = exc
        if attempt < retries:
            time.sleep(2 * attempt)
    raise RuntimeError(f"notification failed after {retries} attempts: {last_error}")


def _value(name: str) -> str:
    return os.getenv(name, "").strip()


def _priority_url(prefix: str, priority: str) -> str:
    high = _value(f"{prefix}_HIGH")
    general = _value(f"{prefix}_ALL")
    return high if priority == "high" and high else general


def _plain_job(job: dict[str, Any], match: Any) -> str:
    reasons = "; ".join(match.reasons[:4]) or "Matched configured profile"
    lines = [
        f"{'🚨' if match.priority == 'high' else '🔬'} {job.get('title', 'New job')}",
        f"Company: {job.get('company', '')}",
        f"Location: {job.get('location') or 'Not supplied'}",
        f"Match: {match.score} ({match.priority})",
        f"Why: {reasons}",
        f"Source: {job.get('source') or 'unknown'}",
    ]
    if job.get("url"):
        lines.append(f"Open: {job['url']}")
    return "\n".join(lines)


def _slack_payload(job: dict[str, Any], match: Any) -> dict[str, Any]:
    emoji = ":rotating_light:" if match.priority == "high" else ":microscope:"
    reasons = "; ".join(match.reasons[:4]) or "Matched configured profile"
    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{emoji} {job.get('title', 'New job')}", "emoji": True},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Company*\n{job.get('company', '')}"},
                {"type": "mrkdwn", "text": f"*Location*\n{job.get('location') or 'Not supplied'}"},
                {"type": "mrkdwn", "text": f"*Match score*\n{match.score} ({match.priority})"},
                {"type": "mrkdwn", "text": f"*Seniority signal*\n{match.seniority}"},
            ],
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Why it matched*\n{reasons}"}},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": f"Source: {job.get('source') or 'unknown'}"}]},
    ]
    if job.get("url"):
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Open job"},
                        "url": job["url"],
                    }
                ],
            }
        )
    return {"text": f"{emoji} {job.get('title', 'New job')} at {job.get('company', '')}", "blocks": blocks}


def _discord_payload(job: dict[str, Any], match: Any) -> dict[str, Any]:
    reasons = "; ".join(match.reasons[:4]) or "Matched configured profile"
    return {
        "embeds": [
            {
                "title": f"{'🚨' if match.priority == 'high' else '🔬'} {job.get('title', 'New job')}",
                "url": job.get("url") or None,
                "description": reasons[:4000],
                "fields": [
                    {"name": "Company", "value": str(job.get("company") or "Not supplied"), "inline": True},
                    {"name": "Location", "value": str(job.get("location") or "Not supplied"), "inline": True},
                    {"name": "Match", "value": f"{match.score} ({match.priority})", "inline": True},
                    {"name": "Source", "value": str(job.get("source") or "unknown"), "inline": True},
                ],
            }
        ]
    }


def _telegram_text(job: dict[str, Any], match: Any) -> str:
    reasons = html.escape("; ".join(match.reasons[:4]) or "Matched configured profile")
    title = html.escape(str(job.get("title") or "New job"))
    company = html.escape(str(job.get("company") or "Not supplied"))
    location = html.escape(str(job.get("location") or "Not supplied"))
    source = html.escape(str(job.get("source") or "unknown"))
    lines = [
        f"{'🚨' if match.priority == 'high' else '🔬'} <b>{title}</b>",
        f"<b>Company:</b> {company}",
        f"<b>Location:</b> {location}",
        f"<b>Match:</b> {match.score} ({html.escape(match.priority)})",
        f"<b>Why:</b> {reasons}",
        f"<b>Source:</b> {source}",
    ]
    url = str(job.get("url") or "")
    if url:
        lines.append(f'<a href="{html.escape(url, quote=True)}">Open job</a>')
    return "\n".join(lines)


def _send_slack(job: dict[str, Any], match: Any) -> bool:
    url = _priority_url("SLACK_WEBHOOK", match.priority)
    if not url:
        return False
    _post_json(url, _slack_payload(job, match))
    return True


def _send_discord(job: dict[str, Any], match: Any) -> bool:
    url = _priority_url("DISCORD_WEBHOOK", match.priority)
    if not url:
        return False
    _post_json(url, _discord_payload(job, match))
    return True


def _send_telegram(job: dict[str, Any], match: Any) -> bool:
    token = _value("TELEGRAM_BOT_TOKEN")
    chat_id = _value("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    _post_json(
        f"https://api.telegram.org/bot{token}/sendMessage",
        {
            "chat_id": chat_id,
            "text": _telegram_text(job, match),
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        },
    )
    return True


def _send_ntfy(job: dict[str, Any], match: Any) -> bool:
    topic_url = _value("NTFY_TOPIC_URL")
    if not topic_url:
        return False
    headers = {
        "Title": f"{job.get('title', 'New job')} — {job.get('company', '')}"[:250],
        "Priority": "high" if match.priority == "high" else "default",
        "Tags": "rotating_light,briefcase" if match.priority == "high" else "microscope,briefcase",
    }
    if job.get("url"):
        headers["Click"] = str(job["url"])
    token = _value("NTFY_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = requests.post(topic_url, data=_plain_job(job, match).encode("utf-8"), headers=headers, timeout=20)
    if not 200 <= response.status_code < 300:
        raise RuntimeError(f"ntfy returned HTTP {response.status_code}: {response.text[:300]}")
    return True


def _send_pushover(job: dict[str, Any], match: Any) -> bool:
    token = _value("PUSHOVER_APP_TOKEN")
    user = _value("PUSHOVER_USER_KEY")
    if not token or not user:
        return False
    payload: dict[str, Any] = {
        "token": token,
        "user": user,
        "title": f"{job.get('title', 'New job')} — {job.get('company', '')}"[:250],
        "message": _plain_job(job, match)[:1024],
        "priority": 1 if match.priority == "high" else 0,
    }
    if job.get("url"):
        payload["url"] = job["url"]
        payload["url_title"] = "Open job"
    _post_form("https://api.pushover.net/1/messages.json", payload)
    return True


def _deliver(senders: list[tuple[str, Callable[[], bool]]]) -> None:
    configured = 0
    successful = 0
    failures: list[str] = []
    for name, sender in senders:
        try:
            was_configured = sender()
            if was_configured:
                configured += 1
                successful += 1
        except Exception as exc:  # one broken channel must not suppress all others
            configured += 1
            failures.append(f"{name}: {exc}")
    if configured == 0:
        raise ValueError(
            "No notification channel configured. Set Slack, Discord, Telegram, ntfy, or Pushover secrets."
        )
    if successful == 0:
        raise RuntimeError("All configured notification channels failed: " + " | ".join(failures))
    if failures:
        print("WARNING: some notification channels failed: " + " | ".join(failures))


def post_job(job: dict[str, Any], match: Any) -> None:
    _deliver(
        [
            ("Slack", lambda: _send_slack(job, match)),
            ("Discord", lambda: _send_discord(job, match)),
            ("Telegram", lambda: _send_telegram(job, match)),
            ("ntfy", lambda: _send_ntfy(job, match)),
            ("Pushover", lambda: _send_pushover(job, match)),
        ]
    )


def post_status(message: str) -> None:
    # Status summaries are intentionally simple and sent only to general channels.
    senders: list[tuple[str, Callable[[], bool]]] = []
    slack = _value("SLACK_WEBHOOK_ALL")
    if slack:
        senders.append(("Slack", lambda: (_post_json(slack, {"text": message}) or True)))
    discord = _value("DISCORD_WEBHOOK_ALL")
    if discord:
        senders.append(("Discord", lambda: (_post_json(discord, {"content": message}) or True)))
    token, chat_id = _value("TELEGRAM_BOT_TOKEN"), _value("TELEGRAM_CHAT_ID")
    if token and chat_id:
        senders.append(
            (
                "Telegram",
                lambda: (
                    _post_json(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        {"chat_id": chat_id, "text": message},
                    )
                    or True
                ),
            )
        )
    topic = _value("NTFY_TOPIC_URL")
    if topic:
        def send_ntfy_status() -> bool:
            response = requests.post(topic, data=message.encode("utf-8"), timeout=20)
            response.raise_for_status()
            return True
        senders.append(("ntfy", send_ntfy_status))
    push_token, push_user = _value("PUSHOVER_APP_TOKEN"), _value("PUSHOVER_USER_KEY")
    if push_token and push_user:
        senders.append(
            (
                "Pushover",
                lambda: (
                    _post_form(
                        "https://api.pushover.net/1/messages.json",
                        {"token": push_token, "user": push_user, "message": message[:1024]},
                    )
                    or True
                ),
            )
        )
    if senders:
        _deliver(senders)
