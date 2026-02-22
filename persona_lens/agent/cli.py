import typer
from dotenv import load_dotenv

load_dotenv()
app = typer.Typer()


@app.command()
def chat(
    tweets: int = typer.Option(30, "--tweets", "-t", help="Default tweets to fetch per account"),
):
    """Start an interactive KOL analysis agent."""
    from persona_lens.agent.loop import run_interactive_loop
    run_interactive_loop(tweet_count=tweets)
