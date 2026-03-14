# Data Model — Politics-Contradictor

## Overview

Data flows through three storage layers:

- **Local SQLite** — used by the `statement-processor` pipeline for offline development (local-first, no external services required)
- **Supabase (PostgreSQL)** — the production database: tweets, articles, topics, contradictions, figure pages, agent run logs
- **Pinecone** — vector embeddings for semantic search over tweets and news articles

Raw text is stored in Supabase. Embeddings in Pinecone carry metadata that mirrors the Supabase fields needed for filtering and display. The local SQLite schema mirrors the Supabase `news_articles` table and adds extraction-specific tables (`stance_records`, `stance_relations`) used during local development.

---

## Supabase tables

### Phase 1 — Core data (LIVE)

#### `tweets`

Stores raw tweet data for the tracked public figures.

| Column | Type | Notes |
|---|---|---|
| `tweet_id` | TEXT | Primary key |
| `account_id` | TEXT | Twitter/X account identifier |
| `author_name` | TEXT | Human-readable name |
| `text` | TEXT | Full tweet text |
| `created_at` | TIMESTAMPTZ | Original tweet timestamp |
| `has_urls` | BOOLEAN | Whether the tweet contains URLs |

#### `news_articles`

Stores news articles scraped from RSS feeds.

| Column | Type | Notes |
|---|---|---|
| `id` | SERIAL | Primary key |
| `doc_id` | TEXT | Unique content hash (SHA-256) |
| `title` | TEXT | Article headline |
| `text` | TEXT | Full article body |
| `date` | TEXT | Publication date (string) |
| `media_name` | TEXT | Publication name |
| `media_type` | TEXT | `newspaper` / `radio` / `tv` / `broadcast` |
| `source_platform` | TEXT | `Google` / `Twitter` |
| `state` | TEXT | US state (where applicable) |
| `city` | TEXT | City (where applicable) |
| `link` | TEXT | Original article URL |
| `speakers_mentioned` | TEXT[] | Array of politician names mentioned |
| `created_at` | TIMESTAMPTZ | When the record was inserted |

---

### Phase 2 — Topic Extraction (PLANNED)

#### `topics`

Master taxonomy of political topics.

| Column | Type | Notes |
|---|---|---|
| `id` | SERIAL | Primary key |
| `name` | TEXT | Unique topic slug, e.g. `healthcare`, `economy` |
| `description` | TEXT | Human-readable description |

#### `tweet_topics`

Junction table: maps tweets to topics with a confidence score.

| Column | Type | Notes |
|---|---|---|
| `tweet_id` | TEXT | FK → `tweets.tweet_id` |
| `topic_id` | INTEGER | FK → `topics.id` |
| `confidence` | FLOAT | LLM-assigned confidence (0–1) |

Primary key: `(tweet_id, topic_id)`

#### `article_topics`

Junction table: maps articles to topics with a confidence score.

| Column | Type | Notes |
|---|---|---|
| `doc_id` | TEXT | FK → `news_articles.doc_id` |
| `topic_id` | INTEGER | FK → `topics.id` |
| `confidence` | FLOAT | LLM-assigned confidence (0–1) |

Primary key: `(doc_id, topic_id)`

**Note:** The Topic Extractor will also add a `topics TEXT[]` denormalised column to both `tweets` and `news_articles` for fast Pinecone metadata filtering. This avoids a join on hot query paths.

---

### Phase 3 — Contradiction Detection (PLANNED)

#### `contradictions`

Stores detected contradictions between a figure's statements and news coverage, or between past and present positions.

| Column | Type | Notes |
|---|---|---|
| `id` | SERIAL | Primary key |
| `figure_name` | TEXT | Politician name |
| `topic_id` | INTEGER | FK → `topics.id` |
| `tweet_id` | TEXT | Source tweet (nullable) |
| `doc_id` | TEXT | Source article (nullable) |
| `contradiction_type` | TEXT | `tweet_vs_news` / `past_vs_present` |
| `explanation` | TEXT | LLM-generated explanation |
| `severity` | TEXT | `minor` / `major` |
| `detected_at` | TIMESTAMPTZ | When the contradiction was detected |

---

### Phase 4 — Figure Pages (PLANNED)

#### `figure_pages`

Cached per-figure summary pages built by the Page Builder agent.

