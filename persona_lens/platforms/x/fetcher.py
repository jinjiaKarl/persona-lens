import httpx
import os
import re
import urllib.parse

SESSION_ID = "persona-lens"
INSTANCES_URL = "https://raw.githubusercontent.com/libredirect/instances/main/data.json"


def _count_tweets(snapshot: str) -> int:
    """Count unique tweet status IDs in the snapshot.

    Matches lines of the form: /url: /username/status/<id>#m
    """
    return len(set(re.findall(r'/url: /\w+/status/(\d+)#m', snapshot)))



def _extract_cursor(snapshot: str) -> str | None:
    """Extract the next-page cursor from the Nitter snapshot text."""
    cursors = re.findall(r'cursor=([^"&\s]+)', snapshot)
    return cursors[0] if cursors else None


def _extract_load_more_ref(snapshot: str) -> str | None:
    """Extract the element ref of the 'Load more' link from the Nitter snapshot.

    Snapshot format: - link "Load more" [e175]:
    """
    match = re.search(r'link "Load more" \[(e\d+)\]', snapshot)
    return match.group(1) if match else None


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


def fetch_snapshot(username: str, tweet_count: int = 20, mode: str = "cursor") -> str:
    """Fetch Nitter profile page snapshots via Camofox Browser REST API.

    Returns concatenated accessibility snapshot text from all pages needed
    to accumulate at least `tweet_count` tweets.

    mode="cursor" (default): navigates to next page via URL cursor parameter.
    mode="click": clicks the 'Load more' button in the page DOM.
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

                # 4. Stop if we have enough tweets
                if total_seen >= tweet_count:
                    break

                # 5. Advance to next page
                if mode == "click":
                    ref = _extract_load_more_ref(snap)
                    if not ref:
                        break
                    client.post(f"/tabs/{tab_id}/click", json={
                        "userId": SESSION_ID,
                        "ref": ref,
                    })
                    # Wait for the Load more button to reappear — this signals
                    # new tweets have finished loading. If it never appears the
                    # wait times out and the next snapshot will have no ref → stop.
                    client.post(f"/tabs/{tab_id}/wait", json={
                        "userId": SESSION_ID,
                        "selector": 'a[href*="cursor="]',
                    })
                else:  # cursor (default)
                    cursor = _extract_cursor(snap)
                    if not cursor:
                        break
                    next_url = f"{nitter}/{username}?cursor={urllib.parse.quote(cursor, safe='')}"
                    client.post(f"/tabs/{tab_id}/navigate", json={
                        "userId": SESSION_ID,
                        "url": next_url,
                    })
        finally:
            # 6. Always clean up tab, even if an error occurs
            client.delete(f"/tabs/{tab_id}")

    return "\n\n--- PAGE BREAK ---\n\n".join(snapshots)
