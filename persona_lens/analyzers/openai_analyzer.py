import json
import os

from openai import OpenAI

from persona_lens.models import PersonaReport

SYSTEM_PROMPT = """
You are an expert persona analyst. You receive an accessibility snapshot of a
person's Nitter (Twitter mirror) profile page, plus their day-of-week posting
distribution.

Extract and return a JSON object with these fields:
- display_name: their real/display name
- username: their @handle (without @)
- bio: their profile bio verbatim; if no bio is present in the snapshot, generate a concise 1-2 sentence bio based on their posts and areas of expertise
- personality_traits: list of 3-6 personality traits inferred from writing style and content
- communication_style: 1-2 sentence description of how they communicate (tone, formality)
- writing_style: 1-2 sentence description of their writing style (vocabulary, sentence structure, use of humor/sarcasm/emojis, etc.)
- interests: list of topics they frequently discuss
- expertise: list of domains they demonstrate knowledge in
- values: list of core values evident in their posts
- summary: a 2-3 sentence overall persona summary
- activity_insights: 2-3 sentence psychological insight into what the posting schedule reveals about this person (e.g. work habits, lifestyle, motivation patterns, whether they post more on weekdays vs weekends and what that suggests)

Base your analysis on patterns across posts, not single tweets.
Return only valid JSON, no markdown formatting.
"""


def analyze(snapshot: str, posting_days: dict[str, int], posting_hours: dict[str, int]) -> PersonaReport:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    day_summary  = ", ".join(f"{d}: {c}" for d, c in sorted(posting_days.items()))  or "no data"
    hour_summary = ", ".join(f"{s}: {c}" for s, c in sorted(posting_hours.items())) or "no data"
    user_content = (
        f"Posting activity by day of week: {day_summary}\n"
        f"Posting activity by time of day (UTC): {hour_summary}\n\n"
        f"{snapshot}"
    )

    response = client.chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
    )
    data = json.loads(response.choices[0].message.content)
    data["posting_days"] = posting_days
    data["posting_hours"] = posting_hours
    return PersonaReport.model_validate(data)
