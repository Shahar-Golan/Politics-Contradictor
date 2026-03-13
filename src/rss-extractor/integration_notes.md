# Integration Notes — Scout/Extractor Pipeline

This document provides detailed guidance for integrating the merge-ready package into the team repository and uploading records to Supabase.

---

## What to Copy

Copy these two folders into your project:

| Source | Destination | Purpose |
|---|---|---|
| `merge_ready/src/` | `<your_repo>/src/` | All pipeline source code |
| `merge_ready/config/` | `<your_repo>/config/` | Feed, politician, topic, and settings configuration |

Optionally copy:

| Source | Purpose |
|---|---|
| `merge_ready/tests/` | Schema adapter tests |
| `merge_ready/examples/` | Example output artifacts |

After copying, ensure your `PYTHONPATH` includes the `src/` directory.

---

## What the Code Does

### Scout (`src/scout/`)

Responsible for the data **acquisition** layer:

- **`poller.py`** — downloads raw RSS/Atom feed XML via HTTP, with retry and conditional GET support.
- **`feed_parser.py`** — parses feed XML into typed `FeedItem` records using `feedparser`.
- **`dedup.py`** — filters out already-seen feed items using the database.
- **`fetcher.py`** — downloads article HTML pages from feed item URLs.
- **`scheduler.py`** — determines which feeds are due for polling based on last-poll timestamps.
- **`models.py`** — domain dataclasses: `FeedSource`, `FeedFetchLog`, `FeedItem`, `RawArticle`.

### Extractor (`src/extractor/`)

Responsible for **content extraction and analysis**:

- **`article_extractor.py`** — orchestrates extraction using Trafilatura (preferred) or BeautifulSoup (fallback).
- **`metadata.py`** — extracts title, byline, publication date, site name from HTML (JSON-LD, Open Graph, meta tags).
- **`cleaner.py`** — normalises Unicode, collapses whitespace, strips artefacts.
- **`canonicalise.py`** — resolves the canonical URL from `<link rel="canonical">` or `og:url`.
- **`relevance.py`** — scores how relevant an article is to each tracked politician.
- **`quotes.py`** — extracts direct quotes and indirect statements attributed to politicians.
- **`topics.py`** — assigns topic labels via keyword matching.
- **`models.py`** — domain dataclasses: `ExtractedArticle`, `ArticleMetadata`, `PoliticianMention`, `StatementCandidate`.

### Adapter (`src/adapters/`)

Responsible for **schema transformation** for Supabase integration:

- **`supabase_export.py`** — transforms `ExtractedArticle` + `PoliticianMention` records into the team's exact Supabase target schema.

### Pipelines (`src/pipelines/`)

Responsible for **orchestration**:

- **`ingest_feed.py`** — end-to-end feed polling + parsing + dedup + persistence.
- **`ingest_article.py`** — end-to-end article extraction + relevance scoring + quote extraction + persistence.

### Utils (`src/utils/`)

Shared helpers:

- **`config.py`** — YAML configuration loaders for feeds, politicians, topics, settings.
- **`hashing.py`** — deterministic SHA-256 fingerprints for URLs and content.
- **`urls.py`** — URL normalisation (strips tracking params, normalises scheme/host).
- **`time.py`** — timestamp parsing and normalisation using `python-dateutil`.
- **`logging.py`** — logging configuration.

### Storage (`src/storage/`)

- **`sql.py`** — SQLite schema creation and CRUD operations.
- **`document_store.py`** — file-based storage for raw HTML and extracted text.
- **`schemas.py`** — typed dataclasses representing database table rows.

---

## Target Output Schema

The exported record schema matches the following CSV header exactly:

```
id,doc_id,title,text,date,media_name,media_type,source_platform,state,city,link,speakers_mentioned,created_at
```

---

## Field Mapping Rules

