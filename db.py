from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path("jobs.db")


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    connection = connect()
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dedup_key TEXT NOT NULL UNIQUE,
                company TEXT NOT NULL,
                title TEXT NOT NULL,
                location TEXT,
                url TEXT,
                source TEXT,
                score INTEGER,
                priority TEXT,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_first_seen ON jobs(first_seen)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_users (
                telegram_user_id INTEGER PRIMARY KEY,
                chat_id INTEGER NOT NULL,
                name TEXT,
                onboarding_state TEXT NOT NULL DEFAULT 'awaiting_name',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        existing_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(bot_users)").fetchall()
        }
        for column in (
            "science_fields",
            "skills",
            "career_stage",
            "cv_draft_name",
            "cv_draft_fields",
            "cv_draft_skills",
            "cv_draft_career_stage",
        ):
            if column not in existing_columns:
                connection.execute(f"ALTER TABLE bot_users ADD COLUMN {column} TEXT")
        connection.commit()
    finally:
        connection.close()


def make_dedup_key(job: dict[str, Any]) -> str:
    url = str(job.get("url") or "").strip().casefold().rstrip("/")
    if url:
        basis = url
    else:
        basis = "|".join(
            str(job.get(key) or "").strip().casefold()
            for key in ("company", "title", "location")
        )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def job_exists(dedup_key: str) -> bool:
    connection = connect()
    try:
        row = connection.execute(
            "SELECT 1 FROM jobs WHERE dedup_key = ? LIMIT 1", (dedup_key,)
        ).fetchone()
        return row is not None
    finally:
        connection.close()


