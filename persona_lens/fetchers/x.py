import httpx
import os
import re
import urllib.parse
from collections import Counter
from datetime import datetime, timezone

SESSION_ID = "persona-lens"
_TWITTER_EPOCH_MS = 1288834974657  # Nov 4, 2010
INSTANCES_URL = "https://raw.githubusercontent.com/libredirect/instances/main/data.json"


def _count_tweets(snapshot: str) -> int:
    """Count unique tweet status IDs in the snapshot.

    Matches lines of the form: /url: /username/status/<id>#m
    """
    return len(set(re.findall(r'/url: /\w+/status/(\d+)#m', snapshot)))


_TIME_SLOTS = [
    ("00-04", 0),
    ("04-08", 4),
    ("08-12", 8),
    ("12-16", 12),
    ("16-20", 16),
    ("20-24", 20),
]


def _hour_to_slot(hour: int) -> str:
    for label, start in reversed(_TIME_SLOTS):
        if hour >= start:
            return label
    return "00-04"


def extract_activity(snapshot: str) -> tuple[dict[str, int], dict[str, int]]:
    """Decode Twitter snowflake IDs to get day-of-week and time-slot posting counts (UTC).

    Returns (posting_days, posting_hours).
    """
    tweet_ids = set(re.findall(r'/url: /\w+/status/(\d+)#m', snapshot))
    days: Counter = Counter()
    hours: Counter = Counter()
    for tid in tweet_ids:
        try:
            ts_ms = (int(tid) >> 22) + _TWITTER_EPOCH_MS
            dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
            days[dt.strftime('%A')] += 1
            hours[_hour_to_slot(dt.hour)] += 1
        except (ValueError, OverflowError):
            continue
    return dict(days), dict(hours)


def _extract_cursor(snapshot: str) -> str | None:
    """Extract the next-page cursor from the Nitter snapshot text."""
    cursors = re.findall(r'cursor=([^"&\s]+)', snapshot)
    return cursors[0] if cursors else None


def _resolve_nitter() -> str:
    """Return a reachable Nitter instance.

    Uses NITTER_INSTANCE env var if set. Otherwise tries https://nitter.net
    and falls back to the first reachable clearnet instance from the
    LibreRedirect instance list.
    """
    configured = os.getenv("NITTER_INSTANCE")
    if configured:
        return configured.rstrip("/")

    default = "https://nitter.net"
    try:
        with httpx.Client(timeout=5) as probe:
            probe.get(default)
        return default
    except httpx.HTTPError:
        pass

    # Fetch community instance list and try each clearnet URL
    try:
        with httpx.Client(timeout=10) as probe:
            instances = probe.get(INSTANCES_URL).json()
            for url in instances.get("nitter", {}).get("clearnet", []):
                try:
                    probe.get(url, timeout=5)
                    return url.rstrip("/")
                except httpx.HTTPError:
                    continue
    except httpx.HTTPError:
        pass

    raise RuntimeError(
        "No reachable Nitter instance found. "
        "Set NITTER_INSTANCE in your .env or start a local Nitter instance."
    )


def fetch_snapshot(username: str, tweet_count: int = 20) -> str:
    """Fetch Nitter profile page snapshots via Camofox Browser REST API.

    Returns concatenated accessibility snapshot text from all pages needed
    to accumulate at least `tweet_count` tweets. Uses Nitter cursor-based
    pagination via POST /tabs/:id/navigate instead of clicking UI elements.
    """
    base_url = os.getenv("CAMOFOX_URL", "http://localhost:9377")
    nitter = _resolve_nitter()

    snapshots: list[str] = []
    total_seen = 0

    with httpx.Client(base_url=base_url, timeout=30) as client:
        # 1. Create tab with first page
        tab = client.post("/tabs", json={
            "url": f"{nitter}/{username}",
            "userId": SESSION_ID,
            "sessionKey": username,
        }).json()
        tab_id = tab["tabId"]

        try:
            while True:
                # 2. Wait for Nitter timeline to be present before snapshotting
                client.post(f"/tabs/{tab_id}/wait", json={
                    "userId": SESSION_ID,
                    "selector": ".timeline-item",
                })

                # 3. Get snapshot for current page
                snap = client.get(f"/tabs/{tab_id}/snapshot", params={"userId": SESSION_ID}).json()["snapshot"]
                snapshots.append(snap)
                total_seen += _count_tweets(snap)

                # 4. Stop if we have enough tweets or no cursor for next page
                if total_seen >= tweet_count:
                    break
                cursor = _extract_cursor(snap)
                if not cursor:
                    break

                # 5. Navigate to next page using cursor
                next_url = f"{nitter}/{username}?cursor={urllib.parse.quote(cursor, safe='')}"
                client.post(f"/tabs/{tab_id}/navigate", json={
                    "userId": SESSION_ID,
                    "url": next_url,
                })
        finally:
            # 6. Always clean up tab, even if an error occurs
            client.delete(f"/tabs/{tab_id}")

    return "\n\n--- PAGE BREAK ---\n\n".join(snapshots)
