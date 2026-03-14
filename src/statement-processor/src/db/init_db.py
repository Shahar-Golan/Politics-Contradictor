"""
db.init_db
==========
Creates the local SQLite database and applies the canonical schema.

This module can be imported programmatically or run directly as a script:

    python -m db.init_db [--db-path /path/to/political_dossier.db]

The schema is read from ``schema.sql`` in the same directory so that the
single source of truth for the table definitions lives in plain SQL, not
scattered across Python strings.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .sqlite_utils import execute_script, get_connection, get_default_db_path, list_tables

# Path to the checked-in SQL schema file.
_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def init_db(db_path: Path | str | None = None) -> Path:
    """Create the SQLite database and apply the schema.

    The function is idempotent – tables are created with ``IF NOT EXISTS``
    so repeated calls are safe.

    Parameters
    ----------
    db_path:
        Path to the SQLite file.  Defaults to the project's
        ``data/political_dossier.db``.

    Returns
    -------
    Path
        The resolved path of the database file that was initialised.
    """
    resolved = Path(db_path).resolve() if db_path else get_default_db_path()

    schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")

    with get_connection(resolved) as conn:
        execute_script(conn, schema_sql)
        tables = list_tables(conn)

    print(f"[init_db] Database initialised at: {resolved}")
    print(f"[init_db] Tables present: {', '.join(tables)}")
    return resolved


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Initialise the local SQLite database for statement-processor.",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        metavar="PATH",
        help=(
            "Path to the SQLite file to create/update. "
            f"Defaults to: {get_default_db_path()}"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    init_db(args.db_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
