#!/usr/bin/env python3
"""
push_to_supabase.py
===================
Upload ``output.csv`` (or any Supabase-schema CSV) to a Supabase table,
with built-in deduplication based on ``doc_id``.

Setup
-----
1. Copy ``.env.example`` to ``.env`` in this directory and fill in your
   Supabase credentials (see ``.env.example`` for details).
2. Install the Supabase client::

       pip install supabase

3. Generate the CSV first::

       python export_csv.py

4. Push to Supabase::

       python push_to_supabase.py                       # defaults
       python push_to_supabase.py --csv output.csv      # custom CSV
       python push_to_supabase.py --table articles      # custom table
       python push_to_supabase.py --dry-run              # preview only

Security
--------
- **Never** commit your ``.env`` file.  It is listed in ``.gitignore``.
- Store your Supabase API key in the ``.env`` file only.
- Use the **service_role** key only if Row-Level Security (RLS) requires it;
  otherwise prefer the **anon** key with appropriate RLS policies.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure merge_ready/ (script directory) is importable so that
# ``from src.X import ...`` works, matching manual_test.py convention.
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))


def _load_env(env_path: Path) -> None:
    """Load KEY=VALUE pairs from a .env file into os.environ.

    Skips blank lines and comments (lines starting with ``#``).
    Does not override existing environment variables.
    """
    if not env_path.exists():
        return
    with env_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value


def _read_csv(csv_path: Path) -> list[dict[str, str]]:
    """Read a CSV file and return a list of row dicts."""
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Push output.csv to Supabase with deduplication."
    )
    parser.add_argument(
        "--csv",
        default="output.csv",
        help="Path to the CSV file to upload (default: output.csv)",
    )
    parser.add_argument(
        "--table",
        default="news_articles",
        help="Supabase table name (default: news_articles)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of records per insert batch (default: 100)",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to .env file with credentials (default: .env)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be uploaded without actually inserting.",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv)
    env_path = Path(args.env_file)

    # Load environment
    _load_env(env_path)

    supabase_url = os.environ.get("SUPABASE_URL", "")
    supabase_key = os.environ.get("SUPABASE_KEY", "")

    if not supabase_url or not supabase_key:
        print(
            "ERROR: SUPABASE_URL and SUPABASE_KEY must be set.\n"
            "\n"
            "  Option 1: Create a .env file (see .env.example):\n"
            f"            cp .env.example {args.env_file}\n"
            f"            # Edit {args.env_file} with your credentials\n"
            "\n"
            "  Option 2: Set environment variables directly:\n"
            "            export SUPABASE_URL=https://your-project.supabase.co\n"
            "            export SUPABASE_KEY=your-api-key\n",
            file=sys.stderr,
        )
        sys.exit(1)

    if not csv_path.exists():
        print(
            f"ERROR: CSV file not found at {csv_path}\n"
            "       Run 'python export_csv.py' first to generate it.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Read CSV
    rows = _read_csv(csv_path)
    if not rows:
        print("CSV is empty — nothing to upload.")
        return

    print(f"Read {len(rows)} records from {csv_path}")

    # --- Dry-run mode ---
    if args.dry_run:
        print(
            f"\n[DRY RUN] Would upload {len(rows)} records to "
            f"table '{args.table}' at {supabase_url}"
        )
        print(f"[DRY RUN] Columns: {', '.join(rows[0].keys())}")
        print(f"[DRY RUN] First doc_id: {rows[0].get('doc_id', 'N/A')}")
        return

    # --- Import Supabase client (lazy: the package is an optional dependency) ---
    try:
        from supabase import create_client  # type: ignore[import-untyped]
    except ImportError:
        print(
            "ERROR: The 'supabase' package is required.\n"
            "       Install it with:  pip install supabase",
            file=sys.stderr,
        )
        sys.exit(1)

    client = create_client(supabase_url, supabase_key)

    # --- Deduplication: fetch existing doc_ids ---
    print(f"Checking for existing records in '{args.table}'...")
    existing_doc_ids: set[str] = set()
    try:
        # Paginate through existing doc_ids
        offset = 0
        page_size = 1000
        while True:
            response = (
                client.table(args.table)
                .select("doc_id")
                .range(offset, offset + page_size - 1)
                .execute()
            )
            batch = response.data or []
            if not batch:
                break
            for record in batch:
                existing_doc_ids.add(record["doc_id"])
            if len(batch) < page_size:
                break
            offset += page_size
    except Exception as e:
        print(
            f"WARNING: Could not fetch existing doc_ids for dedup: {e}\n"
            "         Proceeding without deduplication — duplicates may occur.",
            file=sys.stderr,
        )

    # Filter out already-existing records
    new_rows = [r for r in rows if r.get("doc_id") not in existing_doc_ids]
    skipped = len(rows) - len(new_rows)

    if skipped:
        print(f"Skipping {skipped} duplicate records (already in Supabase)")

    if not new_rows:
        print("All records already exist in Supabase — nothing to upload.")
        return

    # --- Upload in batches ---
    print(f"Uploading {len(new_rows)} new records to '{args.table}'...")
    uploaded = 0
    errors = 0

    for i in range(0, len(new_rows), args.batch_size):
        batch = new_rows[i : i + args.batch_size]
        batch_num = i // args.batch_size + 1
        try:
            client.table(args.table).insert(batch).execute()
            uploaded += len(batch)
            print(
                f"  Uploaded batch {batch_num}: "
                f"{len(batch)} records ({uploaded}/{len(new_rows)})"
            )
        except Exception as e:
            errors += len(batch)
            print(
                f"  ERROR uploading batch {batch_num}: {e}",
                file=sys.stderr,
            )

    # Summary
    print(
        f"\nDone. Uploaded: {uploaded}, Skipped (duplicates): {skipped}, "
        f"Errors: {errors}"
    )


if __name__ == "__main__":
    main()
