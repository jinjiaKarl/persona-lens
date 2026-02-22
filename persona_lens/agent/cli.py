from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown

load_dotenv()
app = typer.Typer()
console = Console()


@app.command()
def analyze(
    accounts: Path = typer.Option(..., "--accounts", "-a", help="File with one username per line"),
    tweets: int = typer.Option(30, "--tweets", "-t", help="Tweets to fetch per account"),
    briefs: Optional[Path] = typer.Option(None, "--briefs", "-b", help="File with content briefs (one per line)"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Save report to file"),
):
    usernames = [u.strip().lstrip("@") for u in accounts.read_text().splitlines() if u.strip()]
    brief_list = []
    if briefs:
        brief_list = [b.strip() for b in briefs.read_text().splitlines() if b.strip()]

    console.print(f"[bold green]Analyzing {len(usernames)} accounts...[/]")

    from persona_lens.agent.core import run_agent
    result = run_agent(usernames, brief_list, tweet_count=tweets)

    from persona_lens.agent.formatter import format_agent_report
    md = format_agent_report(result)

    if output:
        output.write_text(md)
        console.print(f"[bold green]Report saved to[/] [cyan]{output}[/]")
    else:
        console.print(Markdown(md))
