"""
storage.sql
===========
SQL/database interaction helpers for the Politician Tracker.

Provides a thin interface over SQLite for reading and writing Scout and
Extractor records.  All functions accept an open :class:`sqlite3.Connection`
and operate on the schema created by :func:`init_schema`.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from src.extractor.models import ExtractedArticle, PoliticianMention, StatementCandidate
from src.scout.models import FeedFetchLog, FeedItem, FeedSource, FetchStatus, RawArticle

logger = logging.getLogger(__name__)


def get_connection(db_path: Path | str) -> sqlite3.Connection:
    """Open and return a SQLite database connection.

    Enables WAL journal mode for better concurrency and row factory
    for dict-like row access.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        An open ``sqlite3.Connection``.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Create all required tables if they do not already exist.

    Args:
        conn: Open SQLite connection.
    """
    logger.info("Initialising database schema.")
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    logger.info("Schema initialisation complete.")


# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS feed_sources (
    id                      TEXT PRIMARY KEY,
    name                    TEXT NOT NULL,
    url                     TEXT NOT NULL,
    enabled                 INTEGER NOT NULL DEFAULT 1,
    poll_interval_minutes   INTEGER NOT NULL DEFAULT 30,
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feed_fetch_logs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    feed_id             TEXT NOT NULL REFERENCES feed_sources(id),
    fetched_at          TEXT NOT NULL,
    status              TEXT NOT NULL,
    http_status_code    INTEGER,
    etag                TEXT,
    last_modified       TEXT,
    items_found         INTEGER NOT NULL DEFAULT 0,
    error_message       TEXT
);

CREATE TABLE IF NOT EXISTS feed_items (
    item_id         TEXT PRIMARY KEY,
    feed_id         TEXT NOT NULL REFERENCES feed_sources(id),
    title           TEXT NOT NULL,
    url             TEXT NOT NULL,
    published_at    TEXT,
    summary         TEXT,
    guid            TEXT,
    discovered_at   TEXT NOT NULL,
    fetched         INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS raw_articles (
    article_id      TEXT PRIMARY KEY,
    feed_item_id    TEXT NOT NULL REFERENCES feed_items(item_id),
    url             TEXT NOT NULL,
    final_url       TEXT NOT NULL,
    html_path       TEXT NOT NULL,
    fetched_at      TEXT NOT NULL,
    status          TEXT NOT NULL,
    http_status_code INTEGER,
    content_type    TEXT,
    error_message   TEXT
);

CREATE TABLE IF NOT EXISTS extracted_articles (
    article_id          TEXT PRIMARY KEY REFERENCES raw_articles(article_id),
    url                 TEXT NOT NULL,
    title               TEXT NOT NULL DEFAULT '',
    body_path           TEXT NOT NULL,
    word_count          INTEGER NOT NULL DEFAULT 0,
    extraction_backend  TEXT NOT NULL DEFAULT '',
    extracted_at        TEXT NOT NULL,
    language            TEXT,
    byline              TEXT,
    published_at        TEXT,
    site_name           TEXT,
    canonical_url       TEXT
);

CREATE TABLE IF NOT EXISTS politician_mentions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    politician_id   TEXT NOT NULL,
    article_id      TEXT NOT NULL REFERENCES extracted_articles(article_id),
    relevance       TEXT NOT NULL,
    relevance_score REAL NOT NULL,
    mention_count   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS statement_candidates (
    statement_id    TEXT PRIMARY KEY,
    article_id      TEXT NOT NULL REFERENCES extracted_articles(article_id),
    politician_id   TEXT NOT NULL,
    text            TEXT NOT NULL,
    is_direct_quote INTEGER NOT NULL DEFAULT 0,
    context         TEXT NOT NULL DEFAULT '',
    char_offset     INTEGER
);

-- Indexes on common query / foreign-key fields for fast lookups.
CREATE INDEX IF NOT EXISTS idx_feed_fetch_logs_feed_id
    ON feed_fetch_logs(feed_id);

CREATE INDEX IF NOT EXISTS idx_feed_items_feed_id
    ON feed_items(feed_id);

CREATE INDEX IF NOT EXISTS idx_raw_articles_feed_item_id
    ON raw_articles(feed_item_id);

CREATE INDEX IF NOT EXISTS idx_politician_mentions_article_id
    ON politician_mentions(article_id);

CREATE INDEX IF NOT EXISTS idx_politician_mentions_politician_id
    ON politician_mentions(politician_id);

CREATE INDEX IF NOT EXISTS idx_statement_candidates_article_id
    ON statement_candidates(article_id);

CREATE INDEX IF NOT EXISTS idx_statement_candidates_politician_id
    ON statement_candidates(politician_id);
"""


