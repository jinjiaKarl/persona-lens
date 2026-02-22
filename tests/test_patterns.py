from persona_lens.fetchers.patterns import compute_posting_patterns

TWEETS = [
    {"id": "1750000000000000001", "timestamp_ms": 1642723174657, "text": "x", "likes": 5, "retweets": 1, "replies": 0},
    {"id": "1750000000000000002", "timestamp_ms": 1642723174657, "text": "y", "likes": 10, "retweets": 2, "replies": 1},
]

def test_returns_peak_days_and_hours():
    result = compute_posting_patterns(TWEETS)
    assert "peak_days" in result
    assert "peak_hours" in result

def test_peak_days_is_dict_of_str_int():
    result = compute_posting_patterns(TWEETS)
    for k, v in result["peak_days"].items():
        assert isinstance(k, str)
        assert isinstance(v, int)

def test_empty_tweets_returns_empty():
    result = compute_posting_patterns([])
    assert result["peak_days"] == {}
    assert result["peak_hours"] == {}
