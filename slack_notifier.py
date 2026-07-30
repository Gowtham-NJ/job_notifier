"""Backward-compatible import wrapper.

The notifier now supports Slack, Discord, Telegram, ntfy, and Pushover through
``notifiers.py``. Existing imports continue to work.
"""

from notifiers import post_job, post_status

__all__ = ["post_job", "post_status"]
