#!/usr/bin/env python3
"""
prepare_extraction_batch.py
===========================
CLI script to load triage-positive articles and generate the full stance
extraction Batch API JSONL input file.

This script performs pipeline Stage 4:
  Stage 4: generate full extraction Batch API JSONL for triage-positive articles

Only articles that were classified as positive by the triage stage are
included.  This is the key throughput optimisation: the expensive full
extraction model runs only on a small subset of the original corpus.

Before running this script, you must have:
1. Run ``prepare_triage_batch.py``
2. Submitted the triage batch and ingested results with ``ingest_triage_batch.py``
3. Confirmed that ``positives.jsonl`` is present in the triage run directory

Usage examples
--------------
Prepare an extraction batch from a triage run:

    python scripts/prepare_extraction_batch.py \\
        --triage-run-dir data/batch_artifacts/triage/run-001

Use a specific extraction model and run ID:

    python scripts/prepare_extraction_batch.py \\
        --triage-run-dir data/batch_artifacts/triage/run-001 \\
        --extraction-model gpt-4o \\
        --run-id extraction-run-001

Use a custom database path:

    python scripts/prepare_extraction_batch.py \\
        --triage-run-dir data/batch_artifacts/triage/run-001 \\
        --db-path /data/political_dossier.db

Output
------
Artifacts are written under:
  data/batch_artifacts/extraction/<run-id>/
    articles_for_extraction.jsonl  – triage-positive articles
    batch_input.jsonl              – extraction Batch API request file
    prepare_summary.json           – preparation summary

After running this script, submit ``batch_input.jsonl`` to the OpenAI Batch
API and place the completed output as ``batch_output.jsonl`` in the same
directory.  Then run ``ingest_extraction_batch.py``.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# ── Add src/ to sys.path ──────────────────────────────────────────────────
_SRC_DIR = Path(__file__).parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from pipeline.artifacts import resolve_run_dir
from pipeline.bulk_option_a import BulkPipelineConfig, run_prepare_extraction
from triage.batch_ingest import ingest_triage_batch_output
from triage.models import TriageConfig, TriageResult
from extraction.models import ExtractionConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s – %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("prepare_extraction_batch")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate extraction Batch API JSONL for triage-positive articles."
    )
    parser.add_argument(
        "--triage-run-dir",
        required=True,
        metavar="DIR",
        help="Path to the triage run directory containing positives.jsonl.",
    )
    parser.add_argument(
        "--extraction-model",
        default="gpt-4o-mini",
        metavar="MODEL",
        help="Model to use for extraction (default: gpt-4o-mini).",
    )
    parser.add_argument(
        "--max-chunk-chars",
        type=int,
        default=6000,
        metavar="N",
        help="Maximum characters per article chunk (default: 6000).",
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


def _load_positives_from_triage_dir(triage_run_dir: Path) -> list[TriageResult]:
    """Read positives from a completed triage run by re-ingesting the output.

    Parameters
    ----------
    triage_run_dir:
        Path to the triage run directory.

    Returns
    -------
    list[TriageResult]
        Triage-positive results.
    """
    output_path = triage_run_dir / "batch_output.jsonl"
    input_path = triage_run_dir / "batch_input.jsonl"

    if not output_path.exists():
        # Try to read positives.jsonl directly (simpler re-use path).
        positives_path = triage_run_dir / "positives.jsonl"
        if positives_path.exists():
            logger.info("Reading positives from %s", positives_path)
            from triage.models import TriageResult, TriageDecision
            results: list[TriageResult] = []
            with positives_path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    results.append(
                        TriageResult(
                            doc_id=data["doc_id"],
                            title=None,
                            link=None,
                            date=None,
                            matched_politician=None,
                            request_id=data.get("request_id", f"triage-{data['doc_id']}"),
                            decision=TriageDecision(
                                has_stance_statement=True,
                                has_policy_position=True,
                                has_politician_action=False,
                                has_contradiction_signal=False,
                                advance=True,
                            ),
                            raw_response=None,
                            parse_error=None,
                            failed=False,
                        )
                    )
            return results
        raise FileNotFoundError(
            f"Neither batch_output.jsonl nor positives.jsonl found in {triage_run_dir}"
        )

    ingestion = ingest_triage_batch_output(
        output_jsonl=output_path,
        input_jsonl=input_path if input_path.exists() else None,
    )
    return ingestion.positives


def main() -> None:
    args = _parse_args()
    triage_run_dir = Path(args.triage_run_dir).resolve()

    if not triage_run_dir.exists():
        logger.error("Triage run directory not found: %s", triage_run_dir)
        sys.exit(1)

    # Load triage positives.
    try:
        positives = _load_positives_from_triage_dir(triage_run_dir)
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        sys.exit(1)

    if not positives:
        logger.warning("No triage-positive articles found in %s.  Exiting.", triage_run_dir)
        sys.exit(0)

    logger.info("Loaded %d triage-positive articles.", len(positives))

    extraction_config = ExtractionConfig(
        model_name=args.extraction_model,
        max_chunk_chars=args.max_chunk_chars,
    )
    pipeline_config = BulkPipelineConfig(
        extraction_config=extraction_config,
        db_path=args.db_path,
        artifacts_base_dir=args.artifacts_dir,
    )

    extraction_base = Path(args.artifacts_dir) / "extraction"
    run_dir = resolve_run_dir(extraction_base, run_id=args.run_id)
    logger.info("Extraction run directory: %s", run_dir)

    from triage.batch_ingest import TriageBatchIngestionResult

    # Build a minimal TriageBatchIngestionResult containing only the positives.
    triage_result = TriageBatchIngestionResult(results=positives)

    paths = run_prepare_extraction(triage_result, pipeline_config, run_dir, db_path=args.db_path)

    print(f"\n✓ Loaded {len(positives)} triage-positive article(s).")
    print(f"✓ Extraction batch input written to:")
    for p in paths:
        print(f"    {p}")

    if paths:
        print(
            f"\nNext step: submit the batch input file(s) to the OpenAI Batch API,\n"
            f"then place the completed output as 'batch_output.jsonl' in:\n"
            f"    {run_dir}\n"
            f"and run:\n"
            f"    python scripts/ingest_extraction_batch.py --run-dir {run_dir}"
        )
    else:
        print("\nNo batch files generated (no articles to process).  Pipeline complete.")


if __name__ == "__main__":
    main()
