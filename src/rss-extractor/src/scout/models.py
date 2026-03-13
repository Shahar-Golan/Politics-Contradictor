"""
scout.models
============
Typed domain models for the Scout acquisition layer.

These dataclasses represent the core records produced by the Scout pipeline:
feed sources, fetch logs, parsed feed items, and raw article fetches.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class FetchStatus(str, Enum):
    """HTTP fetch outcome for a polling attempt."""

    SUCCESS = "success"
    NOT_MODIFIED = "not_modified"
    ERROR = "error"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"


@dataclass
class FeedSource:
    """A configured RSS/Atom feed to be polled by the Scout.

    Attributes:
        id: Unique slug identifier (matches config/feeds.yaml).
        name: Human-readable display name.
        url: URL of the RSS or Atom feed endpoint.
        enabled: Whether the feed is currently active.
        tags: Optional topic tags for the source.
        poll_interval_minutes: How often this feed should be polled.
    """

    id: str
    name: str
    url: str
    enabled: bool = True
    tags: list[str] = field(default_factory=list)
    poll_interval_minutes: int = 30


@dataclass
class FeedFetchLog:
    """Log record for a single feed poll attempt.

    Attributes:
        feed_id: ID of the ``FeedSource`` that was polled.
        fetched_at: UTC timestamp when the poll was initiated.
        status: Outcome of the fetch attempt.
        http_status_code: Raw HTTP response code, if available.
        etag: ETag header returned by the server, if any.
        last_modified: Last-Modified header returned by the server, if any.
        items_found: Number of items parsed from the feed response.
        error_message: Human-readable error detail on failure.
    """

    feed_id: str
    fetched_at: datetime
    status: FetchStatus
    http_status_code: int | None = None
    etag: str | None = None
    last_modified: str | None = None
    items_found: int = 0
    error_message: str | None = None


@dataclass
class FeedItem:
    """A single item (entry) parsed from an RSS or Atom feed.

    Attributes:
        item_id: Unique fingerprint hash for deduplication.
        feed_id: ID of the source ``FeedSource``.
        title: Item title from the feed.
        url: Link URL of the article.
        published_at: Publication timestamp, if present in the feed.
        summary: Short description or excerpt from the feed.
        guid: Feed-level GUID for the item, if provided.
        discovered_at: UTC timestamp when this item was first parsed.
    """

    item_id: str
    feed_id: str
    title: str
    url: str
    published_at: datetime | None = None
    summary: str | None = None
    guid: str | None = None
    discovered_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


@dataclass
class FeedPollResult:
    """Result of a single feed poll attempt.

    Bundles the fetch log together with the raw XML text (when available)
    so callers receive a single, self-describing object rather than a plain
    tuple.

    Attributes:
        log: ``FeedFetchLog`` describing the outcome of the poll.
        xml_text: Raw XML content of the feed response, or ``None`` if the
            feed was unchanged, disabled, or an error occurred.
    """

    log: FeedFetchLog
    xml_text: str | None


@dataclass
class RawArticle:
    """A raw HTML page fetched from an article URL.

    Attributes:
        article_id: Unique fingerprint hash for this fetch.
        feed_item_id: ID of the ``FeedItem`` that led to this fetch.
        url: URL of the fetched page.
        final_url: URL after any redirects (canonical resolved URL).
        html: Raw HTML content of the page.
        fetched_at: UTC timestamp of the fetch.
        status: Outcome of the HTTP fetch.
        http_status_code: HTTP response status code.
        content_type: Content-Type header from the response.
        error_message: Error detail if the fetch failed.
    """

    article_id: str
    feed_item_id: str
    url: str
    final_url: str
    html: str
    fetched_at: datetime
    status: FetchStatus
    http_status_code: int | None = None
    content_type: str | None = None
    error_message: str | None = None
