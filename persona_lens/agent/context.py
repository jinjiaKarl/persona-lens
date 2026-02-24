"""Shared agent context: platform-neutral cache passed through all agent turns."""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentContext:
    # [platform][username] -> cached profile data (tweets, patterns, user_info)
    profile_cache: dict[str, dict[str, dict]] = field(default_factory=dict)
    # [platform][username] -> cached analysis result
    analysis_cache: dict[str, dict[str, Any]] = field(default_factory=dict)
    post_count: int = 30
