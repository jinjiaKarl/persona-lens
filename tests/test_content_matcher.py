from unittest.mock import patch, MagicMock
from persona_lens.analyzers.content_matcher import match_content_briefs

BRIEFS = ["AI产品测评，大众口吻", "技术深度分析，dev口吻"]
PROFILES = {
    "karpathy": {"writing_style": "technical but accessible", "products": ["Cursor", "Claude"]},
    "sama": {"writing_style": "formal, data-driven", "products": ["ChatGPT", "OpenAI API"]},
}

MOCK_RESPONSE = '{"matches": [{"brief": "AI产品测评，大众口吻", "matched_users": ["karpathy"], "reason": "accessible technical style"}, {"brief": "技术深度分析，dev口吻", "matched_users": ["sama"], "reason": "formal data-driven"}]}'

def test_returns_match_per_brief():
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices[0].message.content = MOCK_RESPONSE
    with patch("persona_lens.analyzers.content_matcher.OpenAI", return_value=mock_client):
        result = match_content_briefs(BRIEFS, PROFILES)
    assert len(result) == 2
    assert result[0]["brief"] == "AI产品测评，大众口吻"
    assert "matched_users" in result[0]
    assert "reason" in result[0]
