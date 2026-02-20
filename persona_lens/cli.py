import typer
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.markdown import Markdown
from dotenv import load_dotenv

load_dotenv()
app = typer.Typer()
console = Console()


@app.command()
def analyze(
    username: str = typer.Argument(help="X username, with or without @"),
    tweets: int = typer.Option(20, "--tweets", "-t", help="Number of tweets to fetch"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Save report to file instead of printing"),
):
    username = username.lstrip("@")

    with console.status("[bold green]Fetching profile from Nitter..."):
        from persona_lens.fetchers.x import fetch_snapshot, extract_activity
        snapshot = fetch_snapshot(username, tweet_count=tweets)
        posting_days, posting_hours = extract_activity(snapshot)

    with console.status("[bold green]Analyzing persona with OpenAI..."):
        from persona_lens.analyzers.openai_analyzer import analyze as run_analysis
        report = run_analysis(snapshot, posting_days, posting_hours)

    from persona_lens.formatters.markdown import format_report
    md = format_report(report)

    if output:
        output.write_text(md)
        console.print(f"[bold green]✓[/] Report saved to [cyan]{output}[/]")
    else:
        console.print(Markdown(md))
