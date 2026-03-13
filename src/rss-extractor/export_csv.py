#!/usr/bin/env python3
"""
export_csv.py
=============
Export **all** stored extracted articles from the local SQLite database
into ``output.csv`` using the Supabase-compatible schema.

Usage (run from the ``merge_ready/`` directory)::

    python export_csv.py                        # default paths
    python export_csv.py --db data/tracker.db   # custom DB path
    python export_csv.py --out my_export.csv    # custom output file

The script reads every row in the ``extracted_articles`` table, loads the
corresponding body text from the document store, resolves politician names
from the ``politician_mentions`` table via the politicians config, and writes
the result as a CSV whose header matches the team's Supabase schema exactly::

    id,doc_id,title,text,date,media_name,media_type,source_platform,
    state,city,link,speakers_mentioned,created_at
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure merge_ready/ (script directory) is importable so that
# ``from src.X import ...`` works, matching manual_test.py convention.
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from src.adapters.supabase_export import (  # noqa: E402
    SupabaseRecord,
    records_to_csv,
    to_supabase_record,
)
from src.extractor.models import (  # noqa: E402
    ArticleMetadata,
    ExtractedArticle,
    PoliticianMention,
    RelevanceLevel,
)
from src.storage.document_store import load_extracted_text  # noqa: E402
from src.utils.config import load_politicians  # noqa: E402


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def _get_all_extracted_articles(
    conn: sqlite3.Connection,
    data_dir: Path,
) -> list[ExtractedArticle]:
    """Read every extracted article from the database.

    Body text is loaded from the document store on disk.
    """
    rows = conn.execute(
        """
        SELECT article_id, url, title, body_path, word_count,
               extraction_backend, extracted_at, language, byline,
               published_at, site_name, canonical_url
        FROM   extracted_articles
        ORDER  BY extracted_at
        """
    ).fetchall()

    articles: list[ExtractedArticle] = []
    for row in rows:
        body = load_extracted_text(row["article_id"], data_dir) or ""

        published_at = None
        if row["published_at"]:
            published_at = datetime.fromisoformat(row["published_at"])
            if published_at.tzinfo is None:
                published_at = published_at.replace(tzinfo=UTC)

        extracted_at = datetime.fromisoformat(row["extracted_at"])
        if extracted_at.tzinfo is None:
            extracted_at = extracted_at.replace(tzinfo=UTC)

        metadata = ArticleMetadata(
            title=row["title"] or "",
            byline=row["byline"],
            published_at=published_at,
            site_name=row["site_name"],
            language=row["language"],
            canonical_url=row["canonical_url"],
        )

        articles.append(
            ExtractedArticle(
                article_id=row["article_id"],
                url=row["url"],
                body=body,
                metadata=metadata,
                word_count=row["word_count"],
                extraction_backend=row["extraction_backend"],
                extracted_at=extracted_at,
            )
        )
    return articles


def _get_all_mentions(
    conn: sqlite3.Connection,
    politician_names: dict[str, str],
) -> dict[str, list[PoliticianMention]]:
    """Read all politician mentions, grouped by article_id.

    Args:
        conn: Open SQLite connection.
        politician_names: Mapping of politician_id → canonical name
            (from the politicians config).

    Returns:
        Dict mapping article_id to its list of PoliticianMention objects.
    """
    rows = conn.execute(
        """
        SELECT politician_id, article_id, relevance, relevance_score,
               mention_count
        FROM   politician_mentions
        ORDER  BY article_id, relevance_score DESC
        """
    ).fetchall()

    mentions: dict[str, list[PoliticianMention]] = {}
    for row in rows:
        pid = row["politician_id"]
        name = politician_names.get(pid, pid)  # fall back to ID if unknown
        mention = PoliticianMention(
            politician_id=pid,
            politician_name=name,
            article_id=row["article_id"],
            relevance=RelevanceLevel(row["relevance"]),
            relevance_score=row["relevance_score"],
            mention_count=row["mention_count"],
        )
        mentions.setdefault(row["article_id"], []).append(mention)
    return mentions


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export all stored articles to a Supabase-compatible CSV."
    )
    parser.add_argument(
        "--db",
        default="data/tracker.db",
        help="Path to the SQLite database (default: data/tracker.db)",
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Root data directory for document store (default: data)",
    )
    parser.add_argument(
        "--out",
        default="output.csv",
        help="Output CSV file path (default: output.csv)",
    )
    parser.add_argument(
        "--politicians",
        default="config/politicians.yaml",
        help="Path to politicians config (default: config/politicians.yaml)",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    data_dir = Path(args.data_dir)
    out_path = Path(args.out)
    politicians_path = Path(args.politicians)

    # Validate inputs
    if not db_path.exists():
        print(f"ERROR: Database not found at {db_path}", file=sys.stderr)
        sys.exit(1)

    # Build politician_id → name lookup from config
    politician_names: dict[str, str] = {}
    if politicians_path.exists():
        politicians = load_politicians(str(politicians_path))
        politician_names = {p.id: p.name for p in politicians}
    else:
        print(
            f"WARNING: Politicians config not found at {politicians_path}; "
            "speaker names will fall back to politician IDs.",
            file=sys.stderr,
        )

    # Connect to database
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    try:
        # Load all extracted articles
        articles = _get_all_extracted_articles(conn, data_dir)
        if not articles:
            print("No extracted articles found in the database.")
            # Write CSV with header only
            out_path.write_text(
                ",".join(
                    [
                        "id", "doc_id", "title", "text", "date", "media_name",
                        "media_type", "source_platform", "state", "city",
                        "link", "speakers_mentioned", "created_at",
                    ]
                )
                + "\n"
            )
            print(f"Wrote empty CSV (header only) to {out_path}")
            return

        # Load all politician mentions
        mentions_map = _get_all_mentions(conn, politician_names)

        # Convert to Supabase records
        records: list[SupabaseRecord] = []
        for article in articles:
            article_mentions = mentions_map.get(article.article_id, [])
            record = to_supabase_record(article, mentions=article_mentions)
            records.append(record)

        # Write CSV
        csv_output = records_to_csv(records)
        out_path.write_text(csv_output, encoding="utf-8")
        print(f"Exported {len(records)} records to {out_path}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
