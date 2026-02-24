import re
import urllib.parse
from typing import Any

_TWITTER_EPOCH_MS = 1288834974657

# Private-use unicode icons some Nitter versions prepend to stat numbers
_ICON_CHARS = re.compile(r'[\uf000-\uf8ff\U000f0000-\U000ffffd]')


def _snowflake_to_ms(tweet_id: str) -> int:
    try:
        return (int(tweet_id) >> 22) + _TWITTER_EPOCH_MS
    except (ValueError, OverflowError):
        return 0


def _parse_stats_from_text(raw: str) -> tuple[str, int, int, int, int]:
    """Separate trailing engagement stats from a text line.

    Nitter sometimes appends stats to the end of a text line with 2+ spaces:
        "Some tweet content  1   22  4,418"
    Or a line may be pure stats:
        "1   22  4,418"

    Returns (cleaned_text, replies, retweets, likes, views).
    """
    # Strip surrounding quotes if present
    text = raw.strip().strip('"')

    # Remove private-use icon chars (some Nitter versions)
    text = _ICON_CHARS.sub('', text).strip()

    if not text:
        return ('', 0, 0, 0, 0)

    # Check pure stats line first (all digits, commas, spaces)
    if re.fullmatch(r'[\d,\s]+', text):
        text_part = ''
        nums = [int(n.replace(',', '')) for n in re.findall(r'[\d,]+', text)]
    else:
        # Try to find trailing numbers separated by 2+ spaces
        # Pattern: text_content  num  num  num  [num]
        m = re.match(r'^(.*?)\s{2,}([\d,]+(?:\s{1,}[\d,]+){1,3})\s*$', text)
        if m:
            text_part = m.group(1).strip()
            nums_str = m.group(2)
            nums = [int(n.replace(',', '')) for n in re.findall(r'[\d,]+', nums_str)]
        else:
            return (text, 0, 0, 0, 0)

    replies = retweets = likes = views = 0
    if len(nums) >= 4:
        replies, retweets, likes, views = nums[0], nums[1], nums[2], nums[3]
    elif len(nums) == 3:
        replies, retweets, likes = nums[0], nums[1], nums[2]
    elif len(nums) == 2:
        replies, likes = nums[0], nums[1]
    elif len(nums) == 1:
        likes = nums[0]

    return (text_part, replies, retweets, likes, views)


_SKIP_LABELS = {"pinned tweet", "retweeted", ""}


def extract_user_info(snapshot: str, username: str) -> dict[str, Any]:
    """Parse user profile info from a Nitter snapshot.

    Returns dict with: username, display_name, bio, joined,
    tweets_count, followers, following.
    """
    info: dict[str, Any] = {
        "username": username,
        "display_name": "",
        "bio": "",
        "joined": "",
        "tweets_count": 0,
        "followers": 0,
        "following": 0,
    }

    lines = snapshot.split("\n")
    for line in lines:
        line = line.strip()

        if not info["display_name"]:
            m = re.match(r'^- link "([^@#"][^"]+)"\s*(\[e\d+\])?:?$', line)
            if m:
                name = m.group(1).strip()
                if name.lower() not in ("nitter", "logo") and username.lower() not in name.lower():
                    info["display_name"] = name

        if not info["bio"] and line.startswith("- paragraph:"):
            bio = line.removeprefix("- paragraph:").strip()
            if bio and "Joined" not in bio:
                info["bio"] = bio

        if not info["joined"] and "Joined" in line:
            m = re.search(r"Joined\s+(.+)", line)
            if m:
                info["joined"] = m.group(1).strip()

        if "Tweets " in line:
            m = re.search(r"Tweets\s+([\d,]+)", line)
            if m:
                info["tweets_count"] = int(m.group(1).replace(",", ""))
        if "Followers " in line:
            m = re.search(r"Followers\s+([\d,]+)", line)
            if m:
                info["followers"] = int(m.group(1).replace(",", ""))
        if "Following " in line:
            m = re.search(r"Following\s+([\d,]+)", line)
            if m:
                info["following"] = int(m.group(1).replace(",", ""))

    return info


