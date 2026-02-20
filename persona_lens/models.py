from pydantic import BaseModel


class PersonaReport(BaseModel):
    display_name: str
    username: str
    bio: str
    personality_traits: list[str]
    communication_style: str
    writing_style: str
    interests: list[str]
    expertise: list[str]
    values: list[str]
    summary: str
    posting_days: dict[str, int] = {}   # day-of-week counts, locally computed
    posting_hours: dict[str, int] = {}  # time-slot counts (UTC), locally computed
    activity_insights: str = ""         # OpenAI-generated from activity data
