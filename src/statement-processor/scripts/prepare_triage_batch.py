#!/usr/bin/env python3
"""
prepare_triage_batch.py
=======================
CLI script to run the deterministic pre-filter and generate the triage
Batch API JSONL input file.

This script performs pipeline Stages 1 and 2:
  Stage 1: deterministic pre-filter (no LLM calls)
  Stage 2: generate triage Batch API JSONL from selected articles

The output is a ``batch_input.jsonl`` file ready for submission to the
OpenAI Batch API.

Usage examples
--------------
Generate a triage batch for Trump and Biden articles:

    python scripts/prepare_triage_batch.py \\
        --politicians Trump Biden \\
        --run-id run-001

Limit to 500 articles, minimum score 2:

    python scripts/prepare_triage_batch.py \\
        --politicians Trump \\
        --min-score 2 \\
        --max-results 500 \\
        --run-id run-trump-001

Use a date range:

    python scripts/prepare_triage_batch.py \\
        --politicians Trump Biden \\
        --date-from 2024-01-01 \\
        --date-to 2024-12-31 \\
        --run-id run-2024

Use a custom database path:

    python scripts/prepare_triage_batch.py \\
        --politicians Trump Biden \\
        --db-path /data/political_dossier.db \\
        --run-id run-001

Output
------
Artifacts are written under:
  data/batch_artifacts/triage/<run-id>/
    selected_articles.jsonl   – articles that passed the deterministic filter
    batch_input.jsonl         – triage Batch API request file
    summary.json              – selection stage summary
    prepare_summary.json      – triage preparation summary

After running this script, submit ``batch_input.jsonl`` to the OpenAI Batch
API and place the completed output as ``batch_output.jsonl`` in the same
directory.  Then run ``ingest_triage_batch.py`` to process the results.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# ── Add src/ to sys.path ──────────────────────────────────────────────────
_SRC_DIR = Path(__file__).parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from pipeline.artifacts import resolve_run_dir
from pipeline.bulk_option_a import BulkPipelineConfig, run_prepare_triage, run_select
from triage.models import TriageConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s – %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("prepare_triage_batch")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run deterministic pre-filter and generate triage Batch API JSONL."
    )
    parser.add_argument(
        "--politicians",
        nargs="+",
        default=["Trump", "Biden"],
        metavar="NAME",
        help="Canonical politician names to filter by (default: Trump Biden).",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=1,
        metavar="N",
        help="Minimum selection score (default: 1).",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=None,
        metavar="N",
        help="Maximum number of articles to select (default: no limit).",
    )
    parser.add_argument(
        "--date-from",
        default=None,
        metavar="YYYY-MM-DD",
        help="Select articles published on or after this date.",
    )
    parser.add_argument(
        "--date-to",
        default=None,
        metavar="YYYY-MM-DD",
        help="Select articles published on or before this date.",
    )
    parser.add_argument(
        "--triage-model",
        default="gpt-4o-mini",
        metavar="MODEL",
        help="Model to use for triage (default: gpt-4o-mini).",
    )
    parser.add_argument(
        "--triage-max-chars",
        type=int,
        default=2000,
        metavar="N",
        help="Maximum article characters to include in triage prompt (default: 2000).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10000,
        metavar="N",
        help="Maximum requests per Batch API file (default: 10000).",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        metavar="PATH",
        help="Path to the local SQLite database (default: data/political_dossier.db).",
    )
    parser.add_argument(
        "--artifacts-dir",
        default="data/batch_artifacts",
        metavar="DIR",
        help="Root directory for pipeline artifacts (default: data/batch_artifacts).",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        metavar="ID",
        help="Run identifier (default: auto-generated timestamp).",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    triage_config = TriageConfig(
        model_name=args.triage_model,
        max_article_chars=args.triage_max_chars,
        batch_size=args.batch_size,
    )
    pipeline_config = BulkPipelineConfig(
        politicians=args.politicians,
        min_score=args.min_score,
        max_results=args.max_results,
        date_from=args.date_from,
        date_to=args.date_to,
        triage_config=triage_config,
        db_path=args.db_path,
        artifacts_base_dir=args.artifacts_dir,
    )

    triage_base = Path(args.artifacts_dir) / "triage"
    run_dir = resolve_run_dir(triage_base, run_id=args.run_id)
    logger.info("Run directory: %s", run_dir)

    # Stage 1 – deterministic pre-filter.
    selected = run_select(pipeline_config, run_dir)
    if not selected:
        logger.warning("No articles passed the deterministic filter.  Exiting.")
        sys.exit(0)

    # Stage 2 – triage batch preparation.
    paths = run_prepare_triage(selected, pipeline_config, run_dir)

    print(f"\n✓ Selected {len(selected)} article(s) after deterministic filtering.")
    print(f"✓ Triage batch input written to:")
    for p in paths:
        print(f"    {p}")
    print(
        f"\nNext step: submit the batch input file(s) to the OpenAI Batch API,\n"
        f"then place the completed output as 'batch_output.jsonl' in:\n"
        f"    {run_dir}\n"
        f"and run:\n"
        f"    python scripts/ingest_triage_batch.py --run-dir {run_dir}"
    )


if __name__ == "__main__":
    main()
