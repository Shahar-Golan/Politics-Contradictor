#!/usr/bin/env python3
"""
ingest_extraction_batch.py
==========================
CLI script to ingest a completed full stance extraction Batch API output file
and store the raw candidate extraction results.

This script performs pipeline Stage 5:
  Stage 5: ingest completed extraction batch output, store raw candidates

Important: all extracted events are stored as **raw/intermediate candidates**.
They are NOT validated or persisted to the final ``stance_records`` table.
They require a later validation/normalisation step.

Before running this script, you must:
1. Have run ``prepare_extraction_batch.py`` to generate ``batch_input.jsonl``
2. Submitted ``batch_input.jsonl`` to the OpenAI Batch API
3. Downloaded the completed output and placed it as ``batch_output.jsonl``
   in the extraction run directory

Usage examples
--------------
Ingest extraction results from a run directory:

    python scripts/ingest_extraction_batch.py \\
        --run-dir data/batch_artifacts/extraction/run-001

Use a custom output filename:

    python scripts/ingest_extraction_batch.py \\
        --run-dir data/batch_artifacts/extraction/run-001 \\
        --output-file my_batch_output.jsonl

Specify the model name for provenance tracking:

    python scripts/ingest_extraction_batch.py \\
        --run-dir data/batch_artifacts/extraction/run-001 \\
        --model gpt-4o-mini

Output
------
The following artifacts are written to the run directory:
  raw_outputs.jsonl         – raw model response metadata (provenance)
  candidate_events.jsonl    – parsed stance events (UNTRUSTED – raw candidates)
  failures.jsonl            – request-level failures
  parse_errors.jsonl        – parse-error doc_ids
  summary.json              – stage summary counts

These outputs are NOT final.  They must be validated by a downstream
validation stage before being written to ``stance_records``.
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

from pipeline.bulk_option_a import run_ingest_extraction

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s – %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ingest_extraction_batch")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest a completed extraction Batch API output file."
    )
    parser.add_argument(
        "--run-dir",
        required=True,
        metavar="DIR",
        help="Run directory containing batch_input.jsonl and batch_output.jsonl.",
    )
    parser.add_argument(
        "--output-file",
        default="batch_output.jsonl",
        metavar="FILENAME",
        help="Name of the completed batch output file (default: batch_output.jsonl).",
    )
    parser.add_argument(
        "--model",
        default="unknown",
        metavar="MODEL",
        help="Model name to record in raw outputs (default: unknown).",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    run_dir = Path(args.run_dir).resolve()

    if not run_dir.exists():
        logger.error("Run directory not found: %s", run_dir)
        sys.exit(1)

    output_path = run_dir / args.output_file
    if not output_path.exists():
        logger.error(
            "Batch output file not found: %s\n"
            "Download the completed Batch API output and place it at this path.",
            output_path,
        )
        sys.exit(1)

    logger.info("Ingesting extraction batch from %s", run_dir)
    result = run_ingest_extraction(
        run_dir,
        output_jsonl_name=args.output_file,
        model_name=args.model,
    )

    summary = result.summary()
    print(f"\n✓ Extraction ingestion complete (raw/intermediate candidates – NOT validated).")
    print(f"  Total chunk responses: {summary['total_responses']}")
    print(f"  Candidate events:      {summary['candidate_events']}  (UNTRUSTED)")
    print(f"  Failed requests:       {summary['failed_requests']}")
    print(f"  Parse errors:          {summary['parse_errors']}")
    print(f"  Retry candidates:      {summary['retry_candidates']}")
    print(f"\nArtifacts written to: {run_dir}")
    print(
        "\nNOTE: candidate_events.jsonl contains raw, unvalidated extraction outputs.\n"
        "A future validation stage is required before these can be used as final stance records."
    )


if __name__ == "__main__":
    main()
