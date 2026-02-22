from unittest.mock import patch, MagicMock
from persona_lens.analyzers.engagement_analyzer import find_engagement_patterns

ALL_USER_DATA = {
    "karpathy": {
        "tweets": [
            {"id": "1", "text": "Cursor rocks", "likes": 500, "retweets": 100, "replies": 20, "timestamp_ms": 1700000000000},
            {"id": "2", "text": "hello world", "likes": 5, "retweets": 1, "replies": 0, "timestamp_ms": 1700000001000},
        ],
        "products": [{"product": "Cursor", "category": "AI工具-编程", "tweet_ids": ["1"]}],
        "patterns": {"peak_days": {"Thursday": 2}, "peak_hours": {"12-16": 2}},
    }
}

MOCK_RESPONSE = '{"result": {"insights": "High engagement on AI coding tools", "patterns": [{"type": "product_type", "description": "AI编程工具互动最高"}]}}'

def test_returns_insights_and_patterns():
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices[0].message.content = MOCK_RESPONSE
    with patch("persona_lens.analyzers.engagement_analyzer.OpenAI", return_value=mock_client):
        result = find_engagement_patterns(ALL_USER_DATA)
    assert "insights" in result
    assert "patterns" in result
