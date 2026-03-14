# Bulk Processing Pipeline (Option A)

This document explains how to run the high-throughput bulk processing pipeline
that reduces the cost and wall-clock time of processing large article corpora.

---

## Overview

The pipeline processes ~30,000 news articles in five sequential stages:

```
news_articles (SQLite)
  │
  ▼  Stage 1 – deterministic pre-filter (no LLM)
selected_articles.jsonl
  │
  ▼  Stage 2 – triage Batch API JSONL generation
batch_input.jsonl  ──→  [Submit to OpenAI Batch API]  ──→  batch_output.jsonl
  │
  ▼  Stage 3 – triage batch ingestion
positives.jsonl  (much smaller set)
  │
  ▼  Stage 4 – extraction Batch API JSONL generation
batch_input.jsonl  ──→  [Submit to OpenAI Batch API]  ──→  batch_output.jsonl
  │
  ▼  Stage 5 – extraction batch ingestion
candidate_events.jsonl  (raw, untrusted – for downstream validation)
```

Each stage can be run independently.  Artifacts from each stage are written
to a predictable local directory structure so the pipeline is auditable and
resumable.

---

## Prerequisites

### Environment

Set up the conda environment:

```bash
conda env create -f environment.yml
conda activate politician-tracker
```

### Environment variables

```bash
export OPENAI_API_KEY="sk-..."
```

### Local data

The pipeline reads articles from the local SQLite database:

```
statement-processor/data/political_dossier.db
```

Populate this database using the existing import workflow before running
the pipeline.  See `docs/local_testing.md` for import instructions.

---

## Artifact directory structure

All artifacts are written under:

```
statement-processor/data/batch_artifacts/
  triage/
    <run-id>/
      selected_articles.jsonl    – articles after deterministic filter
      batch_input.jsonl          – triage Batch API request file
      batch_output.jsonl         – completed triage output (user-placed)
      triage_results.jsonl       – all classified triage decisions
      positives.jsonl            – doc_ids that advance to extraction
      negatives.jsonl            – doc_ids that did not advance
      retry_candidates.jsonl     – failed + parse errors for resubmission
      summary.json               – stage summary counts
      prepare_summary.json       – batch preparation summary
  extraction/
    <run-id>/
      articles_for_extraction.jsonl  – triage-positive articles
      batch_input.jsonl              – extraction Batch API request file
      batch_output.jsonl             – completed extraction output (user-placed)
      raw_outputs.jsonl              – raw model response metadata
      candidate_events.jsonl         – parsed events (UNTRUSTED – raw candidates)
      failures.jsonl                 – request-level failures
      parse_errors.jsonl             – parse-error doc_ids
      summary.json                   – stage summary counts
```

---

## Step-by-step local execution

### Stage 1 + 2 – deterministic filter + triage batch preparation

```bash
cd statement-processor

python scripts/prepare_triage_batch.py \
    --politicians Trump Biden \
    --min-score 1 \
    --run-id run-001
```

Options:
- `--politicians` – which politicians to target (default: `Trump Biden`)
- `--min-score` – minimum selection score (default: `1`)
- `--max-results` – cap on articles (default: no limit)
- `--date-from` / `--date-to` – optional date range (ISO-8601)
- `--triage-model` – triage LLM model (default: `gpt-4o-mini`)
- `--triage-max-chars` – max article chars for triage prompt (default: `2000`)
- `--batch-size` – max requests per Batch API file (default: `10000`)
- `--db-path` – path to SQLite database
- `--run-id` – run identifier (auto-generated if omitted)

Output: `data/batch_artifacts/triage/run-001/batch_input.jsonl`

You can inspect the selection count in `summary.json` before submitting.

---

### Submitting the triage batch to OpenAI

