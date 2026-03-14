#!/usr/bin/env python3
"""
select_candidate_articles.py
============================
CLI script to run deterministic article selection against the local
SQLite ``news_articles`` table.

Usage examples
--------------
Select eligible articles for Trump and Biden (default):

    python scripts/select_candidate_articles.py

Select articles for Trump only, minimum score 3, at most 25 results:

    python scripts/select_candidate_articles.py \\
        --politicians Trump \\
        --min-score 3 \\
        --max-results 25

Filter by date range:

    python scripts/select_candidate_articles.py \\
        --politicians Trump Biden \\
        --date-from 2024-01-01 \\
        --date-to 2024-12-31

Use a custom database path:

    python scripts/select_candidate_articles.py \\
        --db-path /tmp/my_political_dossier.db

Write eligible doc_ids to a file (one per line):

    python scripts/select_candidate_articles.py --output /tmp/eligible_ids.txt

Output
------
The script prints a human-readable summary table to stdout and optionally
writes a list of eligible ``doc_id`` values (one per line) to a file.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make sure the src package directory is on the path when the script is run
# directly from the statement-processor/ root.
_SCRIPT_DIR = Path(__file__).resolve().parent
_SRC_DIR = _SCRIPT_DIR.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from db.sqlite_utils import get_default_db_path
from selection.article_selector import select_candidate_articles
from selection.keywords import POLITICIAN_ALIASES
from selection.models import SelectionConfig, ScoredArticle


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _format_rules(rules: tuple[str, ...]) -> str:
    return ", ".join(rules) if rules else "(none)"


def _print_summary(article: ScoredArticle, index: int) -> None:
    eligible_marker = "✓" if article.is_eligible else "✗"
    title_display = (article.title or "(no title)")[:80]
    print(
        f"  [{index:>4}] {eligible_marker} score={article.score:>3}  "
        f"politician={article.matched_politician:<8}  "
        f"doc_id={article.doc_id}"
    )
    print(f"         title  : {title_display}")
    print(f"         rules  : {_format_rules(article.matched_rules)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    available_politicians = sorted(POLITICIAN_ALIASES.keys())
    default_db = get_default_db_path()

    parser = argparse.ArgumentParser(
        description=(
            "Select candidate articles for stance extraction from the local "
            "SQLite news_articles table."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Available politicians: " + ", ".join(available_politicians) + "\n\n"
            "The selector is deterministic: re-running on the same database\n"
            "produces the same ranked list of candidate articles."
        ),
    )
    parser.add_argument(
        "--politicians",
        nargs="+",
        default=["Trump", "Biden"],
        metavar="NAME",
        help=(
            "One or more canonical politician names to filter by. "
            f"Available: {available_politicians}. "
            "Default: Trump Biden"
        ),
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=1,
        metavar="N",
        help=(
            "Minimum score for an article to be eligible. "
            "Articles below this threshold are shown but flagged as ineligible. "
            "Default: 1"
        ),
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=None,
        metavar="N",
        help="Maximum number of eligible articles to return. Default: no limit.",
    )
    parser.add_argument(
        "--date-from",
        default=None,
        metavar="YYYY-MM-DD",
        help="Include only articles published on or after this date.",
    )
    parser.add_argument(
        "--date-to",
        default=None,
        metavar="YYYY-MM-DD",
        help="Include only articles published on or before this date.",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        metavar="PATH",
        help=f"Path to the SQLite database file. Default: {default_db}",
    )
    parser.add_argument(
        "--output",
        default=None,
        metavar="PATH",
        help=(
            "Optional file path to write eligible doc_ids to, one per line. "
            "Useful for piping to downstream extraction scripts."
        ),
    )
    parser.add_argument(
        "--show-ineligible",
        action="store_true",
        default=False,
        help="Also print ineligible (low-score) articles in the output.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    config = SelectionConfig(
        politicians=args.politicians,
        min_score=args.min_score,
        max_results=args.max_results,
        date_from=args.date_from,
        date_to=args.date_to,
    )

    print("[select_candidate_articles] Running article selector…")
    print(f"  Politicians : {', '.join(config.politicians)}")
    print(f"  Min score   : {config.min_score}")
    print(f"  Max results : {config.max_results or 'unlimited'}")
    if config.date_from or config.date_to:
        print(f"  Date range  : {config.date_from or '*'} → {config.date_to or '*'}")
    print()

    try:
        result = select_candidate_articles(config=config, db_path=args.db_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print(
        f"[select_candidate_articles] Candidates found : {result.total_candidates}"
    )
    print(
        f"[select_candidate_articles] Eligible articles: {result.eligible_count}"
    )
    print()

    # Print eligible articles.
    eligible = result.eligible_articles
    if eligible:
        print(f"=== Eligible articles ({len(eligible)}) ===")
        for i, article in enumerate(eligible, start=1):
            _print_summary(article, i)
            print()
    else:
        print("No eligible articles found for the given criteria.")

    # Optionally print ineligible.
    if args.show_ineligible:
        ineligible = [a for a in result.articles if not a.is_eligible]
        if ineligible:
            print(f"=== Ineligible articles ({len(ineligible)}) ===")
            for i, article in enumerate(ineligible, start=1):
                _print_summary(article, i)
                print()

    # Optionally write doc_ids to a file.
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc_ids = [a.doc_id for a in eligible]
        output_path.write_text("\n".join(doc_ids) + ("\n" if doc_ids else ""), encoding="utf-8")
        print(f"[select_candidate_articles] Wrote {len(doc_ids)} doc_ids to: {output_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
