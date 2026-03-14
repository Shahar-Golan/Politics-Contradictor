#!/usr/bin/env python
"""
scripts/init_local_db.py
========================
Entry-point script to initialise the local SQLite database.

Usage::

    python scripts/init_local_db.py [--db-path PATH]

The script creates (or updates) the SQLite file at the given path and
applies the canonical schema from ``src/db/schema.sql``.  All three
tables (``news_articles``, ``stance_records``, ``stance_relations``) are
created if they do not already exist.
"""

from __future__ import annotations

import sys
from pathlib import Path

from tqdm.auto import tqdm

# Ensure the package root (src/) is importable when executed as a plain script.
_PACKAGE_ROOT = Path(__file__).parent.parent / "src"
if str(_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT))

from db.init_db import main as init_db_main  # noqa: E402


def _run_with_progress() -> int:
    """Execute database initialization with a lightweight progress indicator."""
    with tqdm(total=1, desc="Initializing local DB", unit="step") as progress:
        exit_code = init_db_main()
        progress.update(1)
    return int(exit_code) if isinstance(exit_code, int) else 0

if __name__ == "__main__":
    sys.exit(_run_with_progress())
