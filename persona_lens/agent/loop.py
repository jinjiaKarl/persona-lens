"""Interactive agent loop: conversational KOL analysis powered by OpenAI Agents SDK."""

import asyncio

from agents import Agent, ModelSettings, Runner, WebSearchTool
from agents.extensions.memory import SQLAlchemySession
from openai.types.responses import ResponseTextDeltaEvent
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from rich.console import Console
from sqlalchemy.ext.asyncio import create_async_engine

from persona_lens.agent.context import AgentContext
from persona_lens.agent.skills import use_skill
from persona_lens.platforms.x.agent import x_kol_agent

console = Console()

MAIN_SYSTEM_PROMPT = """You are a helpful assistant.
- For general questions, use web_search to find up-to-date information.
- When the user asks to analyze an X/Twitter account or user, hand off to the KOL Analysis Agent.
- When the user asks for a report, summary, or formatted output, use use_skill to load the appropriate skill instructions.
- Always reply in English."""

main_agent = Agent[AgentContext](
    name="Assistant",
    instructions=MAIN_SYSTEM_PROMPT,
    model="gpt-4o",
    model_settings=ModelSettings(prompt_cache_retention="24h"),
    tools=[WebSearchTool(), use_skill],
    handoffs=[x_kol_agent],  # Add more platform agents here: linkedin_agent, youtube_agent, ...
)


async def _run_loop(post_count: int = 30) -> None:
    ctx = AgentContext(post_count=post_count)

    # In-memory session for testing
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    agent_session = SQLAlchemySession("kol-session", engine=engine, create_tables=True)
    prompt_session = PromptSession()

    console.print("[bold green]KOL Analysis Agent[/] [dim](type 'exit' to quit)[/]\n")

    while True:
        try:
            user_input = await prompt_session.prompt_async(HTML("<ansigreen><b>You</b></ansigreen>: "))
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye![/]")
            break

        user_input = user_input.strip()
        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "q"):
            console.print("[dim]Goodbye![/]")
            break

        result = Runner.run_streamed(
            main_agent,
            input=user_input,
            context=ctx,
            session=agent_session,
        )
        console.print("\n[bold cyan]Agent:[/]", end=" ")

        async for event in result.stream_events():
            if event.type == "raw_response_event":
                if isinstance(event.data, ResponseTextDeltaEvent):
                    print(event.data.delta, end="", flush=True)

        print("\n")


def run_interactive_loop(tweet_count: int = 30) -> None:
    """Start the interactive KOL analysis agent."""
    asyncio.run(_run_loop(tweet_count))