# ---------------------------------------------------------------------------
# Feed source persistence
# ---------------------------------------------------------------------------


def upsert_feed_source(conn: sqlite3.Connection, source: FeedSource) -> None:
    """Insert or update a ``FeedSource`` in the ``feed_sources`` table.

    Ensures parent feed rows exist before inserting FK-dependent records such
    as ``feed_fetch_logs`` and ``feed_items``.

    Args:
        conn: Open SQLite connection.
        source: Feed source metadata to persist.
    """
    now_iso = datetime.now(tz=UTC).isoformat()
    conn.execute(
        """
        INSERT INTO feed_sources
            (id, name, url, enabled, poll_interval_minutes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            url = excluded.url,
            enabled = excluded.enabled,
            poll_interval_minutes = excluded.poll_interval_minutes,
            updated_at = excluded.updated_at
        """,
        (
            source.id,
            source.name,
            source.url,
            int(source.enabled),
            source.poll_interval_minutes,
            now_iso,
            now_iso,
        ),
    )
    conn.commit()
    logger.debug("Upserted feed source %s.", source.id)


def get_feed_source_name(conn: sqlite3.Connection, feed_id: str) -> str | None:
    """Return the display name of a feed source, or ``None`` if not found.

    Args:
        conn: Open SQLite connection.
        feed_id: The unique feed source identifier.

    Returns:
        The feed source name, or ``None`` if no matching record exists.
    """
    row = conn.execute(
        "SELECT name FROM feed_sources WHERE id = ?",
        (feed_id,),
    ).fetchone()
    if row and row["name"]:
        return row["name"]
    return None


# ---------------------------------------------------------------------------
# Feed fetch log persistence
# ---------------------------------------------------------------------------


def insert_feed_fetch_log(conn: sqlite3.Connection, log: FeedFetchLog) -> None:
    """Persist a ``FeedFetchLog`` record to the ``feed_fetch_logs`` table.

    Args:
        conn: Open SQLite connection.
        log: The fetch log to insert.
    """
    conn.execute(
        """
        INSERT INTO feed_fetch_logs
            (feed_id, fetched_at, status, http_status_code, etag,
             last_modified, items_found, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            log.feed_id,
            log.fetched_at.isoformat(),
            log.status.value,
            log.http_status_code,
            log.etag,
            log.last_modified,
            log.items_found,
            log.error_message,
        ),
    )
    conn.commit()
    logger.debug("Inserted feed fetch log for feed %s (status=%s).", log.feed_id, log.status.value)


def get_last_fetch_log(conn: sqlite3.Connection, feed_id: str) -> FeedFetchLog | None:
    """Return the most recent ``FeedFetchLog`` for a given feed, or ``None``.

    Args:
        conn: Open SQLite connection.
        feed_id: ID of the ``FeedSource`` to look up.

    Returns:
        The most recent ``FeedFetchLog`` for ``feed_id``, or ``None`` if no
        records exist for that feed.
    """
    row = conn.execute(
        """
        SELECT feed_id, fetched_at, status, http_status_code, etag,
               last_modified, items_found, error_message
        FROM   feed_fetch_logs
        WHERE  feed_id = ?
        ORDER  BY fetched_at DESC
        LIMIT  1
        """,
        (feed_id,),
    ).fetchone()

    if row is None:
        return None

    fetched_at_raw: str = row["fetched_at"]
    fetched_at = datetime.fromisoformat(fetched_at_raw)
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=UTC)

    return FeedFetchLog(
        feed_id=row["feed_id"],
        fetched_at=fetched_at,
        status=FetchStatus(row["status"]),
        http_status_code=row["http_status_code"],
        etag=row["etag"],
        last_modified=row["last_modified"],
        items_found=row["items_found"] or 0,
        error_message=row["error_message"],
    )


# ---------------------------------------------------------------------------
# Feed item persistence
# ---------------------------------------------------------------------------


def insert_feed_item(conn: sqlite3.Connection, item: FeedItem) -> None:
    """Persist a ``FeedItem`` record to the ``feed_items`` table.

    Uses ``INSERT OR IGNORE`` so concurrent inserts or duplicate calls
    are silently ignored without raising an integrity error.

    Args:
        conn: Open SQLite connection.
        item: The feed item to insert.
    """
    conn.execute(
        """
        INSERT OR IGNORE INTO feed_items
            (item_id, feed_id, title, url, published_at, summary, guid, discovered_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item.item_id,
            item.feed_id,
            item.title,
            item.url,
            item.published_at.isoformat() if item.published_at else None,
            item.summary,
            item.guid,
            item.discovered_at.isoformat(),
        ),
    )
    conn.commit()
    logger.debug("Inserted feed item %s (feed=%s).", item.item_id, item.feed_id)


