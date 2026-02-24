"""Platform agent protocol — documents the interface each platform module should expose."""
from typing import Protocol

from agents import Agent


class PlatformAgent(Protocol):
    """Each platform module should expose a specialist agent on this attribute.

    The specialist agent is registered in main_agent.handoffs so the main
    agent can delegate platform-specific analysis to it.
    """
    specialist_agent: Agent
