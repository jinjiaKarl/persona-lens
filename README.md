# persona-lens

CLI tool that generates a structured persona analysis report from any X (Twitter) profile.

## How it works

1. Fetches the public profile and recent tweets via Nitter using [Camofox Browser](https://github.com/jo-inc/camofox-browser) (anti-detection Firefox automation)
2. Decodes tweet timestamps from Twitter snowflake IDs to compute posting activity patterns
3. Sends the page snapshot + activity data to OpenAI GPT-4o for analysis
4. Outputs a Markdown report with personality traits, writing style, interests, expertise, values, and an activity heatmap

## Requirements

- Python 3.13+
- Node.js (for Camofox Browser)
- `uv` package manager
- OpenAI API key

## Setup

### 1. Start Camofox Browser

Camofox Browser is a Node.js service that wraps Camoufox (anti-detection Firefox) behind an HTTP API. It must be running before you use persona-lens.

```bash
git clone https://github.com/jo-inc/camofox-browser
cd camofox-browser
npm install
npm start
```

The service starts on port 9377 and downloads Camoufox (~300MB) on first run.

Alternatively, build and run with Docker:

```bash
git clone https://github.com/jo-inc/camofox-browser
cd camofox-browser
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
# Print report to terminal (default)
uv run persona-lens elonmusk

# @ prefix is optional
uv run persona-lens @elonmusk

# Fetch more tweets for a deeper analysis
uv run persona-lens elonmusk --tweets 50

# Save to a Markdown file instead of printing
uv run persona-lens elonmusk --output report.md

# Use click mode (clicks "Load more" button) instead of cursor-based pagination
uv run persona-lens elonmusk --tweets 200 --mode click
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--tweets` / `-t` | `20` | Number of tweets to analyse |
| `--output` / `-o` | — | Save report to a file instead of printing to terminal |
| `--mode` / `-m` | `cursor` | Pagination mode: `cursor` (URL-based, faster) or `click` (clicks "Load more" button) |

## Report sections

Each report includes:

- **Summary** — 2–3 sentence persona overview
- **Personality Traits** — inferred from writing style and content
- **Communication Style** — tone and formality
- **Writing Style** — vocabulary, structure, humor, emoji usage
- **Interests** — topics frequently discussed
- **Areas of Expertise** — domains with demonstrated knowledge
- **Core Values** — values evident in posts
- **Posting Activity** — day-of-week and time-of-day ASCII heatmaps (decoded from tweet timestamps, UTC) with psychological insights

## Limitations

**Tweet cap:** Nitter uses Twitter's unauthenticated guest token API, which limits how far back the timeline can be paginated. The exact number varies by Nitter instance and token pool health. Twitter's own timeline API supports deeper history for authenticated users, but Nitter's anonymous mode does not provide a logged-in session.

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | — | Required |
| `CAMOFOX_URL` | `http://localhost:9377` | Camofox Browser API URL |
| `NITTER_INSTANCE` | `https://nitter.net` | Nitter instance to use. If unset, auto-detects a reachable instance from the [LibreRedirect list](https://github.com/libredirect/instances) |

## License

MIT © [jinjiaKarl](https://github.com/jinjiaKarl)
