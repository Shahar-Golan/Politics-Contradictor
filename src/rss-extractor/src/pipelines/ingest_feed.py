"""
pipelines.ingest_feed
=====================
Feed ingestion pipeline: polls a feed, parses items, deduplicates, and persists.

This pipeline combines the Scout ``poller``, ``feed_parser``, and ``dedup``
components together with the storage layer into a single orchestrated job.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass

from src.scout.dedup import filter_new_items
from src.scout.feed_parser import parse_feed
from src.scout.models import FeedFetchLog, FeedSource, FetchStatus
from src.scout.poller import fetch_feed
from src.storage.sql import insert_feed_fetch_log, insert_feed_item, upsert_feed_source
from src.utils.config import AppSettings

logger = logging.getLogger(__name__)


@dataclass
class FeedIngestResult:
    """Result of a single feed ingestion run.

    Attributes:
        feed_id: ID of the polled feed source.
        log: Fetch log for this poll attempt.
        items_found: Total items returned by the feed.
        items_new: Items that were not previously seen and were persisted.
        items_skipped: Items filtered out as duplicates.
        status: Overall outcome of the ingestion (mirrors ``log.status``).
    """

    feed_id: str
    log: FeedFetchLog
    items_found: int
    items_new: int
    items_skipped: int
    status: FetchStatus


def ingest_feed(
    source: FeedSource,
    conn: sqlite3.Connection,
    settings: AppSettings,
) -> FeedIngestResult:
    """Run the full feed ingestion pipeline for a single feed source.

    Steps:

    1. Poll the feed URL via :func:`scout.poller.fetch_feed`.
    2. Persist the :class:`~scout.models.FeedFetchLog` regardless of outcome.
    3. If content was retrieved, parse feed items.
    4. Filter already-seen items using the database.
    5. Persist new :class:`~scout.models.FeedItem` records.

    Args:
        source: The ``FeedSource`` to ingest.
        conn: Open SQLite connection used for deduplication and persistence.
        settings: Application settings providing HTTP and pipeline config.

    Returns:
        A ``FeedIngestResult`` describing what was fetched and parsed.
    """
    # Ensure parent feed_sources row exists for FK-constrained writes.
    upsert_feed_source(conn, source)

    result = fetch_feed(source, settings)
    log = result.log
    xml_text = result.xml_text

    if xml_text is None:
        # Persist the fetch log immediately — no items to count.
        insert_feed_fetch_log(conn, log)
        logger.info(
            "Feed %s: no new content (status=%s).", source.id, log.status.value
        )
        return FeedIngestResult(
            feed_id=source.id,
            log=log,
            items_found=0,
            items_new=0,
            items_skipped=0,
            status=log.status,
        )

    all_items = parse_feed(source.id, xml_text)
    new_items = filter_new_items(conn, all_items)
    items_skipped = len(all_items) - len(new_items)

    # Update log with the actual item count before persisting.
    log.items_found = len(all_items)
    insert_feed_fetch_log(conn, log)

    for item in new_items:
        insert_feed_item(conn, item)

    logger.info(
        "Feed %s: %d total, %d new, %d duplicate(s).",
        source.id,
        len(all_items),
        len(new_items),
        items_skipped,
    )

    return FeedIngestResult(
        feed_id=source.id,
        log=log,
        items_found=len(all_items),
        items_new=len(new_items),
        items_skipped=items_skipped,
        status=log.status,
    )