| Column | Type | Notes |
|---|---|---|
| `id` | SERIAL | Primary key |
| `figure_name` | TEXT | Unique — one row per tracked figure |
| `overview` | TEXT | General narrative summary |
| `top_topics` | JSONB | `[{topic, stance, evidence}]` |
| `recent_news` | JSONB | `[{title, date, source, summary}]` |
| `recent_tweets` | JSONB | `[{text, date}]` |
| `contradictions` | JSONB | `[{type, explanation, evidence}]` |
| `last_updated` | TIMESTAMPTZ | When the page was last rebuilt |

---

### Infrastructure

#### `agent_runs`

Audit log for background pipeline executions.

| Column | Type | Notes |
|---|---|---|
| `id` | SERIAL | Primary key |
| `agent_name` | TEXT | Which agent ran |
| `status` | TEXT | `running` / `completed` / `failed` |
| `records_processed` | INTEGER | Count of records handled |
| `error_message` | TEXT | Populated on failure |
| `started_at` | TIMESTAMPTZ | Run start time |
| `completed_at` | TIMESTAMPTZ | Run end time (null if still running) |

---

## Pinecone indexes

| Index | Dimension | Metric | Content |
|---|---|---|---|
| `politics` | 1024 | cosine | Tweet embeddings (~52K vectors) |
| `politics-news` | 1024 | cosine | News article embeddings (~400 vectors) |

Both indexes use the `RPRTHPB-text-embedding-3-small` model via `https://api.llmod.ai/v1`. The `RPRTHPB-` prefix is a vendor-specific identifier used by the llmod.ai OpenAI-compatible endpoint — it selects the underlying `text-embedding-3-small` model on that platform.

### Vector metadata — `politics` index (tweets)

Each vector carries the following metadata fields (mirrors `tweets` table):

| Field | Type | Notes |
|---|---|---|
| `tweet_id` | string | Supabase primary key |
| `author_name` | string | Politician name |
| `text` | string | Full tweet text |
| `created_at` | string | ISO timestamp |
| `topics` | list[string] | Added by Topic Extractor (Phase 2) |

### Vector metadata — `politics-news` index (articles)

| Field | Type | Notes |
|---|---|---|
| `doc_id` | string | Supabase primary key |
| `title` | string | Article headline |
| `media_name` | string | Publication |
| `state` | string | US state |
| `date` | string | Publication date |
| `speakers_mentioned` | list[string] | Politicians mentioned |
| `topics` | list[string] | Added by Topic Extractor (Phase 2) |

---

## Data flow

```
RSS Feeds
    ↓
src/rss-extractor/scrape.py
    ↓
news_articles (Supabase) + politics-news (Pinecone)

Twitter CSV
    ↓
src/load_tweets_to_pinecone.py
    ↓
tweets (Supabase) + politics (Pinecone)

                        ↓ Phase 2
Topic Extractor agent → topics / tweet_topics / article_topics
                        + updates Pinecone metadata with topic tags

                        ↓ Phase 3
Contradiction Finder  → contradictions table

                        ↓ Phase 4
Page Builder agent    → figure_pages table
```

---

## Local SQLite schema (statement-processor)

The `statement-processor` pipeline uses a local SQLite database for offline
development. The schema is defined in:

```
src/statement-processor/src/db/schema.sql
```

This is the **canonical local schema** and the single source of truth for the
three local tables. Apply or re-apply it with:

```bash
cd src/statement-processor
python scripts/init_local_db.py
```

See `docs/migrations.md` for guidance on making schema changes.

### `news_articles` (local mirror)

A local copy of the Supabase `news_articles` table, populated from a CSV export.

| Column | SQLite type | Notes |
|---|---|---|
| `id` | `INTEGER PRIMARY KEY AUTOINCREMENT` | Local surrogate key |
| `doc_id` | `TEXT NOT NULL UNIQUE` | SHA-256 content hash — deduplication key |
| `title` | `TEXT` | Article headline |
| `text` | `TEXT` | Full article body |
| `date` | `TEXT` | Publication date (string, format varies by source) |
| `media_name` | `TEXT` | Publication name |
| `media_type` | `TEXT` | `newspaper` / `radio` / `tv` / `broadcast` |
| `source_platform` | `TEXT` | `Google` / `Twitter` |
| `state` | `TEXT` | US state (where applicable) |
| `city` | `TEXT` | City (where applicable) |
| `link` | `TEXT` | Original article URL |
| `speakers_mentioned` | `TEXT DEFAULT '[]'` | JSON array string (Postgres `TEXT[]` → SQLite `TEXT`) |
| `created_at` | `TEXT NOT NULL` | ISO-8601 timestamp string |

