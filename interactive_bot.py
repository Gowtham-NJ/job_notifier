from __future__ import annotations

import argparse
import os
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

from db import get_bot_user, init_db, save_user_name, start_user_onboarding
from notifiers import TELEGRAM_API_ROOT, validate_telegram_config

load_dotenv(Path(__file__).resolve().parent / ".env")


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
            return chat_id, f"Welcome back, {user['name']}! 👋"
        return chat_id, "Hello! 👋 What should I call you?"

    if user and user.get("onboarding_state") == "awaiting_name":
        name = " ".join(text.split())[:80]
        save_user_name(user_id, chat_id, name)
        return chat_id, f"Nice to meet you, {name}! 🎉"

    if user and user.get("name"):
        return chat_id, "Phase 1 is ready. For now, send /start to see your greeting."
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
