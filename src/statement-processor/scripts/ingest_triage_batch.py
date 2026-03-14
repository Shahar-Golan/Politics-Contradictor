#!/usr/bin/env python3
"""
ingest_triage_batch.py
======================
CLI script to ingest a completed triage Batch API output file and classify
articles as triage-positive or triage-negative.

This script performs pipeline Stage 3:
  Stage 3: ingest completed triage batch output and classify results

Before running this script, you must:
1. Have run ``prepare_triage_batch.py`` to generate ``batch_input.jsonl``
2. Submitted ``batch_input.jsonl`` to the OpenAI Batch API
3. Downloaded the completed output and placed it as ``batch_output.jsonl``
   in the same run directory

Usage examples
--------------
Ingest triage results from a run directory:

    python scripts/ingest_triage_batch.py \\
        --run-dir data/batch_artifacts/triage/run-001

Use a custom output filename (if different from batch_output.jsonl):

    python scripts/ingest_triage_batch.py \\
        --run-dir data/batch_artifacts/triage/run-001 \\
        --output-file my_batch_output.jsonl

Output
------
The following artifacts are written to the run directory:
  triage_results.jsonl   – all classified triage decisions
  positives.jsonl        – doc_ids that advance to extraction
  negatives.jsonl        – doc_ids that did not advance
  retry_candidates.jsonl – failed + parse-error articles for re-submission
  summary.json           – stage summary counts

After running this script, the ``positives.jsonl`` file contains the doc_ids
ready for Stage 4.  Run ``prepare_extraction_batch.py`` next.
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

from pipeline.bulk_option_a import run_ingest_triage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s – %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ingest_triage_batch")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest a completed triage Batch API output file."
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

    logger.info("Ingesting triage batch from %s", run_dir)
    result = run_ingest_triage(run_dir, output_jsonl_name=args.output_file)

    summary = result.summary()
    print(f"\n✓ Triage ingestion complete.")
    print(f"  Total responses:   {summary['total']}")
    print(f"  Positives:         {summary['positives']}  → advance to extraction")
    print(f"  Negatives:         {summary['negatives']}  → skip")
    print(f"  Failed:            {summary['failed']}")
    print(f"  Parse errors:      {summary['parse_errors']}")
    print(f"  Retry candidates:  {summary['retry_candidates']}")
    print(f"\nArtifacts written to: {run_dir}")

    if summary["positives"] > 0:
        print(
            f"\nNext step: run the extraction batch preparation:\n"
            f"    python scripts/prepare_extraction_batch.py \\\n"
            f"        --triage-run-dir {run_dir}"
        )
    else:
        print("\nNo positive articles found.  Pipeline complete.")


if __name__ == "__main__":
    main()
