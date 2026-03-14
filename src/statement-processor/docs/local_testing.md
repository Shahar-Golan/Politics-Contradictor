# Local Testing: Sub-issues 1–4 End-to-End Workflow

This document describes how to run the **complete local pipeline** for
Sub-issues 1–4 on the machine that has the real `news_articles` data.

> **Required:** The machine must have the real `news_articles` CSV export
> from Supabase (or another source).  The automated tests in `tests/` use
> fixture data and can be run anywhere without real data.

---

## Prerequisites

1. **Clone the repository.**

2. **Create the Conda environment** from the repository root:

   ```bash
   conda env create -f environment.yml
   conda activate politician-tracker
   ```

3. **Obtain a copy of the `news_articles` CSV export** and place it at:

   ```
   statement-processor/data/news_articles.csv
   ```

4. **Set your OpenAI API key** in a `.env` file at the repository root, or
   in your shell environment:

   ```bash
   export OPENAI_API_KEY="sk-..."
   ```

   The extractor reads this key automatically.

---

## Step 1 — Initialise the local database (Sub-issue 1)

```bash
# From the statement-processor/ directory:
python scripts/init_local_db.py
```

This creates `data/political_dossier.db` with three tables:
`news_articles`, `stance_records`, and `stance_relations`.

Verify:

```bash
python scripts/init_local_db.py --verify
```

---

## Step 2 — Import the news_articles CSV (Sub-issue 1)

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

---

## Step 3 — Run the article selector (Sub-issues 2–3)

Select eligible articles and save their `doc_id`s to a file:

```bash
python scripts/select_candidate_articles.py \
    --politicians Trump Biden \
    --min-score 2 \
    --max-results 20 \
    --output /tmp/candidate_ids.txt
```

Inspect the output:

```bash
cat /tmp/candidate_ids.txt
```

Expected: one `doc_id` per line for the highest-scoring eligible articles.

---

## Step 4 — Run the LLM stance extractor (Sub-issue 4)

Run extraction on the selected candidates:

```bash
python scripts/run_extractor.py \
    --doc-ids-file /tmp/candidate_ids.txt \
    --model gpt-4o-mini \
    --debug-log data/debug/extraction_debug.jsonl
```

The script prints a per-article summary:

```
doc_id                                   chunks  failed  events
--------------------------------------------------------------
article-trump-immigration-001                1       0       3
article-biden-healthcare-002                 1       0       2
article-economy-003                          2       0       1
...
--------------------------------------------------------------
TOTAL                                               0       6
```

### Trying a single article first

Run on just one `doc_id` to verify the pipeline is working:

```bash
python scripts/run_extractor.py \
    --doc-ids <your_doc_id_here> \
    --model gpt-4o-mini \
    --debug-log data/debug/extraction_debug.jsonl
```

---

## Step 5 — Inspect intermediate outputs

### View the debug JSONL log

Each line of the debug log is one JSON object containing:
- `doc_id`, `chunk_index`, `chunk_total`
- `model_name`, `extraction_timestamp`
- `raw_response` (exact model output)
- `parsed_json` (null on failure)
- `parse_error` (null on success)
- `attempt_number`

```bash
# View first 3 records (pretty-printed):
head -3 data/debug/extraction_debug.jsonl | python3 -m json.tool
```

### Check for parse failures

```bash
python3 -c "
import json, sys
with open('data/debug/extraction_debug.jsonl') as f:
    for line in f:
        r = json.loads(line)
        if r['parse_error']:
            print(r['doc_id'], r['chunk_index'], r['parse_error'])
"
```

---

## Step 6 — Verify candidate outputs

The extractor produces **untrusted candidate stance events** – they are
not yet written to any final validated table.

To inspect the candidate events programmatically:

```python
import sys
sys.path.insert(0, "src")

from extraction.extractor import extract_articles, load_articles_from_db
from extraction.models import ExtractionConfig

articles = load_articles_from_db(["<your_doc_id>"])
config = ExtractionConfig(
    model_name="gpt-4o-mini",
    debug_log_path="data/debug/extraction_debug.jsonl",
)

results = extract_articles(articles, config=config)

for result in results:
    print(f"\n{result.doc_id}: {result.event_count} events")
    for event in result.candidate_events:
        print(f"  - {event.politician} | {event.topic} | {event.stance_direction}")
        print(f"    {event.normalized_proposition}")
```

---

## Expected outcomes

After running Sub-issues 1–4 locally, you should be able to verify:

| Check | Expected result |
|---|---|
| `news_articles` table row count | Matches your CSV row count |
| Article selector output | A list of `doc_id`s with scores ≥ `min_score` |
| Extractor per-article events | 0-to-many candidate stance events per article |
| Debug JSONL log | One entry per chunk, with `raw_response` visible |
| No write to final tables | `stance_records` remains empty (candidates are untrusted) |

---

## Running the automated test suite

The automated tests use fixture data and mocks – no real data or API key
is needed:

```bash
# From the statement-processor/ directory:
pytest tests/ -v
```

All 150 tests should pass.

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `OPENAI_API_KEY` not set | Export the key in your shell or create a `.env` file |
| `FileNotFoundError: data/political_dossier.db` | Run `python scripts/init_local_db.py` first |
| `doc_id not found in database` | Run `import_news_articles_csv.py` first |
| Parse errors in debug log | Check `parse_error` field; retry with `--max-retries 3` |
| All chunks fail with timeout | Check your network connection and API key |
