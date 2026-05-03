"""Business-day calendar utilities."""
from __future__ import annotations

from datetime import date, timedelta


def business_days(start: date, end: date) -> list[date]:
    """Inclusive business-day range. No holiday calendar -- weekends only."""
    days: list[date] = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            days.append(cur)
        cur += timedelta(days=1)
    return days
