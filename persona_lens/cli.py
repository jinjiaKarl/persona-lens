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
    analyze: bool = typer.Option(True, "--analyze/--no-analyze", help="Run OpenAI persona analysis"),
    debug: bool = typer.Option(False, "--debug", help="Print data sent to LLM before analyzing"),
    mode: str = typer.Option("cursor", "--mode", "-m", help="Pagination mode: 'cursor' (default) or 'click'"),
):
    if mode not in ("cursor", "click"):
        console.print(f"[bold red]Error:[/] --mode must be 'cursor' or 'click', got '{mode}'")
        raise typer.Exit(1)

    username = username.lstrip("@")

    with console.status("[bold green]Fetching profile from Nitter..."):
        from persona_lens.fetchers.x import fetch_snapshot, extract_activity, _count_tweets, clean_snapshot
        snapshot = fetch_snapshot(username, tweet_count=tweets, mode=mode)
        posting_days, posting_hours = extract_activity(snapshot)
        cleaned = clean_snapshot(snapshot)

    tweet_count = _count_tweets(snapshot)
    console.print(f"[dim]Scraped {tweet_count} tweets · {len(cleaned)} chars after cleaning (raw: {len(snapshot)})[/]")

    if not analyze:
        console.print(cleaned)
        return

    if debug:
        console.rule("[bold yellow]LLM Input")
        console.print(f"[dim]posting_days:[/] {posting_days}")
        console.print(f"[dim]posting_hours:[/] {posting_hours}")
        console.rule("[bold yellow]cleaned snapshot")
        console.print(cleaned)
        console.rule()

    with console.status("[bold green]Analyzing persona with OpenAI..."):
        from persona_lens.analyzers.openai_analyzer import analyze as run_analysis
        report = run_analysis(cleaned, posting_days, posting_hours)

    from persona_lens.formatters.markdown import format_report
    md = format_report(report)

    if output:
        output.write_text(md)
        console.print(f"[bold green]✓[/] Report saved to [cyan]{output}[/]")
    else:
        console.print(Markdown(md))