def get_feed_item(conn: sqlite3.Connection, item_id: str) -> FeedItem | None:
    """Return a ``FeedItem`` by its ID, or ``None`` if not found.

    Args:
        conn: Open SQLite connection.
        item_id: The unique item fingerprint hash to look up.

    Returns:
        The matching ``FeedItem``, or ``None`` if no record exists.
    """
    row = conn.execute(
        """
        SELECT item_id, feed_id, title, url, published_at, summary, guid, discovered_at
        FROM   feed_items
        WHERE  item_id = ?
        """,
        (item_id,),
    ).fetchone()

    if row is None:
        return None

    published_at = None
    if row["published_at"]:
        published_at = datetime.fromisoformat(row["published_at"])
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=UTC)

    discovered_at = datetime.fromisoformat(row["discovered_at"])
    if discovered_at.tzinfo is None:
        discovered_at = discovered_at.replace(tzinfo=UTC)

    return FeedItem(
        item_id=row["item_id"],
        feed_id=row["feed_id"],
        title=row["title"],
        url=row["url"],
        published_at=published_at,
        summary=row["summary"],
        guid=row["guid"],
        discovered_at=discovered_at,
    )


# ---------------------------------------------------------------------------
# Raw article persistence
# ---------------------------------------------------------------------------


def insert_raw_article(
    conn: sqlite3.Connection,
    article: RawArticle,
    html_path: str,
) -> None:
    """Persist a ``RawArticle`` record to the ``raw_articles`` table.

    Uses ``INSERT OR IGNORE`` so duplicate calls for the same ``article_id``
    are silently skipped without raising an integrity error.

    Args:
        conn: Open SQLite connection.
        article: The raw article fetch record to insert.
        html_path: Path to the HTML file on disk (already written by the caller).
    """
    conn.execute(
        """
        INSERT OR IGNORE INTO raw_articles
            (article_id, feed_item_id, url, final_url, html_path,
             fetched_at, status, http_status_code, content_type, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            article.article_id,
            article.feed_item_id,
            article.url,
            article.final_url,
            html_path,
            article.fetched_at.isoformat(),
            article.status.value,
            article.http_status_code,
            article.content_type,
            article.error_message,
        ),
    )
    conn.commit()
    logger.debug("Inserted raw article %s (status=%s).", article.article_id, article.status.value)


# ---------------------------------------------------------------------------
# Extracted article persistence
# ---------------------------------------------------------------------------


def insert_extracted_article(
    conn: sqlite3.Connection,
    article: ExtractedArticle,
    body_path: str,
) -> None:
    """Persist an ``ExtractedArticle`` record to the ``extracted_articles`` table.

    Uses ``INSERT OR REPLACE`` so re-extraction updates the existing record.

    Args:
        conn: Open SQLite connection.
        article: The extracted article record to insert.
        body_path: Path to the extracted body text file on disk.
    """
    meta = article.metadata
    conn.execute(
        """
        INSERT OR REPLACE INTO extracted_articles
            (article_id, url, title, body_path, word_count, extraction_backend,
             extracted_at, language, byline, published_at, site_name, canonical_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            article.article_id,
            article.url,
            meta.title,
            body_path,
            article.word_count,
            article.extraction_backend,
            article.extracted_at.isoformat(),
            meta.language,
            meta.byline,
            meta.published_at.isoformat() if meta.published_at else None,
            meta.site_name,
            meta.canonical_url,
        ),
    )
    conn.commit()
    logger.debug("Inserted extracted article %s.", article.article_id)


# ---------------------------------------------------------------------------
# Politician mention persistence
# ---------------------------------------------------------------------------


def insert_politician_mention(
    conn: sqlite3.Connection,
    mention: PoliticianMention,
) -> None:
    """Persist a ``PoliticianMention`` record to the ``politician_mentions`` table.

    Args:
        conn: Open SQLite connection.
        mention: The politician mention record to insert.
    """
    conn.execute(
        """
        INSERT INTO politician_mentions
            (politician_id, article_id, relevance, relevance_score, mention_count)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            mention.politician_id,
            mention.article_id,
            mention.relevance.value,
            mention.relevance_score,
            mention.mention_count,
        ),
    )
    conn.commit()
    logger.debug(
        "Inserted politician mention for %s in article %s (relevance=%s).",
        mention.politician_id,
        mention.article_id,
        mention.relevance.value,
    )


# ---------------------------------------------------------------------------
# Statement candidate persistence
# ---------------------------------------------------------------------------


def insert_statement_candidate(
    conn: sqlite3.Connection,
    statement: StatementCandidate,
) -> None:
    """Persist a ``StatementCandidate`` record to the ``statement_candidates`` table.

    Uses ``INSERT OR IGNORE`` so duplicate statement hashes are silently skipped.

    Args:
        conn: Open SQLite connection.
        statement: The statement candidate record to insert.
    """
    conn.execute(
        """
        INSERT OR IGNORE INTO statement_candidates
            (statement_id, article_id, politician_id, text,
             is_direct_quote, context, char_offset)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            statement.statement_id,
            statement.article_id,
            statement.politician_id,
            statement.text,
            int(statement.is_direct_quote),
            statement.context,
            statement.char_offset,
        ),
    )
    conn.commit()
    logger.debug(
        "Inserted statement candidate %s for politician %s.",
        statement.statement_id,
        statement.politician_id,
    )


