from __future__ import annotations

import argparse
import os
import threading
import time
from collections.abc import Callable

from digest import run_digest
from interactive_bot import run_polling
from main import build_parser as build_collector_parser
from main import run as run_collector


def positive_seconds(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a whole number of seconds") from exc
    if value < 1:
        raise ValueError(f"{name} must be at least 1 second")
    return value


def refresh_catalog() -> None:
    arguments = build_collector_parser().parse_args(["--catalog-only"])
    exit_code = run_collector(arguments)
    if exit_code:
        raise RuntimeError(f"Catalogue refresh exited with status {exit_code}")


def repeat_task(
    name: str,
    task: Callable[[], object],
    interval_seconds: int,
    *,
    run_immediately: bool = True,
    stop_event: threading.Event | None = None,
) -> None:
    stop = stop_event or threading.Event()
    if not run_immediately and stop.wait(interval_seconds):
        return
    while not stop.is_set():
        started = time.monotonic()
        try:
            task()
        except Exception as exc:
            print(f"{name} failed: {type(exc).__name__}: {exc}", flush=True)
        elapsed = time.monotonic() - started
        if stop.wait(max(1, interval_seconds - elapsed)):
            return


def run_service(poll_timeout: int = 25) -> None:
    catalog_interval = positive_seconds("CATALOG_INTERVAL_SECONDS", 3 * 60 * 60)
    digest_interval = positive_seconds("DIGEST_CHECK_INTERVAL_SECONDS", 60)
    print(
        "Persistent bot service starting: Telegram polling, catalogue refresh every "
        f"{catalog_interval}s, digest checks every {digest_interval}s.",
        flush=True,
    )
    workers = [
        threading.Thread(
            target=repeat_task,
            args=("Catalogue refresh", refresh_catalog, catalog_interval),
            daemon=True,
            name="catalog-refresh",
        ),
        threading.Thread(
            target=repeat_task,
            args=("Digest check", lambda: run_digest(send=True), digest_interval),
            daemon=True,
            name="digest-check",
        ),
    ]
    for worker in workers:
        worker.start()
    run_polling(poll_timeout)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the persistent Telegram bot service")
    parser.add_argument("--poll-timeout", type=int, default=25)
    return parser


if __name__ == "__main__":
    try:
        run_service(build_parser().parse_args().poll_timeout)
    except (KeyboardInterrupt, ValueError) as exc:
        if str(exc):
            print(f"Service stopped: {exc}")
        else:
            print("\nService stopped.")
