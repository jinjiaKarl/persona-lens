from persona_lens.fetchers.tweet_parser import extract_tweet_data

SAMPLE_SNAPSHOT = """
- text: "Just shipped a new feature for Cursor!"
- text: "3  12  847"
- link "status" [e1]:
  - /url: /karpathy/status/1750000000000000001#m
- text: "Trying out Claude 3.5 Sonnet today. Impressive."
- text: "1  5  210"
- link "status" [e2]:
  - /url: /karpathy/status/1750000000000000002#m
"""

def test_extract_returns_list_of_tweets():
    tweets = extract_tweet_data(SAMPLE_SNAPSHOT)
    assert len(tweets) == 2

def test_tweet_has_required_fields():
    tweets = extract_tweet_data(SAMPLE_SNAPSHOT)
    t = tweets[0]
    assert "id" in t
    assert "text" in t
    assert "timestamp_ms" in t

def test_tweet_text_is_captured():
    tweets = extract_tweet_data(SAMPLE_SNAPSHOT)
    assert "Cursor" in tweets[0]["text"]

def test_tweet_id_decoded_to_timestamp():
    tweets = extract_tweet_data(SAMPLE_SNAPSHOT)
    assert tweets[0]["timestamp_ms"] > 0
