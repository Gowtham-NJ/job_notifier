from __future__ import annotations

import argparse
import os
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

from db import (
    confirm_user_profile,
    get_bot_user,
    init_db,
    restart_science_profile,
    save_user_fields,
    save_user_name,
    save_user_skills,
    start_user_onboarding,
)
from notifiers import TELEGRAM_API_ROOT, validate_telegram_config

load_dotenv(Path(__file__).resolve().parent / ".env")

SCIENCE_TERMS = {
    "science", "biology", "biochemistry", "biophysics", "bioinformatics",
    "biotechnology", "chemistry", "immunology", "microbiology", "molecular",
    "neuroscience", "genetics", "genomics", "proteomics", "pharmacology",
    "toxicology", "medicine", "medical", "clinical", "physics", "materials",
    "environmental", "ecology", "earth", "geology", "astronomy", "mathematics",
    "computational", "structural", "cell", "biomedical", "epidemiology",
}


def _looks_scientific(value: str) -> bool:
    normalized = value.casefold()
    return any(term in normalized for term in SCIENCE_TERMS)


def _profile_summary(user: dict[str, Any]) -> str:
    return (
        "Please confirm your science profile:\n\n"
        f"🔬 Fields: {user['science_fields']}\n"
        f"🧰 Skills: {user['skills']}\n\n"
        "Reply yes to save it, or no to enter it again."
    )


def reply_for_update(update: dict[str, Any]) -> tuple[int, str] | None:
    message = update.get("message") or {}
    text = str(message.get("text") or "").strip()
    chat_id = message.get("chat", {}).get("id")
    user_id = message.get("from", {}).get("id")
    if not text or not isinstance(chat_id, int) or not isinstance(user_id, int):
        return None

    user = get_bot_user(user_id)
    if text.split()[0].casefold() == "/start":
        start_user_onboarding(user_id, chat_id)
        if user and user.get("name"):
            if user.get("science_fields") and user.get("skills"):
                return chat_id, f"Welcome back, {user['name']}! 👋 Your science profile is ready."
            return chat_id, (
                f"Welcome back, {user['name']}! 👋\n"
                "Which scientific fields are you interested in? For example: immunology, "
                "molecular biology, or bioinformatics."
            )
        return chat_id, "Hello! 👋 What should I call you?"

    if user and user.get("onboarding_state") == "awaiting_name":
        name = " ".join(text.split())[:80]
        save_user_name(user_id, chat_id, name)
        return chat_id, (
            f"Nice to meet you, {name}! 🎉\n"
            "Which scientific fields are you interested in? For example: immunology, "
            "molecular biology, or bioinformatics."
        )

    if user and user.get("onboarding_state") == "awaiting_fields":
        fields = " ".join(text.split())[:500]
        if not _looks_scientific(fields):
            return chat_id, (
                "This bot is only for science-related jobs. Please enter one or more scientific "
                "fields, such as immunology, chemistry, neuroscience, or bioinformatics."
            )
        save_user_fields(user_id, fields)
        return chat_id, (
            "Great! Now share your scientific skills or techniques. For example: flow cytometry, "
            "Python, RNA sequencing, cell culture, or molecular dynamics."
        )

    if user and user.get("onboarding_state") == "awaiting_skills":
        skills = " ".join(text.split())[:1000]
        if len(skills) < 2:
            return chat_id, "Please enter at least one skill or scientific technique."
        save_user_skills(user_id, skills)
        return chat_id, _profile_summary(get_bot_user(user_id) or {})

    if user and user.get("onboarding_state") == "awaiting_confirmation":
        answer = text.casefold().strip(".! ")
        if answer in {"yes", "y"}:
            confirm_user_profile(user_id)
            return chat_id, "Your science profile is saved! ✅"
        if answer in {"no", "n"}:
            restart_science_profile(user_id)
            return chat_id, "No problem. Which scientific fields are you interested in?"
        return chat_id, "Please reply yes to save the profile or no to enter it again."

    if user and user.get("name"):
        return chat_id, "Your science profile is saved. Send /start to see your greeting."
    return chat_id, "Please send /start so I can introduce myself."


def run_polling(poll_timeout: int = 25) -> None:
    token, _ = validate_telegram_config()
    init_db()
    offset = 0
    print("Interactive bot is running. Press Ctrl+C to stop.")
    while True:
        try:
            response = requests.get(
                f"{TELEGRAM_API_ROOT}/bot{token}/getUpdates",
                params={"offset": offset, "timeout": poll_timeout, "allowed_updates": '["message"]'},
                timeout=poll_timeout + 10,
            )
            response.raise_for_status()
            for update in response.json().get("result", []):
                offset = max(offset, int(update["update_id"]) + 1)
                reply = reply_for_update(update)
                if reply:
                    chat_id, text = reply
                    requests.post(
                        f"{TELEGRAM_API_ROOT}/bot{token}/sendMessage",
                        json={"chat_id": chat_id, "text": text},
                        timeout=20,
                    ).raise_for_status()
        except requests.RequestException as exc:
            print(f"Telegram connection interrupted: {type(exc).__name__}; retrying...")
            time.sleep(5)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the interactive Telegram onboarding bot")
    parser.add_argument("--poll-timeout", type=int, default=25)
    return parser


if __name__ == "__main__":
    try:
        run_polling(build_parser().parse_args().poll_timeout)
    except KeyboardInterrupt:
        print("\nInteractive bot stopped.")
