# Merge-Ready Package — Scout/Extractor Pipeline

Minimum viable package for integrating the Scout/Extractor RSS ingestion pipeline into the team repository.

## What This Package Does

This package ingests political news articles from RSS feeds and produces structured records compatible with the team's Supabase schema.

**Pipeline stages:**

1. **Scout** — polls RSS feeds, parses items, deduplicates, and fetches article HTML.
2. **Extractor** — extracts clean text, metadata, politician mentions, and quotes from HTML.
3. **Adapter** — transforms extracted records into the team's target schema for Supabase upload.

## Quick Start

### 1. Copy into your repository

Copy the following folders into your project:

```
merge_ready/src/       →  your_repo/src/        (or your source root)
merge_ready/config/    →  your_repo/config/
```

### 2. Install dependencies

The pipeline requires these Python packages:

```
requests
feedparser
beautifulsoup4
lxml
python-dateutil
pyyaml
trafilatura    # optional, preferred extraction backend
```

Install via pip:

```bash
pip install requests feedparser beautifulsoup4 lxml python-dateutil pyyaml trafilatura
```

### 3. Ensure `src/` is on your Python path

Add the source root to `PYTHONPATH`:

```bash
export PYTHONPATH=src:$PYTHONPATH
```

Or in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
pythonpath = ["src"]
```

### 4. Initialise the database

```python
import sqlite3
from storage.sql import init_schema

conn = sqlite3.connect("data/tracker.db")
conn.row_factory = sqlite3.Row
init_schema(conn)
```

### 5. Run the pipeline

```python
from utils.config import load_feeds, load_politicians, load_settings, load_topics
from pipelines.ingest_feed import ingest_feed
from pipelines.ingest_article import ingest_article
from storage.sql import get_feed_items_pending_fetch, get_raw_articles_pending_extraction
from scout.fetcher import fetch_article

# Load configuration
settings = load_settings("config/settings.yaml")
feeds = load_feeds("config/feeds.yaml")
politicians = load_politicians("config/politicians.yaml")
topics = load_topics("config/topics.yaml")

# Stage 1: Poll feeds
for source in feeds:
    if source.enabled:
        result = ingest_feed(source, conn, settings)
        print(f"Feed {source.id}: {result.items_new} new items")

# Stage 2: Fetch articles
pending = get_feed_items_pending_fetch(conn)
for item in pending:
    raw = fetch_article(item, settings)
    # raw is persisted inside ingest_article below

# Stage 3: Extract and persist
pending_raw = get_raw_articles_pending_extraction(conn)
for raw_article in pending_raw:
    result = ingest_article(raw_article, conn, politicians, topics, settings)
    print(f"Article {result.article_id}: {result.mentions_count} mentions")
```

### 6. Export to Supabase format

```python
from adapters.supabase_export import to_supabase_record, records_to_csv, records_to_dicts

# After extraction, convert to Supabase records
record = to_supabase_record(
    article=result.extracted_article,
    mentions=result.mentions,
)

# As CSV
csv_output = records_to_csv([record])

# As dicts (for JSON or direct Supabase insert)
dicts = records_to_dicts([record])
```

## Output Schema

Every exported record has exactly these fields:

| Field | Type | Source |
|---|---|---|
| `id` | UUID string | Generated at export time |
| `doc_id` | string | Pipeline article fingerprint |
| `title` | string | Extracted article headline |
| `text` | string | Cleaned article body |
| `date` | ISO 8601 or null | Publication date |
| `media_name` | string | Publisher name (may be `""`) |
| `media_type` | string | `"rss_news"` (default) |
| `source_platform` | string | `"rss"` |
| `state` | string | `""` (not currently extracted) |
| `city` | string | `""` (not currently extracted) |
| `link` | string | Canonical article URL |
| `speakers_mentioned` | string | Comma-separated politician names |
| `created_at` | ISO 8601 | Record creation timestamp |

See `examples/` for sample CSV and JSON files.

## Package Structure

```
merge_ready/
├── README.md                  ← This file
├── integration_notes.md       ← Detailed field mapping and policies
├── .env.example               ← Template for Supabase credentials
├── export_csv.py              ← Script: export all stored data to CSV
├── push_to_supabase.py        ← Script: push CSV to Supabase
├── manual_test.py             ← Script: run full pipeline end-to-end
├── config/
│   ├── feeds.yaml             ← RSS feed sources
│   ├── politicians.yaml       ← Politicians to track
│   ├── topics.yaml            ← Topic taxonomy
│   └── settings.yaml          ← Runtime settings
├── src/
│   ├── scout/                 ← Feed polling, parsing, fetching
│   ├── extractor/             ← Text extraction, relevance, quotes
│   ├── storage/               ← Database and document storage
│   ├── pipelines/             ← Orchestration (ingest_feed, ingest_article)
│   ├── adapters/              ← Supabase schema export adapter
│   └── utils/                 ← Shared helpers (hashing, URLs, time, config)
├── tests/
│   └── test_supabase_export.py
└── examples/
    ├── sample_export.csv
    └── sample_export.json
```

## Top-Level Scripts

### Export all stored data to CSV

Generate `output.csv` from everything in the local SQLite database:

```bash
cd merge_ready
python export_csv.py                        # default paths
python export_csv.py --db data/tracker.db   # custom DB path
python export_csv.py --out my_export.csv    # custom output file
```

### Push to Supabase

Upload `output.csv` to your Supabase table with automatic deduplication:

```bash
# 1. Set up credentials (one-time)
cp .env.example .env
# Edit .env with your SUPABASE_URL and SUPABASE_KEY

# 2. Install the Supabase client (one-time)
pip install supabase

# 3. Push
python push_to_supabase.py                       # defaults
python push_to_supabase.py --dry-run              # preview only
python push_to_supabase.py --table my_table       # custom table name
```

The script deduplicates by `doc_id` — records already present in Supabase are skipped automatically.

**Security:** Store your Supabase API key in `.env` only. Never commit `.env` to version control. See `.env.example` for details on where to find your credentials.

## Running Tests

```bash
cd merge_ready
python -m pytest tests/ -v
```

## See Also

- `integration_notes.md` — detailed field mapping, null policies, and Supabase upload guidance
- `.env.example` — template for Supabase credentials
