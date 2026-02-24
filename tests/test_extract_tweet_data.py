from persona_lens.fetchers.tweet_parser import extract_tweet_data, _parse_stats_from_text

# ── Realistic Nitter snapshot with proper structure ──────────────────────────
# Structure: TOC anchors at top, then content blocks each starting with a bare-link anchor
REALISTIC_SNAPSHOT = """\
- link [e1]:
  - /url: /karpathy/status/1750000000000000001#m
- link [e2]:
  - /url: /karpathy/status/1750000000000000002#m
- list:
  - link "Tweets":
- link [e10]:
  - /url: /karpathy/status/1750000000000000001#m
- link "Andrej Karpathy" [e11]:
  - /url: /karpathy
- link "@karpathy" [e12]:
  - /url: /karpathy
- link "10h" [e13]:
  - /url: /karpathy/status/1750000000000000001#m
- text: "Just shipped a new feature for Cursor!"
- text: "3  12  847"
- link [e20]:
  - /url: /karpathy/status/1750000000000000002#m
- link "Andrej Karpathy" [e21]:
  - /url: /karpathy
- link "@karpathy" [e22]:
  - /url: /karpathy
- link "2h" [e23]:
  - /url: /karpathy/status/1750000000000000002#m
- text: "Trying out Claude 3.5 Sonnet today. Impressive."
- text: "1  5  210"
"""

# ── Simple snapshot (old format, no bare-link anchors) ───────────────────────
SIMPLE_SNAPSHOT = """\
- text: "Just shipped a new feature for Cursor!"
- text: "3  12  847"
- link "status" [e1]:
  - /url: /karpathy/status/1750000000000000001#m
- text: "Trying out Claude 3.5 Sonnet today. Impressive."
- text: "1  5  210"
- link "status" [e2]:
  - /url: /karpathy/status/1750000000000000002#m
"""


# ── _parse_stats_from_text tests ─────────────────────────────────────────────

def test_parse_stats_pure_numbers():
    text, replies, rt, likes, views = _parse_stats_from_text("3  12  847")
    assert text == ""
    assert replies == 3
    assert rt == 12
    assert likes == 847

def test_parse_stats_with_commas():
    text, replies, rt, likes, views = _parse_stats_from_text("1  22  4,418")
    assert text == ""
    assert replies == 1
    assert rt == 22
    assert likes == 4418

def test_parse_stats_mixed_text_and_numbers():
    text, replies, rt, likes, views = _parse_stats_from_text('"Some tweet content  1   22  4,418"')
    assert text == "Some tweet content"
    assert replies == 1
    assert rt == 22
    assert likes == 4418

def test_parse_stats_pure_text():
    text, replies, rt, likes, views = _parse_stats_from_text("Hello world no stats here")
    assert text == "Hello world no stats here"
    assert replies == 0
    assert likes == 0

def test_parse_stats_four_numbers():
    text, replies, rt, likes, views = _parse_stats_from_text("2  5  100  10000")
    assert replies == 2
    assert rt == 5
    assert likes == 100
    assert views == 10000


# ── extract_tweet_data: realistic snapshot ───────────────────────────────────

def test_extract_returns_list_of_tweets():
    tweets = extract_tweet_data(REALISTIC_SNAPSHOT)
    assert len(tweets) == 2

def test_tweet_has_required_fields():
    tweets = extract_tweet_data(REALISTIC_SNAPSHOT)
    t = tweets[0]
    for field in ("id", "text", "timestamp_ms", "likes", "retweets", "replies",
                  "views", "author", "author_name", "media", "time_ago"):
        assert field in t, f"Missing field: {field}"

def test_tweet_text_is_captured():
    tweets = extract_tweet_data(REALISTIC_SNAPSHOT)
    assert "Cursor" in tweets[0]["text"]

def test_tweet_id_decoded_to_timestamp():
    tweets = extract_tweet_data(REALISTIC_SNAPSHOT)
    assert tweets[0]["timestamp_ms"] > 0

def test_author_extraction():
    tweets = extract_tweet_data(REALISTIC_SNAPSHOT)
    assert tweets[0]["author"] == "@karpathy"
    assert tweets[0]["author_name"] == "Andrej Karpathy"

def test_time_ago_extraction():
    tweets = extract_tweet_data(REALISTIC_SNAPSHOT)
    assert tweets[0]["time_ago"] == "10h"
    assert tweets[1]["time_ago"] == "2h"

def test_stats_extraction():
    tweets = extract_tweet_data(REALISTIC_SNAPSHOT)
    t = tweets[0]
    assert t["replies"] == 3
    assert t["retweets"] == 12
    assert t["likes"] == 847


# ── Fallback simple format ───────────────────────────────────────────────────

