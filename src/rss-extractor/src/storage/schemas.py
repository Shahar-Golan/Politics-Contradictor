"""
storage.schemas
===============
Domain schema definitions for the persistence layer.

Defines the database table structures and field types that map to the
Scout and Extractor domain models. In this initial scaffold, schemas are
described as plain typed dataclasses with column metadata.

TODO: Wire these to an ORM (e.g. SQLAlchemy) or migration tool in a future issue.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class FeedSourceRow:
    """Persistent representation of a ``FeedSource`` in the database.

    Maps to the ``feed_sources`` table.
    """

    id: str
    name: str
    url: str
    enabled: bool
    tags: list[str] = field(default_factory=list)
    poll_interval_minutes: int = 30
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


@dataclass
class FeedFetchLogRow:
    """Persistent representation of a ``FeedFetchLog`` in the database.

    Maps to the ``feed_fetch_logs`` table.
    """

    id: int | None  # Auto-increment primary key
    feed_id: str
    fetched_at: datetime
    status: str
    http_status_code: int | None = None
    etag: str | None = None
    last_modified: str | None = None
    items_found: int = 0
    error_message: str | None = None


@dataclass
class FeedItemRow:
    """Persistent representation of a ``FeedItem`` in the database.

    Maps to the ``feed_items`` table.
    """

    item_id: str  # Primary key (content hash)
    feed_id: str
    title: str
    url: str
    published_at: datetime | None = None
    summary: str | None = None
    guid: str | None = None
    discovered_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    fetched: bool = False


@dataclass
class RawArticleRow:
    """Persistent representation of a ``RawArticle`` in the database.

    Maps to the ``raw_articles`` table.
    """

    article_id: str  # Primary key (content hash)
    feed_item_id: str
    url: str
    final_url: str
    html_path: str  # Path to the stored HTML file on disk
    fetched_at: datetime
    status: str
    http_status_code: int | None = None
    content_type: str | None = None
    error_message: str | None = None


@dataclass
class ExtractedArticleRow:
    """Persistent representation of an ``ExtractedArticle`` in the database.

    Maps to the ``extracted_articles`` table.
    """

    article_id: str  # Foreign key to ``raw_articles``
    url: str
    title: str
    body_path: str  # Path to the stored body text file
    word_count: int
    extraction_backend: str
    extracted_at: datetime
    language: str | None = None
    byline: str | None = None
    published_at: datetime | None = None
    site_name: str | None = None
    canonical_url: str | None = None


@dataclass
class PoliticianMentionRow:
    """Persistent representation of a ``PoliticianMention`` in the database.

    Maps to the ``politician_mentions`` table.
    """

    id: int | None  # Auto-increment primary key
    politician_id: str
    article_id: str
    relevance: str
    relevance_score: float
    mention_count: int = 0


@dataclass
class StatementCandidateRow:
    """Persistent representation of a ``StatementCandidate`` in the database.

    Maps to the ``statement_candidates`` table.
    """

    statement_id: str  # Primary key (content hash)
    article_id: str
    politician_id: str
    text: str
    is_direct_quote: bool = False
    context: str = ""
    char_offset: int | None = None
