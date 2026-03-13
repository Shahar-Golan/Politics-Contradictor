"""
test_supabase_export
====================
Tests for the Supabase schema adapter and export layer.

Validates:
- Schema transformation correctness
- Required fields are present
- Null/fallback handling
- CSV and dict serialisation
- Import smoke checks for the merge-ready package
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import datetime, timezone

import pytest

from adapters.supabase_export import (
    SUPABASE_COLUMNS,
    SupabaseRecord,
    record_to_dict,
    records_to_csv,
    records_to_dicts,
    to_supabase_record,
    to_supabase_records,
)
from extractor.models import (
    ArticleMetadata,
    ExtractedArticle,
    PoliticianMention,
    RelevanceLevel,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_metadata() -> ArticleMetadata:
    """A realistic ArticleMetadata for testing."""
    return ArticleMetadata(
        title="Senate passes infrastructure bill",
        byline="Jane Reporter",
        published_at=datetime(2025, 10, 15, 14, 30, tzinfo=timezone.utc),
        site_name="Reuters",
        section="Politics",
        language="en",
        tags=["politics", "infrastructure"],
        canonical_url="https://www.reuters.com/example/bill",
    )


@pytest.fixture()
def sample_article(sample_metadata: ArticleMetadata) -> ExtractedArticle:
    """A realistic ExtractedArticle for testing."""
    return ExtractedArticle(
        article_id="abc123",
        url="https://www.reuters.com/example/bill?utm_source=test",
        body="The Senate passed an infrastructure bill today.",
        metadata=sample_metadata,
        word_count=8,
        extraction_backend="beautifulsoup",
        extracted_at=datetime(2025, 10, 15, 15, 0, tzinfo=timezone.utc),
    )


@pytest.fixture()
def sample_mentions() -> list[PoliticianMention]:
    """Politician mentions for testing speakers_mentioned."""
    return [
        PoliticianMention(
            politician_id="joe-biden",
            politician_name="Joe Biden",
            article_id="abc123",
            relevance=RelevanceLevel.PRIMARY,
            relevance_score=0.85,
            mention_count=5,
            matched_aliases=["Biden", "President Biden"],
        ),
        PoliticianMention(
            politician_id="chuck-schumer",
            politician_name="Chuck Schumer",
            article_id="abc123",
            relevance=RelevanceLevel.SECONDARY,
            relevance_score=0.35,
            mention_count=2,
            matched_aliases=["Schumer"],
        ),
    ]


# ---------------------------------------------------------------------------
# Schema transformation tests
# ---------------------------------------------------------------------------


class TestToSupabaseRecord:
    """Tests for to_supabase_record()."""

    def test_all_required_fields_present(
        self, sample_article: ExtractedArticle
    ) -> None:
        """Every field in SUPABASE_COLUMNS must be present in the record."""
        record = to_supabase_record(sample_article)
        record_dict = record_to_dict(record)
        for col in SUPABASE_COLUMNS:
            assert col in record_dict, f"Missing required field: {col}"

    def test_id_is_valid_uuid(self, sample_article: ExtractedArticle) -> None:
        """The generated id must be a valid UUID-4."""
        record = to_supabase_record(sample_article)
        parsed = uuid.UUID(record.id)
        assert parsed.version == 4

    def test_custom_id(self, sample_article: ExtractedArticle) -> None:
        """A caller-supplied record_id should be used."""
        custom_id = "custom-id-000"
        record = to_supabase_record(sample_article, record_id=custom_id)
        assert record.id == custom_id

    def test_doc_id_from_article_id(
        self, sample_article: ExtractedArticle
    ) -> None:
        """doc_id must equal the article's article_id."""
        record = to_supabase_record(sample_article)
        assert record.doc_id == "abc123"

    def test_title_from_metadata(self, sample_article: ExtractedArticle) -> None:
        """title must come from the article metadata."""
        record = to_supabase_record(sample_article)
        assert record.title == "Senate passes infrastructure bill"

    def test_text_from_body(self, sample_article: ExtractedArticle) -> None:
        """text must be the cleaned article body."""
        record = to_supabase_record(sample_article)
        assert record.text == "The Senate passed an infrastructure bill today."

    def test_date_from_published_at(
        self, sample_article: ExtractedArticle
    ) -> None:
        """date must be the ISO 8601 representation of published_at."""
        record = to_supabase_record(sample_article)
        assert record.date is not None
        assert "2025-10-15" in record.date

    def test_date_none_when_no_published_at(
        self, sample_article: ExtractedArticle
    ) -> None:
        """date must be None when published_at is absent."""
        sample_article.metadata.published_at = None
        record = to_supabase_record(sample_article)
        assert record.date is None

    def test_media_name_from_site_name(
        self, sample_article: ExtractedArticle
    ) -> None:
        """media_name must come from metadata.site_name."""
        record = to_supabase_record(sample_article)
        assert record.media_name == "Reuters"

    def test_media_name_fallback_to_empty(
        self, sample_article: ExtractedArticle
    ) -> None:
        """media_name should be empty string when site_name is None."""
        sample_article.metadata.site_name = None
        record = to_supabase_record(sample_article)
        assert record.media_name == ""

    def test_media_type_default(self, sample_article: ExtractedArticle) -> None:
        """media_type defaults to 'rss_news'."""
        record = to_supabase_record(sample_article)
        assert record.media_type == "rss_news"

    def test_media_type_override(self, sample_article: ExtractedArticle) -> None:
        """media_type can be overridden."""
        record = to_supabase_record(sample_article, media_type="article")
        assert record.media_type == "article"

    def test_source_platform_default(
        self, sample_article: ExtractedArticle
    ) -> None:
        """source_platform defaults to 'rss'."""
        record = to_supabase_record(sample_article)
        assert record.source_platform == "rss"

    def test_state_default_empty(self, sample_article: ExtractedArticle) -> None:
        """state defaults to empty string."""
        record = to_supabase_record(sample_article)
        assert record.state == ""

    def test_city_default_empty(self, sample_article: ExtractedArticle) -> None:
        """city defaults to empty string."""
        record = to_supabase_record(sample_article)
        assert record.city == ""

    def test_link_uses_canonical_url(
        self, sample_article: ExtractedArticle
    ) -> None:
        """link should use the canonical URL from metadata."""
        record = to_supabase_record(sample_article)
        assert record.link == "https://www.reuters.com/example/bill"

    def test_link_falls_back_to_article_url(
        self, sample_article: ExtractedArticle
    ) -> None:
        """link should fall back to article.url when canonical_url is None."""
        sample_article.metadata.canonical_url = None
        record = to_supabase_record(sample_article)
        assert record.link == sample_article.url

    def test_speakers_mentioned_with_mentions(
        self,
        sample_article: ExtractedArticle,
        sample_mentions: list[PoliticianMention],
    ) -> None:
        """speakers_mentioned should contain comma-separated politician names."""
        record = to_supabase_record(sample_article, mentions=sample_mentions)
        assert record.speakers_mentioned == "Joe Biden, Chuck Schumer"

    def test_speakers_mentioned_no_mentions(
        self, sample_article: ExtractedArticle
    ) -> None:
        """speakers_mentioned should be empty string with no mentions."""
        record = to_supabase_record(sample_article)
        assert record.speakers_mentioned == ""

    def test_speakers_mentioned_deduplication(
        self, sample_article: ExtractedArticle
    ) -> None:
        """Duplicate politician names should not appear twice."""
        dup_mentions = [
            PoliticianMention(
                politician_id="biden", politician_name="Joe Biden",
                article_id="abc123", relevance=RelevanceLevel.PRIMARY,
                relevance_score=0.9, mention_count=3,
            ),
            PoliticianMention(
                politician_id="biden-2", politician_name="Joe Biden",
                article_id="abc123", relevance=RelevanceLevel.SECONDARY,
                relevance_score=0.4, mention_count=1,
            ),
        ]
        record = to_supabase_record(sample_article, mentions=dup_mentions)
        assert record.speakers_mentioned == "Joe Biden"

    def test_created_at_is_iso_format(
        self, sample_article: ExtractedArticle
    ) -> None:
        """created_at must be an ISO 8601 string."""
        record = to_supabase_record(sample_article)
        # Should be parseable as ISO datetime
        dt = datetime.fromisoformat(record.created_at)
        assert dt.tzinfo is not None

    def test_custom_created_at(self, sample_article: ExtractedArticle) -> None:
        """A caller-supplied created_at should be used."""
        ts = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
        record = to_supabase_record(sample_article, created_at=ts)
        assert "2025-01-01" in record.created_at


