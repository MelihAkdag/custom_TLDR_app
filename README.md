# TLDR Feed Automation

Generic weekly research monitoring for:
- scientific papers
- keyword-based news

The project fetches candidates from configured sources, filters them by topic relevance, stores normalized records in SQLite, summarizes the kept items with a configurable LLM provider, and writes a Markdown/JSON digest.

## Current Status

- arXiv collection
- OpenAlex collection
- Crossref collection
- `news_rss` keyword news collection
- Relevance filtering before summarization
- Semantic Scholar metadata enrichment
- Landing-page abstract fallback for papers missing API abstracts
- OpenAI, Azure OpenAI, Gemini, Ollama, and deterministic summarization
- Markdown and JSON weekly reports
- Scheduled automation via crontab
- Email reports delivery using embedded HTML

## Pipeline

The pipeline is:

1. Collect candidate items from each enabled source for each topic.
2. Score relevance using keyword phrase matches, token overlap, `include_terms`, `exclude_terms`, and `min_relevance_score`.
3. Normalize and deduplicate items into SQLite.
4. Enrich missing paper metadata and abstracts when possible.
5. Summarize retained items with the configured summarizer.
6. Generate Markdown and JSON reports.

Current item types:
- `paper`
- `news_article`

## Project Layout

```text
config/
  topics.example.yaml
  sources.example.yaml
data/
reports/
src/tldr_feed/
tests/
```

Important runtime files:
- `config/topics.yaml`: your topics and keyword rules
- `config/sources.yaml`: enabled sources and source settings
- `.env`: local credentials, if not already injected by your environment
- `data/state.db`: SQLite state
- `reports/YYYY/WW/weekly_report.md`: rendered digest
- `reports/YYYY/WW/weekly_report.json`: machine-readable export

## Setup

Create and activate a virtual environment:

```bash
cd /home/melakd/TLDR_ship_autonomy
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Create your local config files:

```bash
cp config/topics.example.yaml config/topics.yaml
cp config/sources.example.yaml config/sources.yaml
cp .env.example .env
```

If your shell environment already provides summarizer variables, `.env` is optional. Otherwise set one of these options.

OpenAI:

```env
SUMMARIZER_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

Azure OpenAI:

```env
SUMMARIZER_PROVIDER=azure_openai
AZURE_OPENAI_ENDPOINT=...
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_API_VERSION=2024-10-21
AZURE_OPENAI_DEPLOYMENT=...
```

Gemini:

```env
SUMMARIZER_PROVIDER=gemini
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.5-flash
```

Ollama:

```env
SUMMARIZER_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.1:8b
OLLAMA_TIMEOUT_SECONDS=120
```

Email Settings (Optional):

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
EMAIL_FROM=your-email@gmail.com
EMAIL_TO=recipient1@example.com,recipient2@example.com
```

## Topics Configuration

`config/topics.yaml` defines what the system should monitor.

Each topic supports:
- `topic_id`
- `display_name`
- `keywords`
- `include_terms`
- `exclude_terms`
- `allowed_paper_languages`
- `min_relevance_score`
- `sources`

Example:

```yaml
topics:
  - topic_id: "ship_autonomy"
    display_name: "Ship Autonomy"
    keywords:
      - "autonomous ship"
      - "autonomous vessel"
      - "autonomous surface vessel"
      - "unmanned surface vessel"
      - "maritime autonomous navigation"
    include_terms:
      - "maritime"
      - "ship"
      - "vessel"
      - "collision avoidance"
      - "COLREG"
      - "AIS"
      - "path planning"
      - "sensor fusion"
    exclude_terms:
      - "ground vehicle"
      - "aircraft"
      - "drone"
      - "medical"
    allowed_paper_languages: ["en"]
    min_relevance_score: 3.0
    sources: ["arxiv", "openalex", "crossref", "news_rss"]
```

Guidance:
- increase `min_relevance_score` if the report is noisy
- add `include_terms` for domain-specific signals
- add `exclude_terms` for recurring off-topic categories
- use `allowed_paper_languages: ["en"]` if you want to keep only English papers while leaving news untouched
- avoid short ambiguous acronyms unless you really need them

## Sources Configuration

`config/sources.yaml` controls source behavior.

Common sources:
- `arxiv`
- `openalex`
- `crossref`
- `news_rss`
- `semantic_scholar`
- `landing_page`


Recommended paper + news setup:

```yaml
sources:
  arxiv:
    enabled: true
    max_results: 10
    timeout_seconds: 20

  openalex:
    enabled: true
    max_results: 10
    timeout_seconds: 20

  crossref:
    enabled: true
    max_results: 10
    timeout_seconds: 20

  news_rss:
    enabled: true
    max_results: 10
    timeout_seconds: 20
    hl: "en-US"
    gl: "US"
    ceid: "US:en"
    window_days: 7

  semantic_scholar:
    enabled: true
    timeout_seconds: 20

  landing_page:
    enabled: true
```

Source notes:
- `news_rss` collects news articles, not social posts.
- `news_rss` can combine keyword search results with explicit publisher RSS feeds.
- `news_rss` supports `allowed_domains`, `blocked_domains`, and `custom_rss_feeds`.
- Keep `verify_ssl: true` for normal use. If your environment uses a corporate HTTPS inspection proxy, set `ca_bundle` per source or `TLDR_FEED_CA_BUNDLE`/`SSL_CERT_FILE` to your organization's trusted CA bundle.
- `landing_page` tries to extract missing abstracts from HTML pages.

Example `news_rss` tuning for maritime sites:

```yaml
news_rss:
  enabled: true
  max_results: 10
  timeout_seconds: 20
  use_search_feed: true
  hl: "en-US"
  gl: "US"
  ceid: "US:en"
  window_days: 7
  allowed_domains:
    - "gcaptain.com"
    - "safety4sea.com"
    - "seanews.co.uk"
  blocked_domains: []
  custom_rss_feeds:
    - url: "https://gcaptain.com/feed/"
      source_name: "gCaptain"
