import typer
from dotenv import load_dotenv

load_dotenv()
app = typer.Typer(invoke_without_command=True)


@app.callback()
def main(
    tweets: int = typer.Option(30, "--tweets", "-t", help="Default tweets to fetch per account"),
):
    """Interactive KOL analysis agent for X/Twitter profiles."""
    from persona_lens.agent.loop import run_interactive_loop
    run_interactive_loop(tweet_count=tweets)
