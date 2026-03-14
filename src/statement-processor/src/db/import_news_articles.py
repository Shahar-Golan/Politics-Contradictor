"""
db.import_news_articles
=======================
Imports a ``news_articles`` CSV export into the local SQLite database.

Expected CSV columns (order-independent):
    id, doc_id, title, text, date, media_name, media_type,
    source_platform, state, city, link, speakers_mentioned, created_at

The ``doc_id`` column must be unique.  Re-running the import will skip
rows whose ``doc_id`` is already present rather than inserting duplicates
(``INSERT OR IGNORE`` semantics).

``speakers_mentioned`` may arrive as a plain string, a JSON array string,
or a comma-separated list.  All forms are normalised to a JSON array string
before storage (e.g. ``'["Alice", "Bob"]'``).

Usage (CLI)::

    python -m db.import_news_articles --csv data/news_articles.csv \\
        [--db-path data/political_dossier.db]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

from .init_db import init_db
from .sqlite_utils import get_connection, get_default_db_path, row_count

# CSV columns that are written to SQLite (id is omitted; SQLite auto-assigns it).
_INSERT_COLUMNS = (
    "doc_id",
    "title",
    "text",
    "date",
    "media_name",
    "media_type",
    "source_platform",
    "state",
    "city",
    "link",
    "speakers_mentioned",
    "created_at",
)

_INSERT_SQL = (
    "INSERT OR IGNORE INTO news_articles "
    f"({', '.join(_INSERT_COLUMNS)}) "
    f"VALUES ({', '.join(':' + c for c in _INSERT_COLUMNS)});"
)


def _set_max_csv_field_size_limit() -> None:
    """Raise the csv parser field size limit to handle large article bodies.

    Python's default CSV field limit (often 131072 bytes) is too small for
    long article text columns. We try progressively smaller values if the
    platform cannot accept ``sys.maxsize`` directly.
    """
    limit = sys.maxsize
    while limit > 0:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10

    # Fallback to the default parser behavior if no valid larger limit is found.
    csv.field_size_limit()


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------


def _normalise_speakers(raw: Any) -> str:
    """Normalise *raw* ``speakers_mentioned`` value to a JSON array string.

    Handles:
    - Already-valid JSON array strings: returned as-is after round-trip.
    - Comma-separated strings: split and stripped.
    - None / empty: returns ``'[]'``.

    Parameters
    ----------
    raw:
        The raw value from the CSV cell.

    Returns
    -------
    str
        A JSON array string, e.g. ``'["Alice", "Bob"]'``.
    """
    if raw is None or str(raw).strip() == "":
        return "[]"

    raw_str = str(raw).strip()

    # Try to parse as JSON first.
    try:
        parsed = json.loads(raw_str)
        if isinstance(parsed, list):
            return json.dumps([str(s).strip() for s in parsed if str(s).strip()])
    except (json.JSONDecodeError, ValueError):
        pass

    # Fall back to comma-separated parsing.
    parts = [p.strip() for p in raw_str.split(",") if p.strip()]
    return json.dumps(parts)


def _build_row(csv_row: dict[str, Any]) -> dict[str, Any]:
    """Transform a raw CSV row dict into a parameter dict for the INSERT.

    Parameters
    ----------
    csv_row:
        A dict produced by :class:`csv.DictReader`.

    Returns
    -------
    dict
        A dict whose keys match ``_INSERT_COLUMNS``.

    Raises
    ------
    ValueError
        If ``doc_id`` is absent or empty.
    """
    doc_id = csv_row.get("doc_id", "").strip()
    if not doc_id:
        raise ValueError(f"Row is missing a non-empty 'doc_id': {csv_row!r}")

    return {
        "doc_id": doc_id,
        "title": csv_row.get("title") or None,
        "text": csv_row.get("text") or None,
        "date": csv_row.get("date") or None,
        "media_name": csv_row.get("media_name") or None,
        "media_type": csv_row.get("media_type") or None,
        "source_platform": csv_row.get("source_platform") or None,
        "state": csv_row.get("state") or None,
        "city": csv_row.get("city") or None,
        "link": csv_row.get("link") or None,
        "speakers_mentioned": _normalise_speakers(csv_row.get("speakers_mentioned")),
        "created_at": csv_row.get("created_at") or None,
    }


# ---------------------------------------------------------------------------
# Public import function
# ---------------------------------------------------------------------------


def import_csv(
    csv_path: Path | str,
    db_path: Path | str | None = None,
) -> dict[str, int]:
    """Import a ``news_articles`` CSV file into the local SQLite database.

    The function:
    1. Ensures the database and schema exist (calls :func:`init_db`).
    2. Reads every row from *csv_path*.
    3. Inserts rows using ``INSERT OR IGNORE`` (skips duplicate ``doc_id``s).

    Parameters
    ----------
    csv_path:
        Path to the CSV file to import.
    db_path:
        Path to the SQLite database file.  Defaults to the project default.

    Returns
    -------
    dict
        A summary dict with keys ``attempted``, ``inserted``, ``skipped``.

    Raises
    ------
    FileNotFoundError
        If *csv_path* does not exist.
    ValueError
        If a row is missing a required ``doc_id``.
    """
    csv_path = Path(csv_path).resolve()
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    resolved_db = init_db(db_path)
    _set_max_csv_field_size_limit()

    with get_connection(resolved_db) as conn:
        before = row_count(conn, "news_articles")

        with csv_path.open(newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames is None:
                raise ValueError(f"CSV file is empty or has no header: {csv_path}")

            rows: list[dict[str, Any]] = []
            for lineno, raw_row in enumerate(reader, start=2):
                try:
                    rows.append(_build_row(raw_row))
                except ValueError as exc:
                    raise ValueError(f"Line {lineno}: {exc}") from exc

            conn.executemany(_INSERT_SQL, rows)
            conn.commit()

        after = row_count(conn, "news_articles")

    attempted = len(rows)
    inserted = after - before
    skipped = attempted - inserted

    print(f"[import_csv] Source : {csv_path}")
    print(f"[import_csv] Target : {resolved_db}")
    print(f"[import_csv] Attempted : {attempted}")
    print(f"[import_csv] Inserted  : {inserted}")
    print(f"[import_csv] Skipped   : {skipped} (duplicate doc_id)")
    return {"attempted": attempted, "inserted": inserted, "skipped": skipped}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    default_csv = get_default_db_path().parent / "news_articles.csv"
    parser = argparse.ArgumentParser(
        description="Import a news_articles CSV file into the local SQLite database.",
    )
    parser.add_argument(
        "--csv",
        default=str(default_csv),
        metavar="PATH",
        help=f"Path to the CSV file to import (default: {default_csv}).",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        metavar="PATH",
        help=(
            "Path to the SQLite file. "
            f"Defaults to: {get_default_db_path()}"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    import_csv(csv_path=args.csv, db_path=args.db_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
