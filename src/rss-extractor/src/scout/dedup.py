"""
scout.dedup
===========
Deduplication helpers for RSS feed items.

Provides functions to determine whether a ``FeedItem`` has already been seen,
based on a fingerprint derived from its URL and/or title.
"""

from __future__ import annotations

import logging
import sqlite3

from src.scout.models import FeedItem

logger = logging.getLogger(__name__)


class InMemoryDeduplicator:
    """Simple in-memory deduplicator backed by a set of known item IDs.

    Suitable for single-run or testing scenarios. For persistent deduplication
    across runs, use a database-backed implementation.
    """

    def __init__(self) -> None:
        """Initialise with an empty set of seen item IDs."""
        self._seen: set[str] = set()

    def is_duplicate(self, item: FeedItem) -> bool:
        """Return True if this item's ID has been seen before.

        Args:
            item: The ``FeedItem`` to check.

        Returns:
            ``True`` if the item is a duplicate, ``False`` otherwise.
        """
        return item.item_id in self._seen

    def mark_seen(self, item: FeedItem) -> None:
        """Record an item ID as seen.

        Args:
            item: The ``FeedItem`` to mark as processed.
        """
        self._seen.add(item.item_id)

    def filter_new(self, items: list[FeedItem]) -> list[FeedItem]:
        """Filter a list of items, returning only those not yet seen.

        Side effect: marks all returned items as seen.

        Args:
            items: Candidate ``FeedItem`` records.

        Returns:
            A list containing only previously-unseen items.
        """
        new_items: list[FeedItem] = []
        for item in items:
            if not self.is_duplicate(item):
                new_items.append(item)
                self.mark_seen(item)
            else:
                logger.debug("Duplicate item skipped: %s", item.url)
        logger.debug("%d new / %d duplicates in batch.", len(new_items), len(items) - len(new_items))
        return new_items


def deduplicate(items: list[FeedItem], seen_ids: set[str]) -> list[FeedItem]:
    """Return items whose IDs are not in ``seen_ids``.

    This is a stateless helper for use with external ID registries
    (e.g. loaded from a database).

    Args:
        items: Candidate ``FeedItem`` records.
        seen_ids: Set of already-processed item IDs.

    Returns:
        Items not present in ``seen_ids``.
    """
    return [item for item in items if item.item_id not in seen_ids]


def filter_new_items(conn: sqlite3.Connection, items: list[FeedItem]) -> list[FeedItem]:
    """Return only items whose ``item_id`` is not already in the database.

    Uses a single bulk ``IN`` query for efficiency rather than one lookup
    per item.  Already-seen items are silently skipped.

    Args:
        conn: Open SQLite connection with the ``feed_items`` table present.
        items: Candidate ``FeedItem`` records to check.

    Returns:
        The subset of ``items`` not already stored in ``feed_items``.
    """
    if not items:
        return []

    candidate_ids = [item.item_id for item in items]
    placeholders = ",".join("?" * len(candidate_ids))
    # The f-string only interpolates a repeated "?" placeholder string derived
    # from the count of items — no user-supplied data enters the SQL text.
    rows = conn.execute(
        f"SELECT item_id FROM feed_items WHERE item_id IN ({placeholders})",  # noqa: S608
        candidate_ids,
    ).fetchall()
    existing_ids = {row["item_id"] for row in rows}

    new_items = [item for item in items if item.item_id not in existing_ids]
    duplicate_count = len(items) - len(new_items)

    logger.info(
        "%d new / %d duplicate item(s) in batch.",
        len(new_items),
        duplicate_count,
    )
    return new_items
