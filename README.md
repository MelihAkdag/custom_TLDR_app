# TLDR Feed Automation

Generic weekly research monitoring for:
- scientific papers
- keyword-based news
- optional LinkedIn inputs

The project fetches candidates from configured sources, filters them by topic relevance, stores normalized records in SQLite, summarizes the kept items with Azure OpenAI, and writes a Markdown/JSON digest.

## Current Status

The current implementation is intended for manual validation before periodic automation.

Working today:
- arXiv collection
- OpenAlex collection
- Crossref collection
- `news_rss` keyword news collection
- relevance filtering before summarization
- Semantic Scholar metadata enrichment
- landing-page abstract fallback for papers missing API abstracts
- Azure OpenAI summarization
- Markdown and JSON weekly reports

Available but optional:
- `linkedin_import` for manually supplied LinkedIn posts
- `linkedin_posts` for official LinkedIn API access to configured authors/pages

Not implemented in v1:
- Google Scholar collection
- Scopus collection
- broad LinkedIn keyword search across the public network
- scheduled automation/orchestration

## Pipeline

The pipeline is:

1. Collect candidate items from each enabled source for each topic.
2. Score relevance using keyword phrase matches, token overlap, `include_terms`, `exclude_terms`, and `min_relevance_score`.
3. Normalize and deduplicate items into SQLite.
4. Enrich missing paper metadata and abstracts when possible.
5. Summarize retained items with Azure OpenAI.
6. Generate Markdown and JSON reports.

Current item types:
- `paper`
- `news_article`
- `social_post`

## Project Layout

```text
config/
  topics.example.yaml
  sources.example.yaml
data/
imports/
  linkedin/
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

If your shell environment already provides Azure OpenAI variables, `.env` is optional. Otherwise set:

```env
AZURE_OPENAI_ENDPOINT=...
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_API_VERSION=2024-10-21
AZURE_OPENAI_DEPLOYMENT=...
```

Optional:

```env
SEMANTIC_SCHOLAR_API_KEY=
LINKEDIN_ACCESS_TOKEN=
```

## Topics Configuration

`config/topics.yaml` defines what the system should monitor.

Each topic supports:
- `topic_id`
- `display_name`
- `keywords`
- `include_terms`
- `exclude_terms`
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
    min_relevance_score: 3.0
    sources: ["arxiv", "openalex", "crossref", "news_rss"]
```

Guidance:
- increase `min_relevance_score` if the report is noisy
- add `include_terms` for domain-specific signals
- add `exclude_terms` for recurring off-topic categories
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

Optional LinkedIn sources:
- `linkedin_import`
- `linkedin_posts`

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
    timeout_seconds: 20

  linkedin_import:
    enabled: false

  linkedin_posts:
    enabled: false
```

Source notes:
- `news_rss` collects news articles, not social posts.
- `news_rss` can combine keyword search results with explicit publisher RSS feeds.
- `news_rss` supports `allowed_domains`, `blocked_domains`, and `custom_rss_feeds`.
- Keep `verify_ssl: true` for normal use. If your environment uses a corporate HTTPS inspection proxy, set `ca_bundle` per source or `TLDR_FEED_CA_BUNDLE`/`SSL_CERT_FILE` to your organization's trusted CA bundle.
- `landing_page` tries to extract missing abstracts from HTML pages.
- `linkedin_posts` requires an official LinkedIn token and configured author/page URNs.

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

This is the current recommended workflow.

### Corporate Network TLS Setup

If you are on a work network that inspects HTTPS traffic, keep SSL verification enabled and point the collector to the company CA bundle.

One-time shell setup for the current terminal:

```bash
export TLDR_FEED_CA_BUNDLE=/absolute/path/to/company-root-ca.pem
```

If you prefer to keep it in your local `.env`, add:

```env
TLDR_FEED_CA_BUNDLE=/absolute/path/to/company-root-ca.pem
```

You can also pin the same CA bundle in `config/sources.yaml`:

```yaml
sources:
  openalex:
    enabled: true
    verify_ssl: true
    ca_bundle: "/absolute/path/to/company-root-ca.pem"
```

Recommended manual commands on a corporate network:

```bash
export TLDR_FEED_CA_BUNDLE=/absolute/path/to/company-root-ca.pem
PYTHONPATH=src python3 -m tldr_feed.cli collect --week 2026-W13
PYTHONPATH=src python3 -m tldr_feed.cli summarize --run-id <RUN_ID>
PYTHONPATH=src python3 -m tldr_feed.cli report --run-id <RUN_ID>
```

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

This step is sequential. Large runs can take several minutes.

### 4. Generate the Report

```bash
PYTHONPATH=src python3 -m tldr_feed.cli report --run-id <RUN_ID>
```

This does not fetch or summarize again. It only rebuilds the report from existing stored data.

### 5. One-Command Run

If you want the whole flow in one command:

```bash
PYTHONPATH=src python3 -m tldr_feed.cli run-weekly --week 2026-W12
```

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

- `reports/YYYY/WW/weekly_report.md`
- `reports/YYYY/WW/weekly_report.json`

The Markdown report is organized by:
- topic
- section (`Papers`, `News`, `LinkedIn Posts`)
- entry

Each entry currently includes:
- large title heading
- metadata
- AI summary
- abstract or source text
- separator between entries

## Current Relevance Method

Relevance filtering is currently rule-based, not LLM-based.

The collector keeps an item only if it passes:
- phrase matching on keywords
- token overlap scoring
- `include_terms`
- `exclude_terms`
- `min_relevance_score`

The LLM is used after filtering, for summarization only.

## LinkedIn

For personal experimentation, the practical options are:
- `linkedin_import`: manual CSV, JSON, or URL input
- `linkedin_posts`: official API access for configured authors/pages, if you have a valid token

This project does not currently support broad public LinkedIn keyword search.

## Troubleshooting

If summarize fails with Azure errors:
- confirm `.env` or shell variables are present
- confirm `AZURE_OPENAI_API_VERSION` is set
- confirm the deployment name is correct

If collect fails with `SSL verification failed`:
- confirm you are using the company CA bundle, not disabling verification
- export `TLDR_FEED_CA_BUNDLE=/absolute/path/to/company-root-ca.pem`
- rerun `PYTHONPATH=src python3 -m tldr_feed.cli collect --week 2026-W13`

If the report is noisy:
- raise `min_relevance_score`
- reduce `max_results`
- add stronger `include_terms`
- add more aggressive `exclude_terms`

If many papers have no abstract:
- keep `semantic_scholar.enabled: true`
- keep `landing_page.enabled: true`
- note that some publishers block scraping or only expose the abstract through JavaScript/login walls

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

## Next Step

The next planned phase is periodic automation. Before that, the recommended path is:

1. tune topics and source settings
2. validate relevance and report quality
3. confirm manual runs are stable
4. then schedule the pipeline
