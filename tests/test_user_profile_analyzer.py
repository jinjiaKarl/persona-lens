import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from persona_lens.analyzers.user_profile_analyzer import analyze_user_profile

TWEETS = [
    {"id": "1", "text": "Cursor is amazing for coding", "likes": 200, "retweets": 30, "replies": 5, "timestamp_ms": 1700000000000},
    {"id": "2", "text": "Claude API is so fast", "likes": 80, "retweets": 10, "replies": 2, "timestamp_ms": 1700000001000},
]

MOCK_PROFILE = {
    "products": [
        {"product": "Cursor", "category": "AI-Coding", "tweet_ids": ["1"]},
        {"product": "Claude API", "category": "AI-Agent", "tweet_ids": ["2"]},
    ],
    "writing_style": "Technical and concise, with a focus on developer tools.",
    "engagement": {
        "top_posts": [{"text": "Cursor is amazing", "likes": 200, "retweets": 30}],
        "insights": "AI coding tools drive the highest engagement.",
    },
}


def _make_mock_runner():
    mock_result = MagicMock()
    mock_result.final_output.model_dump.return_value = MOCK_PROFILE
    return AsyncMock(return_value=mock_result)


def test_returns_products_and_engagement():
    with patch("persona_lens.analyzers.user_profile_analyzer.Runner.run", new=_make_mock_runner()):
        result = asyncio.run(analyze_user_profile("karpathy", TWEETS))
    assert "products" in result
    assert "engagement" in result


def test_products_have_required_fields():
    with patch("persona_lens.analyzers.user_profile_analyzer.Runner.run", new=_make_mock_runner()):
        result = asyncio.run(analyze_user_profile("karpathy", TWEETS))
    assert len(result["products"]) == 2
    assert "product" in result["products"][0]
    assert "category" in result["products"][0]


def test_engagement_has_insights():
    with patch("persona_lens.analyzers.user_profile_analyzer.Runner.run", new=_make_mock_runner()):
        result = asyncio.run(analyze_user_profile("karpathy", TWEETS))
    assert "insights" in result["engagement"]
    assert "top_posts" in result["engagement"]


def test_empty_tweets_returns_defaults():
    result = asyncio.run(analyze_user_profile("karpathy", []))
    assert result["products"] == []
    assert result["engagement"]["insights"] == ""