| Target Field | Source | Rule |
|---|---|---|
| `id` | Generated | New UUID-4 created at export time. Each export invocation produces a new `id`. |
| `doc_id` | `ExtractedArticle.article_id` | The pipeline's internal SHA-256 fingerprint of the normalised article URL. Stable across re-exports of the same article. |
| `title` | `ExtractedArticle.metadata.title` | Extracted from JSON-LD `headline`, Open Graph `og:title`, or HTML `<title>`. Empty string if none found. |
| `text` | `ExtractedArticle.body` | Cleaned article body text after extraction and normalisation. Empty string if extraction failed. |
| `date` | `ExtractedArticle.metadata.published_at` | ISO 8601 formatted publication date. `None`/null if not found in the article HTML. |
| `media_name` | `ExtractedArticle.metadata.site_name` | Publisher name from JSON-LD `publisher.name` or `og:site_name`. Empty string `""` if not found. |
| `media_type` | Configured default | Defaults to `"rss_news"`. Can be overridden per call via the `media_type` parameter. |
| `source_platform` | Configured default | Fixed to `"rss"` for this pipeline. Can be overridden per call. |
| `state` | Not currently derived | Defaults to `""`. Geographic extraction is not implemented. |
| `city` | Not currently derived | Defaults to `""`. Geographic extraction is not implemented. |
| `link` | `ExtractedArticle.metadata.canonical_url` or `ExtractedArticle.url` | Uses the canonical URL if available; otherwise falls back to the article's fetch URL. |
| `speakers_mentioned` | `PoliticianMention` records | Comma-separated list of unique `politician_name` values from the mention records. Empty string `""` if no mentions. |
| `created_at` | Generated | ISO 8601 UTC timestamp of when the export record was created. |

---

## Null and Fallback Policies

| Field | Can Be Null? | Fallback |
|---|---|---|
| `id` | No | Always generated (UUID-4) |
| `doc_id` | No | Always present (SHA-256 hash) |
| `title` | No | Empty string `""` if not extracted |
| `text` | No | Empty string `""` if extraction failed |
| `date` | **Yes** | `None`/null if publication date not found |
| `media_name` | No | Empty string `""` if site name not found |
| `media_type` | No | `"rss_news"` |
| `source_platform` | No | `"rss"` |
| `state` | No | Empty string `""` (not currently derived) |
| `city` | No | Empty string `""` (not currently derived) |
| `link` | No | Falls back to article URL |
| `speakers_mentioned` | No | Empty string `""` if no mentions |
| `created_at` | No | Always generated (UTC now) |

**Key policy:** Only `date` can be null. All other string fields use `""` as the fallback value to avoid null-handling complexity in downstream systems.

---

## How to Run the Pipeline

### Minimal Python workflow

```python
import sqlite3
from pathlib import Path

from utils.config import load_feeds, load_politicians, load_settings, load_topics
from storage.sql import init_schema, get_feed_items_pending_fetch, get_raw_articles_pending_extraction
from pipelines.ingest_feed import ingest_feed
from pipelines.ingest_article import ingest_article
from scout.fetcher import fetch_article
from adapters.supabase_export import to_supabase_record, records_to_csv

# 1. Setup
conn = sqlite3.connect("data/tracker.db")
conn.row_factory = sqlite3.Row
init_schema(conn)

settings = load_settings("config/settings.yaml")
feeds = load_feeds("config/feeds.yaml")
politicians = load_politicians("config/politicians.yaml")
topics = load_topics("config/topics.yaml")

# 2. Poll feeds
for source in feeds:
    if source.enabled:
        ingest_feed(source, conn, settings)

# 3. Fetch articles
for item in get_feed_items_pending_fetch(conn):
    raw = fetch_article(item, settings)
    # (The raw article is persisted during ingest_article below)

# 4. Extract articles
supabase_records = []
for raw_article in get_raw_articles_pending_extraction(conn):
    result = ingest_article(raw_article, conn, politicians, topics, settings)
    if result.extracted_article and result.extracted_article.body:
        record = to_supabase_record(result.extracted_article, mentions=result.mentions)
        supabase_records.append(record)

# 5. Export
csv_output = records_to_csv(supabase_records)
Path("output.csv").write_text(csv_output)
```