# ---------------------------------------------------------------------------
# Batch conversion tests
# ---------------------------------------------------------------------------


class TestToSupabaseRecords:
    """Tests for to_supabase_records()."""

    def test_batch_conversion(self, sample_article: ExtractedArticle) -> None:
        """Batch conversion should produce one record per article."""
        articles = [sample_article, sample_article]
        records = to_supabase_records(articles)
        assert len(records) == 2
        # Each record should have a unique id
        ids = {r.id for r in records}
        assert len(ids) == 2

    def test_batch_with_mentions(
        self,
        sample_article: ExtractedArticle,
        sample_mentions: list[PoliticianMention],
    ) -> None:
        """Batch conversion should apply mentions when provided."""
        mentions_map = {sample_article.article_id: sample_mentions}
        records = to_supabase_records([sample_article], mentions_by_article=mentions_map)
        assert records[0].speakers_mentioned == "Joe Biden, Chuck Schumer"

    def test_empty_list(self) -> None:
        """Batch conversion of empty list should return empty list."""
        assert to_supabase_records([]) == []


# ---------------------------------------------------------------------------
# Serialisation tests
# ---------------------------------------------------------------------------


class TestRecordSerialization:
    """Tests for record_to_dict, records_to_dicts, and records_to_csv."""

    def test_record_to_dict_keys(
        self, sample_article: ExtractedArticle
    ) -> None:
        """Dict keys must match SUPABASE_COLUMNS exactly."""
        record = to_supabase_record(sample_article)
        d = record_to_dict(record)
        assert set(d.keys()) == set(SUPABASE_COLUMNS)

    def test_records_to_dicts(self, sample_article: ExtractedArticle) -> None:
        """records_to_dicts should produce one dict per record."""
        records = to_supabase_records([sample_article])
        dicts = records_to_dicts(records)
        assert len(dicts) == 1
        assert dicts[0]["doc_id"] == "abc123"

    def test_csv_header(self, sample_article: ExtractedArticle) -> None:
        """CSV output must have the correct header."""
        records = to_supabase_records([sample_article])
        csv_str = records_to_csv(records)
        reader = csv.DictReader(io.StringIO(csv_str))
        assert reader.fieldnames is not None
        assert list(reader.fieldnames) == SUPABASE_COLUMNS

    def test_csv_row_count(self, sample_article: ExtractedArticle) -> None:
        """CSV should have one data row per record."""
        records = to_supabase_records([sample_article, sample_article])
        csv_str = records_to_csv(records)
        lines = csv_str.strip().split("\n")
        assert len(lines) == 3  # header + 2 data rows

    def test_csv_roundtrip(
        self,
        sample_article: ExtractedArticle,
        sample_mentions: list[PoliticianMention],
    ) -> None:
        """Data should survive a CSV write-then-read roundtrip."""
        record = to_supabase_record(sample_article, mentions=sample_mentions)
        csv_str = records_to_csv([record])
        reader = csv.DictReader(io.StringIO(csv_str))
        rows = list(reader)
        assert len(rows) == 1
        row = rows[0]
        assert row["title"] == "Senate passes infrastructure bill"
        assert row["speakers_mentioned"] == "Joe Biden, Chuck Schumer"
        assert row["source_platform"] == "rss"


