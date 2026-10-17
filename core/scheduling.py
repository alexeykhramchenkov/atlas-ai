"""Shared due-time policy for registered pipeline stages."""
from datetime import datetime, timedelta, timezone


def is_due(last_success: datetime, frequency_hours: int, now: datetime) -> bool:
    last_success = last_success.replace(tzinfo=last_success.tzinfo or timezone.utc).astimezone(timezone.utc)
    now = now.replace(tzinfo=now.tzinfo or timezone.utc).astimezone(timezone.utc)
    if frequency_hours == 24:
        # Daily cron is tied to a UTC date, not yesterday's completion time.
        return now.date() > last_success.date()
    return now >= last_success + timedelta(hours=frequency_hours)
