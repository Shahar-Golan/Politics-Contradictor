#!/usr/bin/env python3
"""
run_extractor.py
================
CLI script to run the LLM-based stance extractor against candidate articles
selected from the local SQLite ``news_articles`` table.

Usage examples
--------------
Extract from doc_ids listed in a file (one per line):

    python scripts/run_extractor.py --doc-ids-file /tmp/eligible_ids.txt

Extract directly by specifying doc_ids on the command line:

    python scripts/run_extractor.py --doc-ids art-001 art-002 art-003

Run the selector first and pipe straight into the extractor:

    python scripts/select_candidate_articles.py \\
        --politicians Trump --min-score 2 \\
        --output /tmp/trump_candidates.txt

    python scripts/run_extractor.py \\
        --doc-ids-file /tmp/trump_candidates.txt

Use a specific model and enable debug logging:

    python scripts/run_extractor.py \\
        --doc-ids-file /tmp/trump_candidates.txt \\
        --model gpt-4o \\
        --debug-log data/debug/extraction_debug.jsonl

Use a custom database path:

    python scripts/run_extractor.py \\
        --doc-ids-file /tmp/eligible_ids.txt \\
        --db-path /tmp/my_political_dossier.db

Output
------
The script prints a per-article summary to stdout.  Extracted candidate
events are treated as untrusted and are NOT written to final validated
tables.  Debug output is written to the JSONL log when ``--debug-log`` is
provided.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from tqdm.auto import tqdm

# ── Make src/ importable when the script is run from statement-processor/ ──
_SCRIPT_DIR = Path(__file__).resolve().parent
_SRC_DIR = _SCRIPT_DIR.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))


from extraction.extractor import extract_articles, load_articles_from_db
from extraction.models import ExtractionConfig

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
_log = logging.getLogger("run_extractor")


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run LLM-based stance extraction on candidate articles.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    id_group = parser.add_mutually_exclusive_group(required=True)
    id_group.add_argument(
        "--doc-ids",
        nargs="+",
        metavar="DOC_ID",
        help="One or more doc_id values to extract from.",
    )
    id_group.add_argument(
        "--doc-ids-file",
        metavar="PATH",
        help=(
            "Path to a text file containing one doc_id per line "
            "(output of select_candidate_articles.py --output)."
        ),
    )

    parser.add_argument(
        "--db-path",
        metavar="PATH",
        default=None,
        help="Path to the local SQLite database.  Defaults to data/political_dossier.db.",
    )
    parser.add_argument(
        "--model",
        metavar="MODEL",
        default="gpt-4o-mini",
        help="OpenAI model name to use (default: gpt-4o-mini).",
    )
    parser.add_argument(
        "--max-chunk-chars",
        type=int,
        default=6_000,
        metavar="N",
        help=(
            "Maximum characters per article chunk (default: 6000). "
            "Articles longer than this are split before sending to the LLM."
        ),
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=2,
        metavar="N",
        help="Maximum LLM call attempts per chunk (default: 2).",
    )
    parser.add_argument(
        "--debug-log",
        metavar="PATH",
        default=None,
        help=(
            "Path to write JSONL debug log of raw model responses. "
            "If omitted, no debug file is written."
        ),
    )

    return parser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_doc_ids(args: argparse.Namespace) -> list[str]:
    """Return the list of doc_ids to process from CLI arguments."""
    if args.doc_ids:
        return list(args.doc_ids)

    path = Path(args.doc_ids_file)
    if not path.exists():
        _log.error("doc_ids file not found: %s", path)
        sys.exit(1)

    lines = path.read_text(encoding="utf-8").splitlines()
    doc_ids = [
        line.strip()
        for line in tqdm(lines, desc="Reading doc_ids", unit="line", leave=False)
        if line.strip()
    ]
    if not doc_ids:
        _log.error("doc_ids file is empty: %s", path)
        sys.exit(1)

    return doc_ids


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    doc_ids = _load_doc_ids(args)
    _log.info("Loaded %d doc_id(s) to process.", len(doc_ids))

    # Load articles from SQLite.
    _log.info("Loading articles from database…")
    articles = load_articles_from_db(doc_ids, db_path=args.db_path)
    if not articles:
        _log.error("No articles found for the given doc_ids.")
        sys.exit(1)

    _log.info("Loaded %d article(s).", len(articles))

    # Build extraction config.
    config = ExtractionConfig(
        model_name=args.model,
        max_chunk_chars=args.max_chunk_chars,
        max_retries=args.max_retries,
        debug_log_path=args.debug_log,
    )

    if args.debug_log:
        _log.info("Debug log → %s", args.debug_log)

    # Run extraction.
    _log.info("Starting extraction with model=%r …", config.model_name)
    with tqdm(total=1, desc="Running extraction", unit="run") as progress:
        results = extract_articles(articles, config=config)
        progress.update(1)

    # Print summary.
    total_events = 0
    total_failed = 0
    print()
    print(f"{'doc_id':<40} {'chunks':>6} {'failed':>6} {'events':>6}")
    print("-" * 62)
    for result in tqdm(results, desc="Rendering summary", unit="article", leave=False):
        total_events += result.event_count
        total_failed += result.failed_chunks
        print(
            f"{result.doc_id:<40} "
            f"{result.total_chunks:>6} "
            f"{result.failed_chunks:>6} "
            f"{result.event_count:>6}"
        )
    print("-" * 62)
    print(
        f"{'TOTAL':<40} "
        f"{'':>6} "
        f"{total_failed:>6} "
        f"{total_events:>6}"
    )
    print()
    _log.info(
        "Extraction complete. %d article(s), %d candidate event(s), "
        "%d chunk(s) failed.",
        len(results),
        total_events,
        total_failed,
    )

    if total_events > 0:
        _log.info(
            "Candidate events are UNTRUSTED and have NOT been written to "
            "any final validated table.  Run the validator to review them."
        )


if __name__ == "__main__":
    main()
