# statement-processor – Local Schema & Ingestion Bootstrap

This directory contains the local-first database foundation for the
**dossier extraction pipeline**.  It lets a developer work with
`news_articles` data entirely offline, using a local SQLite database,
before any integration with Supabase/Postgres is required.

---

## Directory layout

```
statement-processor/
├── data/                               # Local data directory (git-tracked skeleton only)
│   └── .gitkeep                        # Placeholder – place CSV exports here
├── docs/
│   ├── stance_extraction_contract.md  # Extraction contract specification (Sub-issue 2)
│   └── local_testing.md               # End-to-end local test instructions (Sub-issues 1–4)
├── prompts/
│   └── stance_extraction_prompt.md    # Checked-in LLM prompt contract (Sub-issue 2)
├── schemas/
│   └── stance_extraction.schema.json  # JSON schema for extraction output (Sub-issue 2)
├── scripts/                            # Developer-facing entry points
│   ├── init_local_db.py                # Create/update the SQLite database
│   ├── import_news_articles_csv.py     # Import a news_articles CSV into SQLite
│   ├── select_candidate_articles.py   # Run deterministic article selection
│   └── run_extractor.py               # Run LLM stance extractor on candidate articles
├── src/
│   ├── contracts/
│   │   ├── vocab.py                    # Controlled vocabularies (Python)
│   │   └── vocab.json                  # Controlled vocabularies (JSON)
│   ├── db/
│   │   ├── __init__.py
│   │   ├── schema.sql                  # Canonical SQL schema (single source of truth)
│   │   ├── sqlite_utils.py             # Low-level SQLite helpers
│   │   ├── init_db.py                  # Schema bootstrap logic
│   │   └── import_news_articles.py     # CSV → SQLite ingestion logic
│   ├── extraction/
│   │   ├── __init__.py                 # Public API re-exports
│   │   ├── models.py                   # Typed data models (ArticleInput, ExtractionResult, …)
│   │   ├── prompt_loader.py            # Load and render the checked-in prompt contract
│   │   ├── chunking.py                 # Article chunking for long-text handling
│   │   ├── client.py                   # LLM provider wrapper (OpenAI)
│   │   ├── debug_logger.py             # JSONL debug/intermediate output logger
│   │   └── extractor.py               # Main extraction orchestration
│   └── selection/
│       ├── __init__.py                 # Public API re-exports
│       ├── keywords.py                 # Configurable keyword lists & politician aliases
│       ├── models.py                   # Typed data models (ScoredArticle, SelectionConfig, …)
│       ├── scoring.py                  # Rule-based article scoring logic
│       └── article_selector.py        # Main SQLite-backed selection function
├── tests/
│   ├── conftest.py
│   ├── fixtures/
│   │   ├── valid/                      # Valid extraction fixture JSON files
│   │   └── invalid/                    # Invalid fixture files (malformed JSON, etc.)
│   ├── test_db_bootstrap.py           # Pytest test suite – DB bootstrap
│   ├── test_article_selection.py      # Pytest test suite – article selection
│   ├── test_contract.py               # Pytest test suite – extraction contract
│   └── test_extractor_fixtures.py     # Pytest test suite – LLM extractor (mocked)
└── README.md                          # This file
```

---

## Prerequisites

Create and activate the project Conda environment (defined in the
repository root):

```bash
conda env create -f environment.yml
conda activate politician-tracker
```

SQLite is part of Python's standard library, so no extra packages are
needed for this module.

---

## Local developer workflow

### 1. Initialise the database

Run this once (or any time you want to reset / re-apply the schema):

```bash
# From the statement-processor directory:
python scripts/init_local_db.py
```

This creates `data/political_dossier.db` and creates the three tables:

| Table | Purpose |
|---|---|
| `news_articles` | Mirror of the Supabase `news_articles` table (local copy) |
| `stance_records` | Extraction output – one row per detected political stance |
| `stance_relations` | Pairwise relations (e.g. contradiction) between stance records |

You can point at a different file with `--db-path`:

```bash
python scripts/init_local_db.py --db-path /tmp/my_test.db
```

---

### 2. Place the CSV export in the data folder

Export `news_articles` from Supabase (or any source) and save it as:

```
statement-processor/data/news_articles.csv
```

The CSV must include at minimum a `doc_id` column.  The expected column
set is:

```
id, doc_id, title, text, date, media_name, media_type,
source_platform, state, city, link, speakers_mentioned, created_at
```

