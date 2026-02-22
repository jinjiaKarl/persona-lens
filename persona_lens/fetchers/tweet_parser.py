import re
from typing import Any

_TWITTER_EPOCH_MS = 1288834974657


def _snowflake_to_ms(tweet_id: str) -> int:
    try:
        return (int(tweet_id) >> 22) + _TWITTER_EPOCH_MS
    except (ValueError, OverflowError):
        return 0


def extract_tweet_data(snapshot: str) -> list[dict[str, Any]]:
    """Parse raw Nitter accessibility snapshot into structured tweet list.

    Must be called on the raw snapshot, before clean_snapshot().
    Each returned dict has: id, text, timestamp_ms, likes, retweets, replies.

    Nitter snapshot structure (per tweet):
      - text: "<tweet content>"
      - text: "<replies>  <retweets>  <likes>"   <- pure-digit line
      - /url: /username/status/<id>#m
    """
    tweets: list[dict[str, Any]] = []
    lines = [l.strip() for l in snapshot.splitlines()]
    id_pattern = re.compile(r'/url: /\w+/status/(\d+)#m')
    pending_texts: list[str] = []
    pending_stats: str | None = None

    for line in lines:
        id_match = id_pattern.search(line)
        if id_match:
            tweet_id = id_match.group(1)
            likes = retweets = replies = 0
            if pending_stats:
                nums = re.findall(r'[\d,]+', pending_stats)
                nums_int = [int(n.replace(',', '')) for n in nums]
                if len(nums_int) >= 3:
                    replies, retweets, likes = nums_int[0], nums_int[1], nums_int[2]
                elif len(nums_int) == 2:
                    retweets, likes = nums_int[0], nums_int[1]
                elif len(nums_int) == 1:
                    likes = nums_int[0]

            text = " ".join(pending_texts).strip()
            if text or tweet_id:
                tweets.append({
                    "id": tweet_id,
                    "text": text,
                    "timestamp_ms": _snowflake_to_ms(tweet_id),
                    "likes": likes,
                    "retweets": retweets,
                    "replies": replies,
                })
            pending_texts = []
            pending_stats = None
            continue

        if line.startswith("- text:"):
            content = line.removeprefix("- text:").strip().strip('"')
            if re.fullmatch(r'[\d,\s]+', content):
                pending_stats = content
            else:
                pending_texts.append(content)

    return tweets