Use the [OpenAI Batch API](https://platform.openai.com/docs/guides/batch)
to submit the generated `batch_input.jsonl` file.

```python
from openai import OpenAI

client = OpenAI()

# Upload the file
with open("data/batch_artifacts/triage/run-001/batch_input.jsonl", "rb") as f:
    file_obj = client.files.create(file=f, purpose="batch")

# Create the batch
batch = client.batches.create(
    input_file_id=file_obj.id,
    endpoint="/v1/chat/completions",
    completion_window="24h",
)
print(f"Batch ID: {batch.id}")

# Poll until complete, then download output
import time
while True:
    b = client.batches.retrieve(batch.id)
    print(f"Status: {b.status}")
    if b.status == "completed":
        content = client.files.content(b.output_file_id)
        with open("data/batch_artifacts/triage/run-001/batch_output.jsonl", "wb") as out:
            out.write(content.content)
        break
    if b.status in ("failed", "cancelled", "expired"):
        print(f"Batch failed: {b}")
        break
    time.sleep(60)
```

---

### Stage 3 – triage batch ingestion

Once `batch_output.jsonl` is present in the run directory:

```bash
python scripts/ingest_triage_batch.py \
    --run-dir data/batch_artifacts/triage/run-001
```

Output: classified results in the run directory, including `positives.jsonl`
with only the articles that advance to full extraction.

Check `summary.json` to verify how many articles were filtered out.

---

### Stage 4 – extraction batch preparation

```bash
python scripts/prepare_extraction_batch.py \
    --triage-run-dir data/batch_artifacts/triage/run-001 \
    --extraction-model gpt-4o-mini \
    --run-id extraction-run-001
```

Options:
- `--triage-run-dir` – path to the completed triage run directory
- `--extraction-model` – model for full extraction (default: `gpt-4o-mini`)
- `--max-chunk-chars` – max chars per article chunk (default: `6000`)
- `--db-path` – path to SQLite database
- `--run-id` – extraction run identifier

Output: `data/batch_artifacts/extraction/extraction-run-001/batch_input.jsonl`

Only triage-positive articles are included.

---

### Submit the extraction batch

Same approach as the triage batch submission above, using the extraction
run directory.

---

### Stage 5 – extraction batch ingestion

```bash
python scripts/ingest_extraction_batch.py \
    --run-dir data/batch_artifacts/extraction/extraction-run-001 \
    --model gpt-4o-mini
```

Output: `candidate_events.jsonl` containing raw, untrusted extraction
candidates.  These are **not** final validated stance records.  A future
validation stage is required before they can be written to `stance_records`.

---

## Verifying throughput reduction

After running the pipeline, compare counts:

```bash
# Total articles in database
sqlite3 data/political_dossier.db "SELECT COUNT(*) FROM news_articles;"

# Articles after deterministic filter
wc -l data/batch_artifacts/triage/run-001/selected_articles.jsonl

# Articles after triage
wc -l data/batch_artifacts/triage/run-001/positives.jsonl

# Candidate events from extraction
wc -l data/batch_artifacts/extraction/extraction-run-001/candidate_events.jsonl
```

The deterministic filter should eliminate most clearly irrelevant articles,
and triage should further reduce the set before the expensive extraction step.

---

## Running individual stages programmatically

You can also use the pipeline modules directly in Python:

```python
from pathlib import Path
from pipeline.bulk_option_a import BulkPipelineConfig, run_select, run_prepare_triage
from pipeline.artifacts import resolve_run_dir
from triage.models import TriageConfig

config = BulkPipelineConfig(
    politicians=["Trump", "Biden"],
    min_score=1,
    triage_config=TriageConfig(model_name="gpt-4o-mini", max_article_chars=2000),
)

run_dir = resolve_run_dir("data/batch_artifacts/triage", run_id="my-run")

# Stage 1 + 2
selected = run_select(config, run_dir)
paths = run_prepare_triage(selected, config, run_dir)

# Stage 3 (after batch output is available)
from pipeline.bulk_option_a import run_ingest_triage
triage_result = run_ingest_triage(run_dir)
print(triage_result.summary())

# Stage 4
from pipeline.bulk_option_a import run_prepare_extraction
ext_run_dir = resolve_run_dir("data/batch_artifacts/extraction")
paths = run_prepare_extraction(triage_result, config, ext_run_dir)

# Stage 5 (after extraction batch output is available)
from pipeline.bulk_option_a import run_ingest_extraction
result = run_ingest_extraction(ext_run_dir)
print(result.summary())
```

---

## Running end-to-end tests locally

Because the agent development environment does not contain the real dataset,
the in-repo tests use fixtures and mocks.  To run these:

```bash
cd statement-processor
pytest tests/test_bulk_pipeline.py -v
```

To run an end-to-end test on the machine that has the real dataset:

1. Follow the step-by-step instructions above.
2. After Stage 3 (triage ingestion), confirm that `positives.jsonl` is much
   smaller than `selected_articles.jsonl`.
3. After Stage 5 (extraction ingestion), inspect `candidate_events.jsonl` to
   confirm extraction produced meaningful events.

---

## Handling failures and retries

The pipeline is designed to be resumable:

- Each stage writes artifacts before the next stage begins.
- `retry_candidates.jsonl` in the triage run directory lists articles that
  failed or had parse errors and should be resubmitted.
- Rerunning any ingestion script on the same output file is idempotent.
- If a batch file is too large for the Batch API, use `--batch-size` to
  split into multiple files.

---

## Module reference

| Module | Purpose |
|--------|---------|
| `src/triage/models.py` | Typed data models for the triage stage |
| `src/triage/prompt.py` | Triage classifier prompt |
| `src/triage/batch_requests.py` | Generate triage Batch API JSONL |
| `src/triage/batch_ingest.py` | Ingest completed triage batch output |
| `src/extraction/batch_requests.py` | Generate extraction Batch API JSONL |
| `src/extraction/batch_ingest.py` | Ingest completed extraction batch output |
| `src/pipeline/artifacts.py` | Local artifact management |
| `src/pipeline/bulk_option_a.py` | Pipeline stage orchestration |
| `scripts/prepare_triage_batch.py` | CLI: Stages 1+2 |
| `scripts/ingest_triage_batch.py` | CLI: Stage 3 |
| `scripts/prepare_extraction_batch.py` | CLI: Stage 4 |
| `scripts/ingest_extraction_batch.py` | CLI: Stage 5 |
