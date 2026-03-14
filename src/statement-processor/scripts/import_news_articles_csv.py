#!/usr/bin/env python
"""
scripts/import_news_articles_csv.py
====================================
Entry-point script to import a ``news_articles`` CSV export into the
local SQLite database.

Usage::

    python scripts/import_news_articles_csv.py \\
        [--csv data/news_articles.csv] \\
        [--db-path data/political_dossier.db]

The CSV file must contain at minimum a ``doc_id`` column.  All other
columns listed in the schema are optional and default to NULL when absent
from the CSV.

``speakers_mentioned`` may be supplied as:
- a JSON array string  ``["Alice","Bob"]``
- a comma-separated string  ``Alice, Bob``
- an empty string or omitted entirely

The script will not insert duplicate rows – a row whose ``doc_id`` is
already present in the database is silently skipped.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the package root (src/) is importable when executed as a plain script.
_PACKAGE_ROOT = Path(__file__).parent.parent / "src"
if str(_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT))

from db.import_news_articles import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
