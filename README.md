# persona-lens

Interactive AI agent for analyzing X (Twitter) KOL (Key Opinion Leader) profiles through conversation.

## How it works

1. You start a chat session and ask the agent to analyze any X/Twitter account
2. The agent fetches tweets via Nitter using [Camofox Browser](https://github.com/jo-inc/camofox-browser) (anti-detection Firefox automation)
3. Tweets are parsed into structured data — text, engagement stats, media, timestamps (decoded from Twitter snowflake IDs)
4. A profile analyzer (GPT-4o) extracts products mentioned, writing style, and engagement insights
5. You can ask follow-up questions, compare accounts, or request new analyses — all in one session

## Requirements

- Python 3.13+
- Node.js (for Camofox Browser)
- `uv` package manager
- OpenAI API key

## Setup

### 1. Start Camofox Browser

```bash
git clone https://github.com/jo-inc/camofox-browser
cd camofox-browser
npm install
npm start
```

The service starts on port 9377 and downloads Camoufox (~300MB) on first run.

Or use Docker:

```bash
docker build -t camofox-browser .
docker run -p 9377:9377 camofox-browser
```

### 2. Install persona-lens

```bash
uv sync
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env and set your OPENAI_API_KEY
```

## Usage

```bash
# Start the interactive agent
uv run persona-lens

# Fetch more tweets per account (default: 30)
uv run persona-lens --tweets 50
```

### Example session

```
KOL Analysis Agent (type 'exit' to quit)

You: Analyze @karpathy and @sama
  → Fetching @karpathy...
  → Analyzing @karpathy...
  → Fetching @sama...
  → Analyzing @sama...

Agent: Here's what I found...

You: Which one mentions more AI coding tools?
Agent: (answers from cached data — no re-fetching)

You: Now analyze @yaborosk
  → Fetching @yaborosk...
  → Analyzing @yaborosk...

Agent: ...
```

### What the agent extracts per account

- **Profile info** — bio, followers, following, tweet count
- **Products mentioned** — with AI-inferred categories
- **Writing style** — tone, vocabulary, format preferences
- **Engagement insights** — top posts and what drives engagement
- **Posting patterns** — peak days and hours (UTC)

## Architecture

```
agent/cli.py          — Typer CLI entry point
agent/loop.py         — Interactive agent loop (OpenAI Agents SDK)
  ├─ fetch_user       — tool: fetch snapshot → parse tweets → compute patterns
  └─ analyze_user     — tool: run profile analyzer sub-agent
fetchers/x.py         — Camofox Browser REST API → Nitter page
fetchers/tweet_parser.py  — snapshot → structured tweets + user info
fetchers/patterns.py      — tweet timestamps → posting patterns
analyzers/user_profile_analyzer.py  — GPT-4o sub-agent → products, style, engagement
```

## Limitations

**Tweet cap:** Nitter uses Twitter's unauthenticated guest token API, which limits how far back the timeline can be paginated. The exact number varies by Nitter instance and token pool health.

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | — | Required |
| `CAMOFOX_URL` | `http://localhost:9377` | Camofox Browser API URL |
| `NITTER_INSTANCE` | `https://nitter.net` | Nitter instance to use. If unset, auto-detects from the [LibreRedirect list](https://github.com/libredirect/instances) |

## License

MIT © [jinjiaKarl](https://github.com/jinjiaKarl)
