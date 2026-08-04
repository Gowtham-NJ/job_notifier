from __future__ import annotations

import argparse
import io
import re
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from pypdf import PdfReader

from db import (
    begin_job_preferences,
    confirm_cv_profile,
    confirm_job_preferences,
    confirm_user_profile,
    discard_cv_profile,
    get_bot_user,
    init_db,
    restart_science_profile,
    restart_job_preferences,
    save_preferred_locations,
    save_target_roles,
    save_user_fields,
    save_user_name,
    save_user_skills,
    save_work_mode,
    save_cv_profile_draft,
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
CV_EXTRACTION_CHARS = 20_000

FIELD_PATTERNS = {
    "Immunology": ("immunology", "immune system", "immunological"),
    "Molecular biology": ("molecular biology",),
    "Cell biology": ("cell biology", "cellular biology"),
    "Bioinformatics": ("bioinformatics", "computational genomics"),
    "Computational biology": ("computational biology",),
    "Biochemistry": ("biochemistry", "biochemical"),
    "Microbiology": ("microbiology", "microbial"),
    "Genetics and genomics": ("genetics", "genomics", "genome"),
    "Neuroscience": ("neuroscience", "neurobiology"),
    "Structural biology": ("structural biology",),
    "Biophysics": ("biophysics", "biophysical"),
    "Biotechnology": ("biotechnology", "biotech"),
    "Computational chemistry": ("computational chemistry", "molecular simulation"),
    "Chemistry": ("chemistry", "chemical science"),
    "Materials science": ("materials science", "material science"),
    "Physics": ("physics", "physical science"),
    "Environmental science": ("environmental science", "ecology"),
    "Clinical research": ("clinical research", "clinical trial"),
}

SKILL_PATTERNS = {
    "Flow cytometry": ("flow cytometry", "facs"),
    "Cell culture": ("cell culture", "tissue culture"),
    "PCR": ("pcr", "polymerase chain reaction"),
    "qPCR": ("qpcr", "real-time pcr"),
    "RNA sequencing": ("rna-seq", "rna sequencing", "transcriptomics"),
    "Next-generation sequencing": ("next-generation sequencing", "ngs"),
    "CRISPR": ("crispr",),
    "Western blotting": ("western blot",),
    "ELISA": ("elisa",),
    "Microscopy": ("microscopy", "confocal"),
    "Mass spectrometry": ("mass spectrometry", "proteomics"),
    "Protein purification": ("protein purification", "chromatography"),
    "Molecular cloning": ("molecular cloning", "cloning"),
    "Python": ("python",),
    "R": ("r programming", "r studio", "rstudio"),
    "Linux": ("linux",),
    "Machine learning": ("machine learning", "deep learning"),
    "Data analysis": ("data analysis", "statistical analysis"),
    "Molecular dynamics": ("molecular dynamics", "gromacs", "amber"),
    "DFT": ("density functional theory", "dft"),
    "HPC": ("high-performance computing", "high performance computing", "hpc"),
}

TARGET_ROLE_TERMS = {
    "postdoc", "postdoctoral", "scientist", "researcher", "research fellow",
    "bioinformatician", "biologist", "chemist", "physicist", "engineer",
    "faculty", "professor", "lecturer", "technician", "specialist", "analyst",
    "developer", "programmer", "data science", "laboratory", "lab manager",
    "principal investigator", "phd", "doctoral", "internship",
}

WORK_MODE_ALIASES = {
    "remote": "Remote",
    "on-site": "On-site",
    "onsite": "On-site",
    "on site": "On-site",
    "hybrid": "Hybrid",
    "any": "Any",
    "all": "Any",
    "flexible": "Any",
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


def _preference_summary(user: dict[str, Any]) -> str:
    return (
        "Please confirm your job preferences:\n\n"
        f"💼 Target roles: {user['target_roles']}\n"
        f"🌍 Preferred locations: {user['preferred_locations']}\n"
        f"🏠 Work arrangement: {user['work_mode']}\n\n"
        "Reply yes to save them, or no to enter them again."
    )


def extract_pdf_text(content: bytes) -> str:
    if not content.startswith(b"%PDF-"):
        raise ValueError("The uploaded file is not a valid PDF.")
    reader = PdfReader(io.BytesIO(content))
    if reader.is_encrypted:
        raise ValueError("Password-protected PDFs are not supported.")
    if len(reader.pages) > MAX_CV_PAGES:
        raise ValueError(f"Please upload a CV with no more than {MAX_CV_PAGES} pages.")
    extracted: list[str] = []
    for page in reader.pages:
        text = (page.extract_text() or "").strip()
        if text:
            extracted.append(text)
        if sum(len(part) for part in extracted) >= CV_EXTRACTION_CHARS:
            break
    full_text = "\n\n".join(extracted).strip()
    if not full_text:
        raise ValueError(
            "I could not extract text from this PDF. It may be a scanned image; please try a text-based PDF."
        )
    return full_text[:CV_EXTRACTION_CHARS]


def extract_pdf_preview(content: bytes) -> str:
    return extract_pdf_text(content)[:CV_PREVIEW_CHARS]


def _infer_name(text: str) -> str | None:
    headings = {"curriculum vitae", "cv", "resume", "résumé"}
    for raw_line in text.splitlines()[:20]:
        line = " ".join(raw_line.split()).strip("|•- ")
        words = line.split()
        if (
            line.casefold() in headings
            or not 2 <= len(words) <= 5
            or len(line) > 80
            or "@" in line
            or "http" in line.casefold()
            or any(character.isdigit() for character in line)
        ):
            continue
        if all(re.fullmatch(r"[^\W\d_]+(?:[-'][^\W\d_]+)?", word, re.UNICODE) for word in words):
            return line.title() if line.isupper() else line
    return None


def infer_cv_profile(text: str) -> dict[str, str | None]:
    normalized = " ".join(text.casefold().split())
    fields = [
        label for label, patterns in FIELD_PATTERNS.items()
        if any(pattern in normalized for pattern in patterns)
    ]
    skills = [
        label for label, patterns in SKILL_PATTERNS.items()
        if any(pattern in normalized for pattern in patterns)
    ]
    career_signals = (
        ("Postdoctoral", ("postdoctoral", "postdoc")),
        ("PhD", ("ph.d", "phd", "doctoral candidate", "doctoral researcher")),
        ("Research scientist", ("research scientist",)),
        ("Master's", ("master of science", "msc", "m.sc")),
        ("Bachelor's", ("bachelor of science", "bsc", "b.sc")),
    )
    career_stage = next(
        (label for label, patterns in career_signals if any(pattern in normalized for pattern in patterns)),
        "Not confidently detected",
    )
    return {
        "name": _infer_name(text),
        "fields": ", ".join(fields) or None,
        "skills": ", ".join(skills) or None,
        "career_stage": career_stage,
    }


def reply_for_pdf_document(update: dict[str, Any], token: str) -> tuple[int, str] | None:
    message = update.get("message") or {}
    document = message.get("document") or {}
    chat_id = message.get("chat", {}).get("id")
    user_id = message.get("from", {}).get("id")
    if not document or not isinstance(chat_id, int) or not isinstance(user_id, int):
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
        text = extract_pdf_text(content)
    except (KeyError, requests.RequestException):
        return chat_id, "I could not download that PDF from Telegram. Please try again."
    except ValueError as exc:
        # PDF parser exceptions are intentionally converted to a user-safe message.
        return chat_id, str(exc)
    except Exception:
        return chat_id, "I could not read that PDF. Please try another file."
    draft = infer_cv_profile(text)
    if not draft["fields"] or not draft["skills"]:
        existing_user = get_bot_user(user_id)
        if existing_user and existing_user.get("name"):
            restart_science_profile(user_id)
            next_question = "Which scientific fields are you interested in?"
        else:
            start_user_onboarding(user_id, chat_id)
            next_question = "What should I call you?"
        return chat_id, (
            "I extracted the CV text, but could not confidently identify both scientific fields "
            f"and skills. Nothing was saved. Please enter your profile manually. {next_question}"
        )
    save_cv_profile_draft(
        user_id,
        chat_id,
        draft["name"],
        draft["fields"],
        draft["skills"],
        str(draft["career_stage"]),
    )
    return chat_id, (
        "I inferred this draft from your CV (the PDF and raw text were not saved):\n\n"
        f"👤 Name: {draft['name'] or 'Not confidently detected'}\n"
        f"🔬 Fields: {draft['fields']}\n"
        f"🧰 Skills: {draft['skills']}\n"
        f"🎓 Current/recent career stage: {draft['career_stage']}\n\n"
        "Reply yes to save this draft, or no to enter your details manually."
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

    if text.split()[0].casefold() == "/preferences":
        if begin_job_preferences(user_id):
            return chat_id, (
                "What science-related roles are you looking for? For example: postdoc, "
                "research scientist, bioinformatician, or laboratory scientist."
            )
        return chat_id, "Please create your science profile first with /start or /cv."

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
            return chat_id, (
                "Your science profile is saved! ✅\n"
                "What science-related roles are you looking for?"
            )
        if answer in {"no", "n"}:
            restart_science_profile(user_id)
            return chat_id, "No problem. Which scientific fields are you interested in?"
        return chat_id, "Please reply yes to save the profile or no to enter it again."

    if user and user.get("onboarding_state") == "awaiting_cv_confirmation":
        answer = text.casefold().strip(".! ")
        if answer in {"yes", "y"}:
            confirm_cv_profile(user_id)
            return chat_id, (
                "Your CV-derived science profile is saved! ✅\n"
                "What science-related roles are you looking for?"
            )
        if answer in {"no", "n"}:
            next_state = discard_cv_profile(user_id)
            if next_state == "awaiting_name":
                return chat_id, "No problem. What should I call you?"
            return chat_id, "No problem. Which scientific fields are you interested in?"
        return chat_id, "Please reply yes to save the CV draft or no to enter it manually."

    if user and user.get("onboarding_state") == "awaiting_target_roles":
        roles = " ".join(text.split())[:500]
        normalized = roles.casefold()
        if not any(term in normalized for term in TARGET_ROLE_TERMS):
            return chat_id, (
                "Please enter one or more science-related roles, such as postdoc, research "
                "scientist, bioinformatician, laboratory scientist, or research software engineer."
            )
        save_target_roles(user_id, roles)
        return chat_id, (
            "Which countries, cities, or regions do you prefer? You can also answer "
            "worldwide or anywhere."
        )

    if user and user.get("onboarding_state") == "awaiting_locations":
        locations = " ".join(text.split())[:500]
        if len(locations) < 2:
            return chat_id, "Please enter at least one location, or answer worldwide."
        save_preferred_locations(user_id, locations)
        return chat_id, "Which work arrangement do you prefer: remote, on-site, hybrid, or any?"

    if user and user.get("onboarding_state") == "awaiting_work_mode":
        work_mode = WORK_MODE_ALIASES.get(text.casefold().strip(".! "))
        if not work_mode:
            return chat_id, "Please answer remote, on-site, hybrid, or any."
        save_work_mode(user_id, work_mode)
        return chat_id, _preference_summary(get_bot_user(user_id) or {})

    if user and user.get("onboarding_state") == "awaiting_preference_confirmation":
        answer = text.casefold().strip(".! ")
        if answer in {"yes", "y"}:
            confirm_job_preferences(user_id)
            return chat_id, "Your job preferences are saved! ✅"
        if answer in {"no", "n"}:
            restart_job_preferences(user_id)
            return chat_id, "No problem. What science-related roles are you looking for?"
        return chat_id, "Please reply yes to save the preferences or no to enter them again."

    if user and user.get("name"):
        return chat_id, (
            "Your science profile is saved. Send /preferences to set job preferences "
            "or /start to see your greeting."
        )
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