**Type mapping note:** `speakers_mentioned` is stored as a JSON array string
(e.g. `'["Alice","Bob"]'`) rather than a Postgres `TEXT[]` array. The
ingestion layer normalises comma-separated strings to this format automatically.

### `stance_records`

One row per atomic political stance event extracted from a news article. Populated
by the stance extractor (planned). The column names align directly with the
`StanceEvent` fields defined in
`src/statement-processor/docs/stance_extraction_contract.md`.

| Column | SQLite type | Notes |
|---|---|---|
| `id` | `INTEGER PRIMARY KEY AUTOINCREMENT` | Local surrogate key |
| `doc_id` | `TEXT NOT NULL` | FK → `news_articles.doc_id` |
| `politician` | `TEXT` | Full name of the politician |
| `topic` | `TEXT` | High-level policy area (controlled vocabulary) |
| `subtopic` | `TEXT` | Optional finer-grained sub-category |
| `normalized_proposition` | `TEXT` | Single declarative sentence summarising the stance |
| `stance_direction` | `TEXT` | `support` / `oppose` / `mixed` / `unclear` |
| `stance_mode` | `TEXT` | `statement` / `action` / `promise` / `accusation` / `value_judgment` |
| `speaker` | `TEXT` | Who delivered the statement (may differ from politician) |
| `event_date` | `TEXT` | ISO-8601 date string (`YYYY`, `YYYY-MM`, or `YYYY-MM-DD`) |
| `event_date_precision` | `TEXT` | `day` / `month` / `year` / `approximate` |
| `evidence_role` | `TEXT` | `direct_quote` / `reported_speech` / `inferred_from_action` / `headline_claim` / `summary_statement` |
| `quote_text` | `TEXT` | Verbatim quote from the article |
| `quote_start_char` | `INTEGER` | 0-based start offset of `quote_text` in the article |
| `quote_end_char` | `INTEGER` | Exclusive end offset of `quote_text` in the article |
| `paraphrase` | `TEXT` | Brief paraphrase of the supporting evidence |
| `confidence` | `REAL` | Extractor confidence score (0.0–1.0) |
| `review_status` | `TEXT DEFAULT 'pending'` | `pending` / `approved` / `rejected` |
| `created_at` | `TEXT NOT NULL` | ISO-8601 timestamp string |
| `updated_at` | `TEXT NOT NULL` | ISO-8601 timestamp string |

Controlled vocabulary values for `topic`, `stance_direction`, `stance_mode`,
and `evidence_role` are defined in `src/statement-processor/src/contracts/vocab.json`.

### `stance_relations`

Pairwise relations between `stance_records` rows — for example, contradiction
or reinforcement relationships. Populated by relation generation logic (planned).

| Column | SQLite type | Notes |
|---|---|---|
| `id` | `INTEGER PRIMARY KEY AUTOINCREMENT` | Local surrogate key |
| `from_stance_id` | `INTEGER NOT NULL` | FK → `stance_records.id` |
| `to_stance_id` | `INTEGER NOT NULL` | FK → `stance_records.id` |
| `relation_type` | `TEXT NOT NULL` | e.g. `contradiction`, `reinforcement` |
| `confidence` | `REAL` | Confidence in the relation (0.0–1.0) |
| `reason` | `TEXT` | Explanation of the relation |
| `created_at` | `TEXT NOT NULL` | ISO-8601 timestamp string |

---

## Raw vs normalised data

- **Raw**: `tweets.text`, `news_articles.text` — unmodified source content.
- **Normalised/derived**: `topics`, `contradictions`, `figure_pages` — LLM-generated analysis of the raw data.
- **Embeddings**: Pinecone vectors are derived from the raw text using the embedding model. They are regenerated if the raw text changes.

---

## Known schema assumptions

- `news_articles.doc_id` is a SHA-256 hash of the article content — used as a stable deduplication key.
- `tweets.tweet_id` is the original Twitter/X numeric ID stored as TEXT.
- `news_articles.date` is stored as TEXT (not TIMESTAMPTZ) — date parsing may vary by source feed.
- `figure_pages.figure_name` must exactly match the names used in `src/rss-extractor/config/politicians.yaml`.
