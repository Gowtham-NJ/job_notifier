from __future__ import annotations

import argparse
import io
import os
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from pypdf import PdfReader

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
MAX_CV_BYTES = 8 * 1024 * 1024
MAX_CV_PAGES = 30
CV_PREVIEW_CHARS = 2800


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


def extract_pdf_preview(content: bytes) -> str:
    if not content.startswith(b"%PDF-"):
        raise ValueError("The uploaded file is not a valid PDF.")
    reader = PdfReader(io.BytesIO(content))
    if reader.is_encrypted:
        raise ValueError("Password-protected PDFs are not supported.")
    if len(reader.pages) > MAX_CV_PAGES:
        raise ValueError(f"Please upload a CV with no more than {MAX_CV_PAGES} pages.")
    extracted = []
    for page in reader.pages:
        text = " ".join((page.extract_text() or "").split())
        if text:
            extracted.append(text)
        if sum(len(part) for part in extracted) >= CV_PREVIEW_CHARS:
            break
    preview = "\n\n".join(extracted).strip()
    if not preview:
        raise ValueError(
            "I could not extract text from this PDF. It may be a scanned image; please try a text-based PDF."
        )
    return preview[:CV_PREVIEW_CHARS]


def reply_for_pdf_document(update: dict[str, Any], token: str) -> tuple[int, str] | None:
    message = update.get("message") or {}
    document = message.get("document") or {}
    chat_id = message.get("chat", {}).get("id")
    if not document or not isinstance(chat_id, int):
        return None
    filename = str(document.get("file_name") or "")
    mime_type = str(document.get("mime_type") or "")
    size = int(document.get("file_size") or 0)
    if mime_type != "application/pdf" or not filename.casefold().endswith(".pdf"):
        return chat_id, "Please upload your CV as a PDF file."
    if size <= 0 or size > MAX_CV_BYTES:
        return chat_id, "Please upload a PDF smaller than 8 MB."
    try:
        metadata = requests.get(
            f"{TELEGRAM_API_ROOT}/bot{token}/getFile",
            params={"file_id": document["file_id"]},
            timeout=20,
        )
        metadata.raise_for_status()
        file_path = metadata.json()["result"]["file_path"]
        downloaded = requests.get(
            f"{TELEGRAM_API_ROOT}/file/bot{token}/{file_path}", timeout=30
        )
        downloaded.raise_for_status()
        content = downloaded.content
        if len(content) > MAX_CV_BYTES:
            return chat_id, "Please upload a PDF smaller than 8 MB."
        preview = extract_pdf_preview(content)
    except (KeyError, requests.RequestException):
        return chat_id, "I could not download that PDF from Telegram. Please try again."
    except (ValueError, Exception) as exc:
        # PDF parser exceptions are intentionally converted to a user-safe message.
        message = str(exc) if isinstance(exc, ValueError) else "I could not read that PDF. Please try another file."
        return chat_id, message
    return chat_id, (
        "I extracted this text preview from your CV (it was not saved):\n\n"
        f"{preview}\n\n"
        "Phase 3 only checks PDF extraction. Profile suggestions will come in the next phase."
    )


def process_update(update: dict[str, Any], token: str) -> tuple[int, str] | None:
    if (update.get("message") or {}).get("document"):
        return reply_for_pdf_document(update, token)
    return reply_for_update(update)


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

    if text.split()[0].casefold() == "/cv":
        return chat_id, "Upload your CV as a text-based PDF smaller than 8 MB."

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
                reply = process_update(update, token)
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
