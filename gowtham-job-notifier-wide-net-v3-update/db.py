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
