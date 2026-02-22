from unittest.mock import patch, MagicMock
from persona_lens.analyzers.product_analyzer import analyze_products

TWEETS = [
    {"id": "1", "text": "Cursor is amazing for coding", "likes": 100, "retweets": 10, "replies": 5, "timestamp_ms": 1700000000000},
    {"id": "2", "text": "Claude API is fast", "likes": 50, "retweets": 5, "replies": 2, "timestamp_ms": 1700000001000},
]

MOCK_RESPONSE = '{"products": [{"product": "Cursor", "category": "AI工具-编程", "tweet_ids": ["1"]}, {"product": "Claude API", "category": "AI工具-Agent", "tweet_ids": ["2"]}]}'

def test_analyze_products_returns_list():
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices[0].message.content = MOCK_RESPONSE
    with patch("persona_lens.analyzers.product_analyzer.OpenAI", return_value=mock_client):
        result = analyze_products("karpathy", TWEETS)
    assert isinstance(result, list)
    assert len(result) == 2

def test_product_has_required_fields():
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices[0].message.content = MOCK_RESPONSE
    with patch("persona_lens.analyzers.product_analyzer.OpenAI", return_value=mock_client):
        result = analyze_products("karpathy", TWEETS)
    assert "product" in result[0]
    assert "category" in result[0]
    assert "tweet_ids" in result[0]