def extract_tweet_data(snapshot: str) -> list[dict[str, Any]]:
    """Parse raw Nitter accessibility snapshot into structured tweet list.

    Returns list of dicts with: id, text, timestamp_ms, likes, retweets, replies,
    views, author, author_name, media, time_ago.
    """
    lines = snapshot.split("\n")
    n = len(lines)

    # ── Step 1: collect all bare-link tweet anchors ──────────────────────
    # Format: "- link [eN]:" followed by "  - /url: /user/status/DIGITS#m"
    all_anchors: list[tuple[int, str, str]] = []  # (line_index, path, tweet_id)
    for i in range(n - 1):
        line = lines[i].strip()
        if not re.match(r'^- link \[e\d+\]:$', line):
            continue
        url_line = lines[i + 1].strip()
        url_match = re.match(r'^- /url:\s+(/(\w+)/status/(\d+)#m)$', url_line)
        if url_match:
            all_anchors.append((i, url_match.group(1), url_match.group(3)))

    if not all_anchors:
        # Fallback: try the old simple pattern for non-standard snapshots
        return _extract_simple(snapshot)

    # ── Step 2: separate TOC anchors from content anchors ────────────────
    def _is_content_anchor(anchor_idx: int) -> bool:
        i, _, _ = all_anchors[anchor_idx]
        for j in range(i + 2, min(n, i + 8)):
            stripped = lines[j].strip()
            if re.match(r'^- link "[^"]+"\s*(\[e\d+\])?:?$', stripped):
                return True
            if stripped.startswith("- text:"):
                return True
            if re.match(r'^- link \[e\d+\]:$', stripped):
                return False
            if stripped.startswith("- list:"):
                return False
        return False

    content_anchors = [
        a for idx, a in enumerate(all_anchors)
        if _is_content_anchor(idx)
    ]

    if not content_anchors:
        return _extract_simple(snapshot)

    # ── Step 3: parse each content tweet block ───────────────────────────
    tweets: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()  # (author, text[:80]) for dedup

    for idx, (start_i, tweet_path, tweet_id) in enumerate(content_anchors):
        end_i = content_anchors[idx + 1][0] if idx + 1 < len(content_anchors) else n

        author_name = None
        author_handle = None
        time_ago = None
        text_parts: list[str] = []
        stats_set = False
        likes = retweets = replies = views = 0
        media_urls: list[str] = []

        for j in range(start_i, min(end_i, start_i + 60)):
            line = lines[j].strip()

            # Author display name
            if not author_name:
                m = re.match(r'^- link "([^@#][^"]*?)"\s*(\[e\d+\])?:?$', line)
                if m:
                    name = m.group(1).strip()
                    skip = (
                        re.match(r'^\d+[smhd]$', name)
                        or re.match(r'^[A-Z][a-z]{2} \d+', name)
                        or name.lower() in (
                            "nitter", "logo", "more replies",
                            "tweets", "tweets & replies", "media", "search",
                            "pinned tweet", "retweeted",
                        )
                        or name == ""
                    )
                    if not skip:
                        author_name = name

            # Author @handle
            if not author_handle:
                m = re.match(r'^- link "@(\w+)"\s*(\[e\d+\])?:?$', line)
                if m:
                    author_handle = f"@{m.group(1)}"

            # Timestamp (relative like "10h" or absolute like "Mar 15")
            if not time_ago:
                m = re.match(r'^- link "(\d+[smhd])"\s*(\[e\d+\])?:?$', line)
                if m:
                    time_ago = m.group(1)
            if not time_ago:
                m = re.match(r'^- link "([A-Z][a-z]{2} \d+(?:, \d{4})?)"\s*(\[e\d+\])?:?$', line)
                if m:
                    time_ago = m.group(1)

            # Text lines
            if line.startswith("- text:"):
                raw = line[len("- text:"):].strip()
                if not raw:
                    continue
                text_part, rc, rt, lk, vw = _parse_stats_from_text(raw)
                if lk or rc:
                    if not stats_set:
                        likes, retweets, replies, views = lk, rt, rc, vw
                        stats_set = True
                if text_part and text_part.strip().lower() not in _SKIP_LABELS:
                    text_parts.append(text_part.strip())

            # Media URL
            url_match = re.match(r'^- /url:\s+(/pic/orig/(.+))$', line)
            if url_match:
                encoded = url_match.group(2)
                decoded = urllib.parse.unquote(encoded)
                if decoded.startswith("media/"):
                    media_file = decoded[6:]
                    media_url = f"https://pbs.twimg.com/media/{media_file}"
                    if media_url not in media_urls:
                        media_urls.append(media_url)

        tweet_text = " ".join(text_parts).strip() if text_parts else ""

        if not tweet_text and not tweet_id:
            continue

        # Dedup by (author, text[:80])
        dedup_key = (author_handle or "", tweet_text[:80])
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        tweets.append({
            "id": tweet_id,
            "text": tweet_text,
            "timestamp_ms": _snowflake_to_ms(tweet_id),
            "likes": likes,
            "retweets": retweets,
            "replies": replies,
            "views": views,
            "author": author_handle,
            "author_name": author_name,
            "media": media_urls,
            "has_media": len(media_urls) > 0,
            "time_ago": time_ago,
        })

    return tweets


def _extract_simple(snapshot: str) -> list[dict[str, Any]]:
    """Fallback parser for non-standard snapshots (old format compatibility)."""
    tweets: list[dict[str, Any]] = []
    lines = [l.strip() for l in snapshot.splitlines()]
    id_pattern = re.compile(r'/url: /\w+/status/(\d+)#m')
    pending_texts: list[str] = []
    pending_stats: tuple[int, int, int, int] | None = None

    for line in lines:
        id_match = id_pattern.search(line)
        if id_match:
            tweet_id = id_match.group(1)
            likes = retweets = replies = views = 0
            if pending_stats:
                replies, retweets, likes, views = pending_stats

            text = " ".join(pending_texts).strip()
            if text or tweet_id:
                tweets.append({
                    "id": tweet_id,
                    "text": text,
                    "timestamp_ms": _snowflake_to_ms(tweet_id),
                    "likes": likes,
                    "retweets": retweets,
                    "replies": replies,
                    "views": views,
                    "author": None,
                    "author_name": None,
                    "media": [],
                    "time_ago": None,
                })
            pending_texts = []
            pending_stats = None
            continue

        if line.startswith("- text:"):
            raw = line.removeprefix("- text:").strip()
            if not raw:
                continue
            text_part, rc, rt, lk, vw = _parse_stats_from_text(raw)
            if lk or rc:
                pending_stats = (rc, rt, lk, vw)
            if text_part and text_part.strip().lower() not in _SKIP_LABELS:
                pending_texts.append(text_part.strip())

    return tweets
