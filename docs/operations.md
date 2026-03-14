# Operations — Politics-Contradictor

## Overview

The system has two operational modes:

- **Interactive query** (System B) — responds to user questions in real time via the web UI or API.
- **Background pipeline** (System A) — a scheduled batch job that ingests data, runs analysis, and refreshes per-figure pages. _This mode is planned but not yet implemented._

---

## Running the backend API

```bash
conda activate politician-tracker
python api/index.py
```

Flask runs on `http://localhost:5000` by default.

---

## API endpoints

| Method | Endpoint | Description | Status |
|---|---|---|---|
| GET | `/api/stats` | Returns system configuration parameters | Live |
| POST | `/api/prompt` | Simple RAG over tweets (legacy) | Live |
| POST | `/api/agent/query` | Legacy ReAct agent (tweets only) | Live |
| POST | `/api/v2/query` | Multi-agent LangGraph graph (tweets + news) | Live |
| POST | `/api/v2/query/stream` | Multi-agent graph with SSE token streaming | Live |

### Example — multi-agent query

```bash
curl -X POST http://localhost:5000/api/v2/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What did Trump say about immigration?"}'
```

### Example — streaming query

```bash
curl --no-buffer -X POST http://localhost:5000/api/v2/query/stream \
  -H "Content-Type: application/json" \
  -d '{"query": "What is Biden's stance on climate change?"}'
```

The streaming endpoint returns `text/event-stream` with events: `node_start`, `node_end`, `token`, `done`.

---

## Configuration files

| File | Purpose |
|---|---|
| `.env` | Runtime secrets and service URLs — never committed |
| `.env.example` | Reference for all required and optional environment variables |
| `environment.yml` | Python/conda environment — source of truth for dependencies |
| `src/rss-extractor/config/politicians.yaml` | List of tracked public figures |
| `src/rss-extractor/config/feeds.yaml` | RSS feed URLs per politician |
| `src/rss-extractor/config/topics.yaml` | Political topic taxonomy |
| `src/rss-extractor/config/settings.yaml` | RSS extractor runtime settings |
| `src/statement-processor/src/contracts/vocab.json` | Controlled vocabulary for stance extraction |
| `src/statement-processor/schemas/stance_extraction.schema.json` | JSON Schema for LLM output validation |

### Required environment variables

```env
OPENAI_API_KEY=        # OpenAI-compatible API key for llmod.ai (not a direct OpenAI key)
BASE_URL=              # https://api.llmod.ai/v1
GPT_MODEL=             # RPRTHPB-gpt-5-mini
PINECONE_API_KEY=      # Pinecone API key
SUPABASE_URL=          # Supabase project URL
SUPABASE_KEY=          # Supabase anon or service role key
```

---

## Data ingestion

### Loading tweets

Tweets are loaded into Supabase and embedded into the `politics` Pinecone index using:

```bash
conda activate politician-tracker
python src/load_tweets_to_pinecone.py
```

### Loading news articles

News articles are loaded into Supabase and embedded into the `politics-news` Pinecone index using:

```bash
conda activate politician-tracker
python src/load_news_to_supabase_and_pinecone.py
```

### Scraping RSS feeds

The RSS extractor scrapes configured feeds and exports results to CSV and/or Supabase:

```bash
conda activate politician-tracker
python src/rss-extractor/scrape.py
python src/rss-extractor/export_csv.py
python src/rss-extractor/push_to_supabase.py
```

Feed configuration is in `src/rss-extractor/config/feeds.yaml`. Politicians are listed in `src/rss-extractor/config/politicians.yaml`.

---

## statement-processor local pipeline

The `statement-processor` pipeline runs entirely offline using a local SQLite
database. No API keys or external services are required for any of these steps.

### 1. Initialise the local database

```bash
cd src/statement-processor
python scripts/init_local_db.py
```

Creates `data/political_dossier.db` with tables: `news_articles`, `stance_records`,
`stance_relations`.

### 2. Import news articles

Place a `news_articles.csv` export at `src/statement-processor/data/news_articles.csv`,
then:

```bash
python scripts/import_news_articles_csv.py
```

### 3. Select candidate articles

```bash
python scripts/select_candidate_articles.py --politicians Trump Biden
```

Common options:

```bash
# Adjust minimum score (default: 1)
python scripts/select_candidate_articles.py --min-score 3

# Limit results
python scripts/select_candidate_articles.py --max-results 50

# Filter by date range
python scripts/select_candidate_articles.py --date-from 2024-01-01 --date-to 2024-12-31

# Save doc_ids to a file for downstream extraction
python scripts/select_candidate_articles.py --politicians Trump --output /tmp/trump_candidates.txt
```

### 4. Run the test suite

```bash
cd src/statement-processor
pytest tests/ -v
```

For schema change guidance, see `docs/migrations.md`.  
For the extraction contract, see `src/statement-processor/docs/stance_extraction_contract.md`.

---

## Background pipeline (System A) — PLANNED

The background pipeline is not yet implemented. When complete, it will be triggered by a scheduled cron job via:

```bash
python src/orchestrator.py  # planned — does not exist yet
```

Expected pipeline: ingestion → topic extraction → contradiction detection → page building.

Progress is logged to the `agent_runs` Supabase table.

---

## Frontend

### Development

```bash
cd frontend
npm run dev
```

Runs on `http://localhost:5173` with Vite's dev server. API calls proxy to `http://localhost:5000`.

### Production build

```bash
cd frontend
npm run build
```

The built files go to `frontend/dist/`. Flask is configured to serve static files from `frontend/dist/` in production.

---

## Deployment

The application targets **Render** for hosting. Deployment configuration is not yet finalised (Phase 5).

---

## Monitoring

The `agent_runs` Supabase table records each background pipeline execution: agent name, status, records processed, errors, and timestamps. Useful for diagnosing pipeline failures once System A is implemented.

---

## Utility scripts (test/)

| Script | Purpose |
|---|---|
| `test/check_all_indexes.py` | Inspect Pinecone index statistics |
| `test/inspect_supabase_db.py` | Query Supabase tables directly |
| `test/test_pinecone.py` | Verify Pinecone connectivity |
| `test/clean_politics_index.py` | Remove vectors from Pinecone (use with care) |
| `test/generate_prompt_examples.py` | Generate example prompts for manual testing |