def save_job(job: dict[str, Any], dedup_key: str, score: int, priority: str) -> None:
    connection = connect()
    try:
        connection.execute(
            """
            INSERT OR IGNORE INTO jobs
                (dedup_key, company, title, location, url, source, score, priority)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dedup_key,
                job.get("company", ""),
                job.get("title", ""),
                job.get("location", ""),
                job.get("url", ""),
                job.get("source", ""),
                score,
                priority,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def start_user_onboarding(telegram_user_id: int, chat_id: int) -> None:
    connection = connect()
    try:
        connection.execute(
            """
            INSERT INTO bot_users (telegram_user_id, chat_id, onboarding_state)
            VALUES (?, ?, 'awaiting_name')
            ON CONFLICT(telegram_user_id) DO UPDATE SET
                chat_id = excluded.chat_id,
                onboarding_state = CASE
                    WHEN bot_users.name IS NULL THEN 'awaiting_name'
                    WHEN bot_users.science_fields IS NULL THEN 'awaiting_fields'
                    ELSE bot_users.onboarding_state
                END,
                updated_at = CURRENT_TIMESTAMP
            """,
            (telegram_user_id, chat_id),
        )
        connection.commit()
    finally:
        connection.close()


def save_user_name(telegram_user_id: int, chat_id: int, name: str) -> None:
    connection = connect()
    try:
        connection.execute(
            """
            INSERT INTO bot_users (telegram_user_id, chat_id, name, onboarding_state)
            VALUES (?, ?, ?, 'awaiting_fields')
            ON CONFLICT(telegram_user_id) DO UPDATE SET
                chat_id = excluded.chat_id,
                name = excluded.name,
                onboarding_state = 'awaiting_fields',
                updated_at = CURRENT_TIMESTAMP
            """,
            (telegram_user_id, chat_id, name),
        )
        connection.commit()
    finally:
        connection.close()


def save_user_fields(telegram_user_id: int, fields: str) -> None:
    connection = connect()
    try:
        connection.execute(
            """
            UPDATE bot_users
            SET science_fields = ?, onboarding_state = 'awaiting_skills',
                updated_at = CURRENT_TIMESTAMP
            WHERE telegram_user_id = ?
            """,
            (fields, telegram_user_id),
        )
        connection.commit()
    finally:
        connection.close()


def save_user_skills(telegram_user_id: int, skills: str) -> None:
    connection = connect()
    try:
        connection.execute(
            """
            UPDATE bot_users
            SET skills = ?, onboarding_state = 'awaiting_confirmation',
                updated_at = CURRENT_TIMESTAMP
            WHERE telegram_user_id = ?
            """,
            (skills, telegram_user_id),
        )
        connection.commit()
    finally:
        connection.close()


def confirm_user_profile(telegram_user_id: int) -> None:
    connection = connect()
    try:
        connection.execute(
            """
            UPDATE bot_users SET onboarding_state = 'complete', updated_at = CURRENT_TIMESTAMP
            WHERE telegram_user_id = ?
            """,
            (telegram_user_id,),
        )
        connection.commit()
    finally:
        connection.close()


def restart_science_profile(telegram_user_id: int) -> None:
    connection = connect()
    try:
        connection.execute(
            """
            UPDATE bot_users
            SET science_fields = NULL, skills = NULL, onboarding_state = 'awaiting_fields',
                updated_at = CURRENT_TIMESTAMP
            WHERE telegram_user_id = ?
            """,
            (telegram_user_id,),
        )
        connection.commit()
    finally:
        connection.close()


def save_cv_profile_draft(
    telegram_user_id: int,
    chat_id: int,
    name: str | None,
    fields: str,
    skills: str,
    career_stage: str,
) -> None:
    connection = connect()
    try:
        connection.execute(
            """
            INSERT INTO bot_users (
                telegram_user_id, chat_id, onboarding_state, cv_draft_name,
                cv_draft_fields, cv_draft_skills, cv_draft_career_stage
            ) VALUES (?, ?, 'awaiting_cv_confirmation', ?, ?, ?, ?)
            ON CONFLICT(telegram_user_id) DO UPDATE SET
                chat_id = excluded.chat_id,
                onboarding_state = 'awaiting_cv_confirmation',
                cv_draft_name = excluded.cv_draft_name,
                cv_draft_fields = excluded.cv_draft_fields,
                cv_draft_skills = excluded.cv_draft_skills,
                cv_draft_career_stage = excluded.cv_draft_career_stage,
                updated_at = CURRENT_TIMESTAMP
            """,
            (telegram_user_id, chat_id, name, fields, skills, career_stage),
        )
        connection.commit()
    finally:
        connection.close()


def confirm_cv_profile(telegram_user_id: int) -> None:
    connection = connect()
    try:
        connection.execute(
            """
            UPDATE bot_users SET
                name = COALESCE(cv_draft_name, name),
                science_fields = cv_draft_fields,
                skills = cv_draft_skills,
                career_stage = cv_draft_career_stage,
                cv_draft_name = NULL,
                cv_draft_fields = NULL,
                cv_draft_skills = NULL,
                cv_draft_career_stage = NULL,
                onboarding_state = 'complete',
                updated_at = CURRENT_TIMESTAMP
            WHERE telegram_user_id = ?
            """,
            (telegram_user_id,),
        )
        connection.commit()
    finally:
        connection.close()


def discard_cv_profile(telegram_user_id: int) -> str:
    connection = connect()
    try:
        row = connection.execute(
            "SELECT name FROM bot_users WHERE telegram_user_id = ?", (telegram_user_id,)
        ).fetchone()
        next_state = "awaiting_fields" if row and row["name"] else "awaiting_name"
        connection.execute(
            """
            UPDATE bot_users SET
                cv_draft_name = NULL,
                cv_draft_fields = NULL,
                cv_draft_skills = NULL,
                cv_draft_career_stage = NULL,
                onboarding_state = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE telegram_user_id = ?
            """,
            (next_state, telegram_user_id),
        )
        connection.commit()
        return next_state
    finally:
        connection.close()


def get_bot_user(telegram_user_id: int) -> dict[str, Any] | None:
    connection = connect()
    try:
        row = connection.execute(
            "SELECT * FROM bot_users WHERE telegram_user_id = ?", (telegram_user_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        connection.close()