`speakers_mentioned` may be a JSON array string (`["Alice","Bob"]`) or a
plain comma-separated string (`Alice, Bob`) – both are accepted and
normalised to a JSON array string in SQLite.

---

### 3. Import the CSV

```bash
python scripts/import_news_articles_csv.py
```

Or with explicit paths:

```bash
python scripts/import_news_articles_csv.py \
    --csv data/news_articles.csv \
    --db-path data/political_dossier.db
```

The script prints a summary:

```
[import_csv] Source    : .../data/news_articles.csv
[import_csv] Target    : .../data/political_dossier.db
[import_csv] Attempted : 1500
[import_csv] Inserted  : 1498
[import_csv] Skipped   : 2 (duplicate doc_id)
```

Re-running the import is safe – duplicate `doc_id` rows are silently
skipped (`INSERT OR IGNORE` semantics).

---

### 4. Verify the database

Open the database with the SQLite CLI or any SQLite browser:

```bash
sqlite3 data/political_dossier.db
```

Useful verification queries:

```sql
-- List all tables
SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;

-- Row counts
SELECT COUNT(*) FROM news_articles;
SELECT COUNT(*) FROM stance_records;
SELECT COUNT(*) FROM stance_relations;

-- Preview rows
SELECT id, doc_id, title, date FROM news_articles LIMIT 5;
```

---

## Step 4 – Run the article selector

After importing your data, you can run the deterministic article selector to
identify which articles are likely to contain meaningful politician stance content.

### Quick start (default: Trump and Biden)

```bash
# From the statement-processor directory:
python scripts/select_candidate_articles.py
```

### Select for a specific politician

```bash
python scripts/select_candidate_articles.py --politicians Trump
python scripts/select_candidate_articles.py --politicians Biden
python scripts/select_candidate_articles.py --politicians Trump Biden
```

### Adjust the minimum eligibility score

```bash
# Only return articles with score >= 3 (more aggressive filtering):
python scripts/select_candidate_articles.py --min-score 3

# Return all articles that mention a politician (score >= 0):
python scripts/select_candidate_articles.py --min-score 0
```

### Limit the number of results

```bash
python scripts/select_candidate_articles.py --max-results 50
```

### Filter by date range

```bash
python scripts/select_candidate_articles.py \
    --date-from 2024-01-01 \
    --date-to 2024-12-31
```

### Save eligible doc_ids for downstream extraction

```bash
python scripts/select_candidate_articles.py \
    --politicians Trump \
    --min-score 2 \
    --output /tmp/trump_candidates.txt
```

The output file contains one `doc_id` per line.

### Show ineligible articles too

```bash
python scripts/select_candidate_articles.py --show-ineligible
```

---

## Article selection scoring

The selector uses deterministic, rule-based scoring.  Each rule contributes a
fixed integer weight.  No LLM or external API is used.

| Rule | Weight | Signal |
|---|---|---|
| `politician_in_speakers` | +3 | Politician in `speakers_mentioned` |
| `reporting_verb_in_title` | +2 | Title contains a reporting/action verb |
| `policy_topic_in_title` | +2 | Title contains a policy keyword |
| `quote_marker_in_text` | +2 | Text contains a direct-quote marker |
| `policy_topic_in_text` | +1 | Text contains a policy keyword |
| `politician_in_title` | +1 | Politician alias appears in title |
| `text_length_ok` | +1 | Text meets minimum length (≥150 chars) |
| `low_priority_signal_in_title` | −2 | Title contains a low-priority signal (e.g. "poll") |
| `low_priority_signal_in_text` | −1 | Text contains a low-priority signal |
| `text_too_short` | −2 | Text is present but below minimum length |

An article is **eligible** when its total score ≥ `min_score` (default: 1).

### Extending the selector

All keyword lists and politician aliases live in
`src/selection/keywords.py`:

- Add new reporting verbs to `REPORTING_VERBS`.
- Add new policy keywords to `POLICY_TOPICS`.
- Add a new politician by adding an entry to `POLITICIAN_ALIASES`:
  ```python
  "Harris": frozenset({"harris", "kamala harris", "vice president harris", "harris's"}),
  ```

---

## Running the tests

```bash
# From the statement-processor directory:
pytest tests/ -v
```

Or from the repository root:

```bash
pytest src/statement-processor/tests/ -v
```

The test suite covers:

