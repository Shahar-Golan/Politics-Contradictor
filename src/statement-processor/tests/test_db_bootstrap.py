"""
test_db_bootstrap
=================
Tests for the local SQLite bootstrap and CSV ingestion pipeline.

Covers:
- database file creation
- table creation (news_articles, stance_records, stance_relations)
- successful CSV import
- duplicate doc_id handling (INSERT OR IGNORE)
- basic row count verification after import
- speakers_mentioned normalisation
- missing doc_id raises ValueError
"""

from __future__ import annotations

import csv
import io
import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from db.init_db import init_db
from db.import_news_articles import import_csv, _normalise_speakers
from db.sqlite_utils import (
    get_connection,
    list_tables,
    row_count,
    table_exists,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

EXPECTED_TABLES = {"news_articles", "stance_records", "stance_relations"}

_MINIMAL_HEADERS = [
    "id", "doc_id", "title", "text", "date", "media_name", "media_type",
    "source_platform", "state", "city", "link", "speakers_mentioned", "created_at",
]


def _make_csv(rows: list[dict]) -> Path:
    """Write *rows* to a temporary CSV file and return its Path."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, encoding="utf-8", newline=""
    )
    writer = csv.DictWriter(tmp, fieldnames=_MINIMAL_HEADERS)
    writer.writeheader()
    writer.writerows(rows)
    tmp.close()
    return Path(tmp.name)


def _sample_row(
    doc_id: str = "doc-001",
    title: str = "Test Article",
    text: str = "Body text.",
    speakers_mentioned: str = '["Alice", "Bob"]',
) -> dict:
    return {
        "id": "",
        "doc_id": doc_id,
        "title": title,
        "text": text,
        "date": "2025-01-01",
        "media_name": "Test News",
        "media_type": "rss_news",
        "source_platform": "rss",
        "state": "",
        "city": "",
        "link": "https://example.com/article",
        "speakers_mentioned": speakers_mentioned,
        "created_at": "2025-01-01T00:00:00Z",
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_db(tmp_path: Path) -> Path:
    """Return a path for a fresh temporary SQLite database."""
    return tmp_path / "test_political_dossier.db"


@pytest.fixture()
def initialised_db(tmp_db: Path) -> Path:
    """Create an initialised (schema applied) database and return its path."""
    init_db(tmp_db)
    return tmp_db


# ---------------------------------------------------------------------------
# Database file creation tests
# ---------------------------------------------------------------------------


class TestDatabaseCreation:
    """Verify that the database file is created on disk."""

    def test_db_file_is_created(self, tmp_db: Path) -> None:
        """init_db must create the SQLite file on disk."""
        assert not tmp_db.exists()
        init_db(tmp_db)
        assert tmp_db.exists()

    def test_db_file_is_valid_sqlite(self, tmp_db: Path) -> None:
        """The created file must be a valid SQLite database."""
        init_db(tmp_db)
        conn = sqlite3.connect(str(tmp_db))
        # A valid SQLite DB responds to this query without raising.
        conn.execute("SELECT sqlite_version();").fetchone()
        conn.close()

    def test_init_db_is_idempotent(self, tmp_db: Path) -> None:
        """Calling init_db twice must not raise and must leave tables intact."""
        init_db(tmp_db)
        init_db(tmp_db)  # second call should be safe
        with get_connection(tmp_db) as conn:
            tables = set(list_tables(conn))
        assert EXPECTED_TABLES.issubset(tables)

    def test_returns_resolved_path(self, tmp_db: Path) -> None:
        """init_db should return the resolved absolute Path of the database."""
        result = init_db(tmp_db)
        assert result.is_absolute()
        assert result == tmp_db.resolve()


# ---------------------------------------------------------------------------
# Table creation tests
# ---------------------------------------------------------------------------


class TestTableCreation:
    """Verify that the schema creates the expected tables."""

    def test_all_expected_tables_exist(self, initialised_db: Path) -> None:
        """All three tables must be present after init_db."""
        with get_connection(initialised_db) as conn:
            tables = set(list_tables(conn))
        assert EXPECTED_TABLES.issubset(tables)

    def test_news_articles_table_exists(self, initialised_db: Path) -> None:
        with get_connection(initialised_db) as conn:
            assert table_exists(conn, "news_articles")

    def test_stance_records_table_exists(self, initialised_db: Path) -> None:
        with get_connection(initialised_db) as conn:
            assert table_exists(conn, "stance_records")

    def test_stance_relations_table_exists(self, initialised_db: Path) -> None:
        with get_connection(initialised_db) as conn:
            assert table_exists(conn, "stance_relations")

    def test_news_articles_has_doc_id_column(self, initialised_db: Path) -> None:
        """news_articles must have a doc_id column."""
        with get_connection(initialised_db) as conn:
            cols = [
                row[1]
                for row in conn.execute("PRAGMA table_info(news_articles);").fetchall()
            ]
        assert "doc_id" in cols

    def test_stance_records_has_required_columns(self, initialised_db: Path) -> None:
        """stance_records must contain the core extraction output columns."""
        required = {
            "id", "doc_id", "politician", "topic", "stance_direction",
            "confidence", "review_status", "created_at", "updated_at",
        }
        with get_connection(initialised_db) as conn:
            cols = {
                row[1]
                for row in conn.execute("PRAGMA table_info(stance_records);").fetchall()
            }
        assert required.issubset(cols)

    def test_stance_relations_has_required_columns(self, initialised_db: Path) -> None:
        """stance_relations must contain the core relation columns."""
        required = {"id", "from_stance_id", "to_stance_id", "relation_type", "confidence"}
        with get_connection(initialised_db) as conn:
            cols = {
                row[1]
                for row in conn.execute(
                    "PRAGMA table_info(stance_relations);"
                ).fetchall()
            }
        assert required.issubset(cols)


# ---------------------------------------------------------------------------
# CSV import tests
# ---------------------------------------------------------------------------


class TestCsvImport:
    """Verify the CSV ingestion path."""

    def test_basic_import(self, tmp_db: Path, tmp_path: Path) -> None:
        """A single-row CSV must be imported successfully."""
        csv_file = _make_csv([_sample_row("doc-001")])
        result = import_csv(csv_file, db_path=tmp_db)
        assert result["attempted"] == 1
        assert result["inserted"] == 1
        assert result["skipped"] == 0

    def test_row_count_after_import(self, tmp_db: Path) -> None:
        """Row count in news_articles must equal number of unique rows imported."""
        rows = [_sample_row(f"doc-{i:03d}") for i in range(5)]
        csv_file = _make_csv(rows)
        import_csv(csv_file, db_path=tmp_db)
        with get_connection(tmp_db) as conn:
            count = row_count(conn, "news_articles")
        assert count == 5

    def test_import_creates_db_if_missing(self, tmp_db: Path) -> None:
        """import_csv must create the database if it does not yet exist."""
        assert not tmp_db.exists()
        csv_file = _make_csv([_sample_row("doc-new")])
        import_csv(csv_file, db_path=tmp_db)
        assert tmp_db.exists()

    def test_csv_not_found_raises(self, tmp_db: Path) -> None:
        """Passing a non-existent CSV path must raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            import_csv("/tmp/does_not_exist_ever.csv", db_path=tmp_db)

    def test_missing_doc_id_raises(self, tmp_db: Path, tmp_path: Path) -> None:
        """A row missing doc_id must raise ValueError."""
        bad_row = _sample_row("doc-001")
        bad_row["doc_id"] = ""  # empty doc_id
        csv_file = _make_csv([bad_row])
        with pytest.raises(ValueError, match="doc_id"):
            import_csv(csv_file, db_path=tmp_db)


# ---------------------------------------------------------------------------
# Duplicate doc_id tests
# ---------------------------------------------------------------------------


class TestDuplicateHandling:
    """Verify that duplicate doc_id rows are silently skipped."""

    def test_duplicate_is_skipped(self, tmp_db: Path) -> None:
        """Importing the same doc_id twice must not create duplicate rows."""
        csv_file = _make_csv([_sample_row("dup-001")])
        import_csv(csv_file, db_path=tmp_db)
        result = import_csv(csv_file, db_path=tmp_db)

        assert result["attempted"] == 1
        assert result["inserted"] == 0
        assert result["skipped"] == 1

        with get_connection(tmp_db) as conn:
            count = row_count(conn, "news_articles")
        assert count == 1

    def test_partial_duplicate_batch(self, tmp_db: Path) -> None:
        """Only new doc_ids must be inserted when batch contains duplicates."""
        row_a = _sample_row("doc-a")
        row_b = _sample_row("doc-b")

        csv_file_1 = _make_csv([row_a])
        import_csv(csv_file_1, db_path=tmp_db)

        # Second import contains doc-a (duplicate) and doc-b (new).
        csv_file_2 = _make_csv([row_a, row_b])
        result = import_csv(csv_file_2, db_path=tmp_db)

        assert result["attempted"] == 2
        assert result["inserted"] == 1
        assert result["skipped"] == 1

        with get_connection(tmp_db) as conn:
            count = row_count(conn, "news_articles")
        assert count == 2


# ---------------------------------------------------------------------------
# speakers_mentioned normalisation tests
# ---------------------------------------------------------------------------


class TestSpeakersMentionedNormalisation:
    """Verify that _normalise_speakers handles all expected input forms."""

    def test_json_array_passthrough(self) -> None:
        raw = '["Alice", "Bob"]'
        result = _normalise_speakers(raw)
        assert json.loads(result) == ["Alice", "Bob"]

    def test_comma_separated(self) -> None:
        result = _normalise_speakers("Alice, Bob, Charlie")
        assert json.loads(result) == ["Alice", "Bob", "Charlie"]

    def test_none_returns_empty_list(self) -> None:
        assert _normalise_speakers(None) == "[]"

    def test_empty_string_returns_empty_list(self) -> None:
        assert _normalise_speakers("") == "[]"

    def test_single_name(self) -> None:
        result = _normalise_speakers("Alice")
        assert json.loads(result) == ["Alice"]

    def test_stored_as_json_string_in_db(self, tmp_db: Path) -> None:
        """speakers_mentioned must be stored as a valid JSON string in SQLite."""
        csv_file = _make_csv([_sample_row("doc-sp", speakers_mentioned="Alice, Bob")])
        import_csv(csv_file, db_path=tmp_db)
        with get_connection(tmp_db) as conn:
            row = conn.execute(
                "SELECT speakers_mentioned FROM news_articles WHERE doc_id=?;",
                ("doc-sp",),
            ).fetchone()
        stored = row["speakers_mentioned"]
        parsed = json.loads(stored)
        assert isinstance(parsed, list)
        assert "Alice" in parsed
        assert "Bob" in parsed
