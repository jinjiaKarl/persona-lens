from collections import Counter
from datetime import datetime, timezone
from typing import Any

_TIME_SLOTS = [
    ("00-04", 0), ("04-08", 4), ("08-12", 8),
    ("12-16", 12), ("16-20", 16), ("20-24", 20),
]


def _hour_to_slot(hour: int) -> str:
    for label, start in reversed(_TIME_SLOTS):
        if hour >= start:
            return label
    return "00-04"


def compute_posting_patterns(tweets: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute peak posting days and time slots from structured tweet list."""
    days: Counter = Counter()
    hours: Counter = Counter()
    for t in tweets:
        ts_ms = t.get("timestamp_ms", 0)
        if not ts_ms:
            continue
        dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
        days[dt.strftime("%A")] += 1
        hours[_hour_to_slot(dt.hour)] += 1
    return {"peak_days": dict(days), "peak_hours": dict(hours)}