- database file creation
- table creation (all three tables)
- successful CSV import
- `doc_id` uniqueness / duplicate handling
- row count verification
- `speakers_mentioned` normalisation (JSON array, CSV string, empty)
- article scoring rule matching (all rules)
- politician alias detection (Trump, Biden)
- end-to-end selection against a SQLite fixture database
- determinism (same input → same output)
- `SelectionConfig` options (min_score, max_results, date range)
- error handling (unknown politician, missing database)
- extractor invocation over fixture/sample articles (mocked LLM)
- zero-event, multi-event, and malformed JSON extraction cases
- retry and failure logging behaviour
- provenance preservation across chunking
- debug logger output (JSONL)

---

## Step 5 – Run the LLM stance extractor

After selecting candidate articles, run the LLM-based extractor to
produce candidate stance events.

### Set your OpenAI API key

```bash
export OPENAI_API_KEY="sk-..."
```

### Quick start — extract from a doc_ids file

```bash
python scripts/run_extractor.py \
    --doc-ids-file /tmp/candidate_ids.txt \
    --model gpt-4o-mini \
    --debug-log data/debug/extraction_debug.jsonl
```

### Extract from explicit doc_ids

```bash
python scripts/run_extractor.py \
    --doc-ids article-001 article-002 article-003 \
    --model gpt-4o-mini
```

### Use a different model

```bash
python scripts/run_extractor.py \
    --doc-ids-file /tmp/candidate_ids.txt \
    --model gpt-4o
```

### Adjust chunking and retry behaviour

```bash
python scripts/run_extractor.py \
    --doc-ids-file /tmp/candidate_ids.txt \
    --max-chunk-chars 4000 \
    --max-retries 3
```

### Pipeline output

The script prints a per-article summary to stdout:

```
doc_id                                   chunks  failed  events
--------------------------------------------------------------
article-trump-immigration-001                1       0       3
article-biden-healthcare-002                 1       0       2
--------------------------------------------------------------
TOTAL                                               0       5
```

Candidate events are **untrusted** and are **not** written to the final
`stance_records` table.  They must pass a later validation step.

### Inspecting debug output

```bash
# View first record (pretty-printed):
head -1 data/debug/extraction_debug.jsonl | python3 -m json.tool
```

Each debug record contains the raw model response, parsed JSON (or null),
parse error (or null), model name, timestamp, and chunk metadata.

---

## Complete local workflow (Sub-issues 1–4)

For full end-to-end instructions including environment setup, database
initialisation, CSV import, article selection, and extraction, see:

> **[`docs/local_testing.md`](docs/local_testing.md)**

This document is especially important if you are testing with the real
`news_articles` data on your local machine.

---

## Extractor architecture

The extraction layer lives in `src/extraction/`:

| Module | Purpose |
|---|---|
| `models.py` | Typed dataclasses: `ArticleInput`, `ExtractionConfig`, `ExtractionResult`, `CandidateStanceEvent`, `RawExtractionOutput`, `ChunkInput` |
| `prompt_loader.py` | Loads and renders the checked-in prompt contract from `prompts/stance_extraction_prompt.md` |
| `chunking.py` | Splits long articles into bounded chunks (paragraph → sentence fallback) |
| `client.py` | OpenAI chat completions wrapper; isolates all provider code |
| `debug_logger.py` | Appends raw extraction outputs to a JSONL file |
| `extractor.py` | Orchestrates chunking → LLM calls → JSON parsing → provenance |

### Candidate vs. validated events

```
ArticleInput
    → chunk_article()
        → LLM (via LLMClient)
            → _parse_raw_response()
                → _build_candidate()
                    → CandidateStanceEvent  ← UNTRUSTED
                        → ExtractionResult
                            → [future validator]
                                → stance_records (final)
```

Candidate events are labelled as untrusted at every step.  The
`stance_records` table is only written by the future validation layer.

---

## Schema notes

### `speakers_mentioned` (TEXT)

The Postgres schema stores this as `TEXT[]` (an array).  In SQLite it is
stored as a **JSON array string**, e.g.:

```json
["Alice", "Bob"]
```

The ingestion code normalises comma-separated strings automatically.

### DATETIME columns

SQLite has no native `DATETIME` type.  All timestamp columns use
ISO-8601 text (e.g. `2025-01-15T12:00:00Z`).

### Auto-increment primary keys

All three tables use `INTEGER PRIMARY KEY AUTOINCREMENT` for `id`.

---

## Out of scope (for these sub-issues)

- Validation / normalization of extracted stance events
- Insertion of validated stance events into final `stance_records`
- Contradiction detection
- Dossier generation
- Supabase sync / production deployment
