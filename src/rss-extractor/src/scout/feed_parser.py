"""
scout.feed_parser
=================
Parses raw RSS/Atom XML feed content into typed ``FeedItem`` records.

Uses the ``feedparser`` library for XML parsing and normalises the results
into the domain model. Does NOT perform HTTP requests; see ``poller`` for that.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import feedparser

from src.scout.models import FeedItem
from src.utils.hashing import hash_url
from src.utils.time import parse_feed_timestamp
from src.utils.urls import normalize_url

logger = logging.getLogger(__name__)


def parse_feed(feed_id: str, xml_text: str) -> list[FeedItem]:
    """Parse raw RSS/Atom XML into a list of typed ``FeedItem`` records.

    Args:
        feed_id: ID of the ``FeedSource`` this content came from.
        xml_text: Raw XML text of the feed response.

    Returns:
        A list of ``FeedItem`` objects. Empty list on parse failure.
    """
    parsed = feedparser.parse(xml_text)

    if parsed.bozo and not parsed.entries:
        logger.warning(
            "Feed %s: feedparser reported a parse error: %s",
            feed_id,
            parsed.bozo_exception,
        )
        return []

    items: list[FeedItem] = []
    for entry in parsed.entries:
        item = _entry_to_feed_item(feed_id, entry)
        if item is not None:
            items.append(item)

    logger.debug("Feed %s: parsed %d items.", feed_id, len(items))
    return items


def _entry_to_feed_item(feed_id: str, entry: feedparser.FeedParserDict) -> FeedItem | None:
    """Convert a single feedparser entry dict into a ``FeedItem``.

    Args:
        feed_id: ID of the parent feed source.
        entry: A single entry dict from ``feedparser``.

    Returns:
        A ``FeedItem``, or ``None`` if the entry lacks a usable URL.
    """
    url: str = _extract_url(entry)
    if not url:
        logger.warning("Skipping entry with no link in feed %s.", feed_id)
        return None

    url = normalize_url(url)

    title: str = getattr(entry, "title", "") or ""
    summary: str = _extract_summary(entry)
    guid: str | None = getattr(entry, "id", None) or None
    published_at: datetime | None = _extract_published(entry)

    item_id = hash_url(url)

    return FeedItem(
        item_id=item_id,
        feed_id=feed_id,
        title=title.strip(),
        url=url,
        published_at=published_at,
        summary=summary or None,
        guid=guid,
        discovered_at=datetime.now(tz=timezone.utc),
    )


def _extract_url(entry: feedparser.FeedParserDict) -> str:
    """Return the best available URL from a feed entry."""
    if hasattr(entry, "link") and entry.link:
        return entry.link
    links = getattr(entry, "links", [])
    for link in links:
        href = link.get("href", "")
        if href:
            return href
    return ""


def _extract_summary(entry: feedparser.FeedParserDict) -> str:
    """Return the best available text summary from a feed entry."""
    summary = getattr(entry, "summary", "") or ""
    if not summary:
        content_list = getattr(entry, "content", [])
        if content_list:
            summary = content_list[0].get("value", "") or ""
    return summary.strip()


def _extract_published(entry: feedparser.FeedParserDict) -> datetime | None:
    """Return a timezone-aware UTC datetime from the feed entry's timestamp."""
    # feedparser may provide a parsed time tuple
    time_struct = getattr(entry, "published_parsed", None) or getattr(
        entry, "updated_parsed", None
    )
    if time_struct is not None:
        try:
            return parse_feed_timestamp(time_struct)
        except (TypeError, ValueError, OverflowError):
            pass

    # Fall back to raw string fields
    raw = getattr(entry, "published", None) or getattr(entry, "updated", None)
    if raw:
        try:
            from utils.time import parse_datetime_string

            return parse_datetime_string(raw)
        except (ValueError, TypeError):
            pass

    return None