---

## How to Upload to Supabase

### Option A: CSV upload

1. Generate a CSV file using `records_to_csv()`.
2. Upload via the Supabase dashboard: **Table Editor → Import CSV**.

### Option B: Python client

```python
from supabase import create_client
from adapters.supabase_export import records_to_dicts

supabase = create_client("https://your-project.supabase.co", "your-api-key")

dicts = records_to_dicts(supabase_records)
for batch in chunks(dicts, 100):  # upload in batches
    supabase.table("articles").insert(batch).execute()
```

### Option C: Direct SQL insert

Use the dict output from `record_to_dict()` to build INSERT statements for your database client.

---

## Configuration

### `config/feeds.yaml`

Defines RSS feed sources to poll. Each entry needs `id`, `name`, `url`, and optionally `enabled`, `tags`, `poll_interval_minutes`.

### `config/politicians.yaml`

Defines politicians to track. Each entry needs `id`, `name`, `aliases` (list of name variants), `party`, `role`.

### `config/topics.yaml`

Defines topic taxonomy. Each entry needs `id` and `keywords` (list of matching keywords).

### `config/settings.yaml`

Runtime settings for HTTP, polling intervals, extraction, relevance scoring, and storage paths. All fields have sensible defaults.

---

## Assumptions and Limitations

1. **Geographic extraction not implemented** — `state` and `city` fields are always empty strings. If needed, add a geographic extraction step before the export adapter.

2. **SQLite for local storage** — the pipeline uses SQLite for persistence. This is independent of Supabase; SQLite is used as the pipeline's internal working database.

3. **Network access required** — the Scout poller and fetcher need HTTP access to RSS feed URLs and article pages.

4. **Trafilatura optional** — Trafilatura is the preferred extraction backend but BeautifulSoup is used as fallback if Trafilatura is not installed.

5. **Import paths** — all imports use bare package names (e.g. `from scout.models import ...`). Ensure the `src/` directory is on your `PYTHONPATH`.

6. **No authentication** — the pipeline does not handle authentication for RSS feeds or article pages. All feeds must be publicly accessible.

---

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| `requests` | ≥ 2.31 | HTTP requests |
| `feedparser` | ≥ 6.0 | RSS/Atom parsing |
| `beautifulsoup4` | ≥ 4.12 | HTML parsing |
| `lxml` | ≥ 4.9 | HTML parser backend |
| `python-dateutil` | ≥ 2.8 | Timestamp parsing |
| `pyyaml` | ≥ 6.0 | YAML config loading |
| `trafilatura` | ≥ 1.6 | Article text extraction (optional) |

---

## Entrypoints

The package exposes these key functions:

| Function | Module | Purpose |
|---|---|---|
| `ingest_feed()` | `pipelines.ingest_feed` | Poll, parse, and persist one feed |
| `ingest_article()` | `pipelines.ingest_article` | Extract and persist one article |
| `fetch_article()` | `scout.fetcher` | Fetch HTML for one feed item |
| `to_supabase_record()` | `adapters.supabase_export` | Convert one article to Supabase schema |
| `to_supabase_records()` | `adapters.supabase_export` | Batch conversion |
| `records_to_csv()` | `adapters.supabase_export` | Serialise to CSV |
| `records_to_dicts()` | `adapters.supabase_export` | Serialise to list of dicts |
| `init_schema()` | `storage.sql` | Create database tables |
| `load_feeds()` | `utils.config` | Load feed configuration |
| `load_politicians()` | `utils.config` | Load politician configuration |
| `load_settings()` | `utils.config` | Load runtime settings |
| `load_topics()` | `utils.config` | Load topic taxonomy |