# ---------------------------------------------------------------------------
# Pending fetch query
# ---------------------------------------------------------------------------


def get_feed_items_pending_fetch(
    conn: sqlite3.Connection,
    limit: int = 0,
) -> list[FeedItem]:
    """Return feed items that have not yet been fetched.

    Uses a ``LEFT JOIN`` to find ``feed_items`` rows with no matching record
    in ``raw_articles``.

    Args:
        conn: Open SQLite connection.
        limit: Maximum number of records to return (0 means no limit).

    Returns:
        A list of ``FeedItem`` objects that do not yet have a corresponding
        ``raw_articles`` record.
    """
    query = """
        SELECT fi.item_id, fi.feed_id, fi.title, fi.url, fi.published_at,
               fi.summary, fi.guid, fi.discovered_at
        FROM   feed_items fi
        LEFT   JOIN raw_articles ra ON fi.item_id = ra.feed_item_id
        WHERE  ra.article_id IS NULL
    """
    params: tuple[int, ...] = ()
    if limit > 0:
        query += " LIMIT ?"
        params = (limit,)

    rows = conn.execute(query, params).fetchall()
    items: list[FeedItem] = []
    for row in rows:
        published_at = None
        if row["published_at"]:
            published_at = datetime.fromisoformat(row["published_at"])
            if published_at.tzinfo is None:
                published_at = published_at.replace(tzinfo=UTC)

        discovered_at = datetime.fromisoformat(row["discovered_at"])
        if discovered_at.tzinfo is None:
            discovered_at = discovered_at.replace(tzinfo=UTC)

        items.append(
            FeedItem(
                item_id=row["item_id"],
                feed_id=row["feed_id"],
                title=row["title"],
                url=row["url"],
                published_at=published_at,
                summary=row["summary"],
                guid=row["guid"],
                discovered_at=discovered_at,
            )
        )
    return items


# ---------------------------------------------------------------------------
# Pending extraction query
# ---------------------------------------------------------------------------


def get_raw_articles_pending_extraction(
    conn: sqlite3.Connection,
    limit: int = 0,
) -> list[RawArticle]:
    """Return raw articles that have not yet been extracted.

    Uses a ``LEFT JOIN`` to find ``raw_articles`` rows with no matching record
    in ``extracted_articles``.  The HTML content is not stored in the database;
    callers should load it from the document store using each article's
    ``article_id``.  The returned ``RawArticle`` objects have ``html`` set to
    an empty string as a placeholder.

    Args:
        conn: Open SQLite connection.
        limit: Maximum number of records to return (0 means no limit).

    Returns:
        A list of ``RawArticle`` objects (with ``html=""``) for articles that
        do not yet have a corresponding ``extracted_articles`` record.
    """
    query = """
        SELECT ra.article_id, ra.feed_item_id, ra.url, ra.final_url,
               ra.fetched_at, ra.status, ra.http_status_code,
               ra.content_type, ra.error_message
        FROM   raw_articles ra
        LEFT   JOIN extracted_articles ea ON ra.article_id = ea.article_id
        WHERE  ea.article_id IS NULL
          AND  ra.status = 'success'
    """
    params: tuple[int, ...] = ()
    if limit > 0:
        query += " LIMIT ?"
        params = (limit,)

    rows = conn.execute(query, params).fetchall()
    articles: list[RawArticle] = []
    for row in rows:
        fetched_at = datetime.fromisoformat(row["fetched_at"])
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=UTC)

        articles.append(
            RawArticle(
                article_id=row["article_id"],
                feed_item_id=row["feed_item_id"],
                url=row["url"],
                final_url=row["final_url"],
                html="",  # HTML is not stored in the DB; load from document store.
                fetched_at=fetched_at,
                status=FetchStatus(row["status"]),
                http_status_code=row["http_status_code"],
                content_type=row["content_type"],
                error_message=row["error_message"],
            )
        )
    return articles