# ---------------------------------------------------------------------------
# Import smoke tests
# ---------------------------------------------------------------------------


class TestImportSmoke:
    """Smoke tests verifying that key modules in the merge-ready package
    can be imported without errors."""

    def test_import_scout_models(self) -> None:
        from scout.models import FeedItem, FeedSource, RawArticle  # noqa: F401

    def test_import_extractor_models(self) -> None:
        from extractor.models import (  # noqa: F401
            ExtractedArticle,
            PoliticianMention,
            StatementCandidate,
        )

    def test_import_adapter(self) -> None:
        from adapters.supabase_export import (  # noqa: F401
            SupabaseRecord,
            to_supabase_record,
        )

    def test_import_utils(self) -> None:
        from utils.hashing import hash_url  # noqa: F401
        from utils.time import utcnow  # noqa: F401
        from utils.urls import normalize_url  # noqa: F401

    def test_import_config(self) -> None:
        from utils.config import AppSettings, PoliticianConfig  # noqa: F401

    def test_import_pipelines(self) -> None:
        from pipelines.ingest_article import ingest_article  # noqa: F401
        from pipelines.ingest_feed import ingest_feed  # noqa: F401

    def test_import_storage(self) -> None:
        from storage.sql import init_schema  # noqa: F401
        from storage.document_store import save_raw_html  # noqa: F401


# ---------------------------------------------------------------------------
# Example output validation
# ---------------------------------------------------------------------------


class TestExampleArtifacts:
    """Validate that the example output artifacts match the expected schema."""

    def test_example_csv_header(self) -> None:
        """examples/sample_export.csv must have the correct header."""
        from pathlib import Path

        csv_path = Path(__file__).parent.parent / "examples" / "sample_export.csv"
        assert csv_path.exists(), f"Example CSV not found at {csv_path}"
        with csv_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            assert reader.fieldnames is not None
            assert list(reader.fieldnames) == SUPABASE_COLUMNS

    def test_example_json_keys(self) -> None:
        """examples/sample_export.json records must have the correct keys."""
        from pathlib import Path

        json_path = Path(__file__).parent.parent / "examples" / "sample_export.json"
        assert json_path.exists(), f"Example JSON not found at {json_path}"
        with json_path.open("r", encoding="utf-8") as f:
            records = json.load(f)
        assert isinstance(records, list)
        assert len(records) > 0
        for record in records:
            for col in SUPABASE_COLUMNS:
                assert col in record, f"Missing field '{col}' in example JSON"
