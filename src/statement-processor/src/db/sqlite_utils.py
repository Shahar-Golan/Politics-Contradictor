"""
db.sqlite_utils
===============
Low-level SQLite helpers for the statement-processor pipeline.

Provides a thin wrapper around ``sqlite3`` so that higher-level modules
(``init_db``, ``import_news_articles``) share a consistent connection
pattern and do not duplicate boilerplate.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

# Default database path relative to the statement-processor root.
_DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "political_dossier.db"


def get_default_db_path() -> Path:
    """Return the default SQLite database path.

    Returns
    -------
    Path
        Resolved absolute path to ``data/political_dossier.db``.
    """
    return _DEFAULT_DB_PATH.resolve()


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Open (or create) the SQLite database and return a connection.

    The connection has ``row_factory`` set to :class:`sqlite3.Row` so that
    cursor results can be accessed by column name.

    Parameters
    ----------
    db_path:
        Path to the SQLite file.  If *None* the default path
        ``data/political_dossier.db`` inside the ``statement-processor``
        directory is used.

    Returns
    -------
    sqlite3.Connection
        An open database connection with foreign-key enforcement enabled.
    """
    if db_path is None:
        db_path = get_default_db_path()

    path = Path(db_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    # Enable foreign-key constraints (off by default in SQLite).
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def execute_script(conn: sqlite3.Connection, sql: str) -> None:
    """Execute a multi-statement SQL script inside *conn*.

    Parameters
    ----------
    conn:
        An open :class:`sqlite3.Connection`.
    sql:
        A string containing one or more SQL statements separated by
        semicolons.
    """
    conn.executescript(sql)
    conn.commit()


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    """Return *True* if *table_name* exists in the database.

    Parameters
    ----------
    conn:
        An open :class:`sqlite3.Connection`.
    table_name:
        The name of the table to check.
    """
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?;",
        (table_name,),
    ).fetchone()
    return row is not None


def row_count(conn: sqlite3.Connection, table_name: str) -> int:
    """Return the number of rows in *table_name*.

    Parameters
    ----------
    conn:
        An open :class:`sqlite3.Connection`.
    table_name:
        The name of the table to count.  Must be an existing table in the
        database; this is validated against ``sqlite_master`` to prevent
        SQL injection from unsanitised input.

    Raises
    ------
    ValueError
        If *table_name* does not exist in the database.
    """
    if not table_exists(conn, table_name):
        raise ValueError(f"Table {table_name!r} does not exist in the database.")
    # table_name is now confirmed to be a real table name – safe to interpolate.
    result: Any = conn.execute(f"SELECT COUNT(*) FROM {table_name};").fetchone()
    return int(result[0])


def list_tables(conn: sqlite3.Connection) -> list[str]:
    """Return a sorted list of user-defined table names in the database.

    Parameters
    ----------
    conn:
        An open :class:`sqlite3.Connection`.
    """
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
    ).fetchall()
    return [row[0] for row in rows]