```

## Manual Pipeline

### 1. Start Fresh

If you want a clean test run:

```bash
rm data/state.db
rm -r reports/2026/12
```

If the report folder does not exist, that is fine.

### 2. Collect

Run collection for a specific ISO week:

```bash
PYTHONPATH=src python3 -m tldr_feed.cli collect --week 2026-W12
```

This prints a `run_id`.

You can also collect by date range:

```bash
PYTHONPATH=src python3 -m tldr_feed.cli collect --from 2026-03-16 --to 2026-03-22
```

### 3. Summarize

Use the `run_id` from collection:

```bash
PYTHONPATH=src python3 -m tldr_feed.cli summarize --run-id <RUN_ID>
```

To summarize with a local Ollama model in the current terminal:

```bash
export SUMMARIZER_PROVIDER=ollama
export OLLAMA_BASE_URL=http://127.0.0.1:11434
export OLLAMA_MODEL=llama3.1:8b
PYTHONPATH=src python3 -m tldr_feed.cli summarize --run-id <RUN_ID>
```

This step is sequential. Large runs can take several minutes.

### 4. Generate the Report

```bash
PYTHONPATH=src python3 -m tldr_feed.cli report --run-id <RUN_ID>
```

This does not fetch or summarize again. It only rebuilds the report from existing stored data.

### 5. One-Command Run (with Email)

If you want the whole flow in one command and have emailing configured:

```bash
PYTHONPATH=src python3 -m tldr_feed.cli run-weekly --week 2026-W12 --email
```

Or just use the provided script to ensure virtual environments are active:
```bash
./scripts/run_and_email.sh
```

## Scheduled Automation

To run the pipeline automatically, such as every Monday at 8 AM, use the provided `run_and_email.sh` with a cronjob.

1. Edit your crontab:
   ```bash
   crontab -e
   ```
2. Insert the following entry (adjust your absolute paths):
   ```cron
   0 8 * * 1 /Users/yourusername/Projects/custom_TLDR_app/scripts/run_and_email.sh >> /tmp/tldr_cron.log 2>&1
   ```

## GitHub Pages

Reports can be automatically published to GitHub Pages after every run.

### First-time setup

1. In `jekyll/_config.yml`, set `baseurl` to your repository name (e.g. `/my-tldr-app`) and `url` to `https://<your-github-username>.github.io`.
2. Push the repository to GitHub.
3. Go to **Settings → Pages** in your GitHub repository.
4. Under **Source**, select **Deploy from a branch**, set **Branch** to `gh-pages` and folder to `/ (root)`, then save.

The `gh-pages` branch is created automatically on the first workflow run.

### How publishing works

`scripts/run_and_email.sh` commits and pushes new report files after every weekly run. The GitHub Actions workflow (`.github/workflows/publish-reports.yml`) detects the push, runs `scripts/build_jekyll_site.py` to generate Jekyll source from the `reports/` directory, builds the site with Jekyll, and deploys the output to the `gh-pages` branch. The site is live within ~2 minutes of the push.

You can also trigger a manual rebuild from **Actions → Publish Reports to GitHub Pages → Run workflow**.

## Inspecting Progress

While summarization is running, check progress in another terminal:

```bash
python3 - <<'PY'
import sqlite3
conn = sqlite3.connect("data/state.db")
run_id = "<RUN_ID>"
total = conn.execute("select count(*) from run_items where run_id = ?", (run_id,)).fetchone()[0]
done = conn.execute("""
select count(*)
from run_items ri
join summaries s on s.item_id = ri.item_id
where ri.run_id = ?
""", (run_id,)).fetchone()[0]
print({"total_items": total, "summarized": done, "remaining": total - done})
PY
```

## Outputs

Reports are written to:

- `reports/YYYY/WW/papers.md`
- `reports/YYYY/WW/news.md`
- `reports/YYYY/WW/weekly_report.json`

Each entry includes:
- Title
- Metadata
- AI summary
- Abstract or source text

## Current Relevance Method

Relevance filtering is currently rule-based, not LLM-based.

The collector keeps an item only if it passes:
- phrase matching on keywords
- token overlap scoring
- `include_terms`
- `exclude_terms`
- `min_relevance_score`

The LLM is used after filtering, for summarization only.

## Troubleshooting

If summarize fails with Ollama errors:
- confirm `SUMMARIZER_PROVIDER=ollama`
- confirm Ollama is running locally
- confirm `OLLAMA_MODEL` matches a model installed in Ollama
- confirm `OLLAMA_BASE_URL` points to the running Ollama server

If summarize fails with Azure/OpenAI/Gemini errors:
- confirm `.env` or shell variables are present
- confirm `SUMMARIZER_PROVIDER` is set correctly
- confirm the deployment name is correct

If the report is noisy:
- raise `min_relevance_score`
- reduce `max_results`
- add stronger `include_terms`
- add more aggressive `exclude_terms`

If many papers have no abstract:
- keep `semantic_scholar.enabled: true`
- keep `landing_page.enabled: true`

If you only want to regenerate Markdown:

```bash
PYTHONPATH=src python3 -m tldr_feed.cli report --run-id <RUN_ID>
```

## Tests

Run the local test suite with:

```bash
python3 -m unittest discover -s tests
python3 -m compileall src tests
```

## Author

- Melih Akdağ
- Date: 2026-04-07

