"""
scout.scheduler
===============
Polling scheduler: determines which feeds are due for a poll and when.

The scheduler is responsible for tracking the last-polled time of each feed
and deciding which feeds should be polled on a given run.
It does NOT perform the actual HTTP requests; see ``poller`` for that.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone

from src.scout.models import FeedSource
from src.utils.time import utcnow

logger = logging.getLogger(__name__)


def get_feeds_due(
    sources: list[FeedSource],
    conn: sqlite3.Connection,
) -> list[FeedSource]:
    """Return feeds that are enabled and due for a poll.

    A feed is due if it has never been polled, or if the time elapsed since
    its last poll attempt (regardless of success or failure) exceeds its
    configured ``poll_interval_minutes``.

    Disabled feeds are always excluded.

    Args:
        sources: All configured ``FeedSource`` objects.
        conn: Open SQLite connection used to look up the last fetch log.

    Returns:
        List of ``FeedSource`` objects that should be polled now.
    """
    from storage.sql import get_last_fetch_log  # avoid circular import at module level

    now = utcnow()
    due: list[FeedSource] = []

    for feed in sources:
        if not feed.enabled:
            logger.debug("Feed %s is disabled — skipping.", feed.id)
            continue

        log = get_last_fetch_log(conn, feed.id)
        if log is None:
            logger.debug("Feed %s has never been polled — marking as due.", feed.id)
            due.append(feed)
            continue

        interval = timedelta(minutes=feed.poll_interval_minutes)
        elapsed = now - log.fetched_at
        if elapsed >= interval:
            logger.debug(
                "Feed %s is overdue (elapsed=%s, interval=%s).",
                feed.id,
                elapsed,
                interval,
            )
            due.append(feed)
        else:
            logger.debug(
                "Feed %s was polled recently (elapsed=%s < interval=%s) — skipping.",
                feed.id,
                elapsed,
                interval,
            )

    logger.debug("%d feed(s) due for polling.", len(due))
    return due


class FeedScheduler:
    """Tracks poll timestamps and returns feeds that are due for polling.

    In this initial implementation, last-poll times are stored in memory.
    A future implementation can back this with a database.

    Args:
        feeds: List of all configured ``FeedSource`` objects.
    """

    def __init__(self, feeds: list[FeedSource]) -> None:
        """Initialise the scheduler with a list of feed sources."""
        self._feeds: list[FeedSource] = feeds
        # Maps feed_id -> last polled UTC datetime
        self._last_polled: dict[str, datetime] = {}

    def due_feeds(self, now: datetime | None = None) -> list[FeedSource]:
        """Return feeds that are enabled and due for a poll.

        A feed is due if it has never been polled, or if the time since its
        last poll exceeds its configured ``poll_interval_minutes``.

        Args:
            now: The current time to use for comparison. Defaults to UTC now.

        Returns:
            List of ``FeedSource`` objects that should be polled.
        """
        if now is None:
            now = datetime.now(tz=timezone.utc)

        due: list[FeedSource] = []
        for feed in self._feeds:
            if not feed.enabled:
                continue
            last = self._last_polled.get(feed.id)
            if last is None:
                due.append(feed)
            else:
                interval = timedelta(minutes=feed.poll_interval_minutes)
                if now - last >= interval:
                    due.append(feed)

        logger.debug("%d feed(s) due for polling.", len(due))
        return due

    def mark_polled(self, feed_id: str, polled_at: datetime | None = None) -> None:
        """Record that a feed has been polled.

        Args:
            feed_id: The ID of the ``FeedSource`` that was polled.
            polled_at: The time of the poll. Defaults to UTC now.
        """
        if polled_at is None:
            polled_at = datetime.now(tz=timezone.utc)
        self._last_polled[feed_id] = polled_at
        logger.debug("Marked feed %s as polled at %s.", feed_id, polled_at.isoformat())