def test_simple_format_fallback():
    tweets = extract_tweet_data(SIMPLE_SNAPSHOT)
    assert len(tweets) == 2
    assert "Cursor" in tweets[0]["text"]
    assert tweets[0]["likes"] == 847


# ── Deduplication ────────────────────────────────────────────────────────────

def test_dedup_removes_duplicate_tweets():
    """Pinned tweets appearing twice should be deduped."""
    snapshot = """\
- link [e10]:
  - /url: /karpathy/status/1750000000000000001#m
- link "Andrej Karpathy" [e11]:
  - /url: /karpathy
- link "@karpathy" [e12]:
  - /url: /karpathy
- link "10h" [e13]:
  - /url: /karpathy/status/1750000000000000001#m
- text: "Pinned tweet content here"
- text: "3  12  847"
- link [e20]:
  - /url: /karpathy/status/1750000000000000001#m
- link "Andrej Karpathy" [e21]:
  - /url: /karpathy
- link "@karpathy" [e22]:
  - /url: /karpathy
- link "10h" [e23]:
  - /url: /karpathy/status/1750000000000000001#m
- text: "Pinned tweet content here"
- text: "3  12  847"
"""
    tweets = extract_tweet_data(snapshot)
    assert len(tweets) == 1


# ── Label filtering ──────────────────────────────────────────────────────────

def test_label_lines_filtered():
    """'Pinned Tweet' and 'Retweeted' labels should not leak into text."""
    snapshot = """\
- link [e10]:
  - /url: /karpathy/status/1750000000000000001#m
- link "Andrej Karpathy" [e11]:
  - /url: /karpathy
- link "@karpathy" [e12]:
  - /url: /karpathy
- link "5h" [e13]:
  - /url: /karpathy/status/1750000000000000001#m
- text: "Pinned Tweet"
- text: "Actual tweet content about AI"
- text: "3  12  847"
"""
    tweets = extract_tweet_data(snapshot)
    assert len(tweets) == 1
    assert "Pinned Tweet" not in tweets[0]["text"]
    assert "AI" in tweets[0]["text"]


# ── Media extraction ─────────────────────────────────────────────────────────

def test_media_url_extraction():
    snapshot = """\
- link [e10]:
  - /url: /karpathy/status/1750000000000000001#m
- link "Andrej Karpathy" [e11]:
  - /url: /karpathy
- link "@karpathy" [e12]:
  - /url: /karpathy
- link "3h" [e13]:
  - /url: /karpathy/status/1750000000000000001#m
- text: "Check out this image"
- text: "1  5  200"
- link [e14]:
  - /url: /pic/orig/media%2FGabcdef.jpg
"""
    tweets = extract_tweet_data(snapshot)
    assert len(tweets) == 1
    assert len(tweets[0]["media"]) == 1
    assert "pbs.twimg.com/media/Gabcdef.jpg" in tweets[0]["media"][0]


# ── TOC filtering ────────────────────────────────────────────────────────────

def test_toc_anchors_filtered():
    """TOC anchors (packed bare links at top) should not produce ghost tweets."""
    snapshot = """\
- link [e1]:
  - /url: /karpathy/status/1750000000000000001#m
- link [e2]:
  - /url: /karpathy/status/1750000000000000002#m
- list:
  - link "Tweets":
- link [e10]:
  - /url: /karpathy/status/1750000000000000001#m
- link "Andrej Karpathy" [e11]:
  - /url: /karpathy
- link "@karpathy" [e12]:
  - /url: /karpathy
- link "10h" [e13]:
  - /url: /karpathy/status/1750000000000000001#m
- text: "Real tweet content"
- text: "3  12  847"
"""
    tweets = extract_tweet_data(snapshot)
    # Only the real content tweet, not the TOC anchors
    assert len(tweets) == 1
    assert "Real tweet content" in tweets[0]["text"]


# ── Mixed text+stats on same line ────────────────────────────────────────────

def test_mixed_text_stats_line():
    """When stats are appended to text with 2+ spaces, both are extracted."""
    snapshot = """\
- link [e10]:
  - /url: /karpathy/status/1750000000000000001#m
- link "Andrej Karpathy" [e11]:
  - /url: /karpathy
- link "@karpathy" [e12]:
  - /url: /karpathy
- link "5h" [e13]:
  - /url: /karpathy/status/1750000000000000001#m
- text: "Great day for coding  3  12  847"
"""
    tweets = extract_tweet_data(snapshot)
    assert len(tweets) == 1
    assert tweets[0]["text"] == "Great day for coding"
    assert tweets[0]["likes"] == 847
    assert tweets[0]["retweets"] == 12
    assert tweets[0]["replies"] == 3
