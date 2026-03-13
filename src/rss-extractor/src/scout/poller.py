"""
scout.poller
============
Feed poller: downloads raw RSS/Atom feed XML from configured sources.

The poller is responsible only for the HTTP fetch of feed content.
It does NOT parse the feed XML — that is the job of ``feed_parser``.
"""

from __future__ import annotations

from datetime import datetime, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.scout.models import FeedFetchLog, FeedPollResult, FeedSource, FetchStatus
from src.utils.config import AppSettings
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Default headers sent with every feed poll request
_DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": "PoliticianTracker/0.1 (research bot)",
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
}


def fetch_feed(
    source: FeedSource,
    settings: AppSettings,
    *,
    etag: str | None = None,
    last_modified: str | None = None,
) -> FeedPollResult:
    """Download the raw XML content of a single RSS/Atom feed.

    Uses the HTTP settings from ``settings`` for timeout and retry
    configuration. Supports conditional GET requests via ETag and
    Last-Modified headers to avoid re-processing unchanged feeds.

    Args:
        source: The ``FeedSource`` to poll.
        settings: Application settings providing HTTP timeout and retry config.
        etag: Previously stored ETag for conditional GET.
        last_modified: Previously stored Last-Modified for conditional GET.

    Returns:
        A ``FeedPollResult`` containing the ``FeedFetchLog`` and, when
        content was retrieved, the raw XML text.
    """
    if not source.enabled:
        logger.debug("Feed %s is disabled, skipping poll.", source.id)
        log = FeedFetchLog(
            feed_id=source.id,
            fetched_at=datetime.now(tz=timezone.utc),
            status=FetchStatus.SKIPPED,
        )
        return FeedPollResult(log=log, xml_text=None)

    headers = {
        **_DEFAULT_HEADERS,
        "User-Agent": settings.http.user_agent,
    }
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified

    retry_strategy = Retry(
        total=settings.http.max_retries,
        backoff_factor=settings.http.retry_backoff_seconds,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    fetched_at = datetime.now(tz=timezone.utc)
    logger.debug("Polling feed %s (%s).", source.id, source.url)
    try:
        response = session.get(
            source.url,
            headers=headers,
            timeout=settings.http.timeout_seconds,
        )
    except requests.Timeout:
        logger.warning("Timeout polling feed %s (%s).", source.id, source.url)
        log = FeedFetchLog(
            feed_id=source.id,
            fetched_at=fetched_at,
            status=FetchStatus.TIMEOUT,
            error_message="Request timed out.",
        )
        return FeedPollResult(log=log, xml_text=None)
    except requests.RequestException as exc:
        logger.error("Error polling feed %s: %s", source.id, exc)
        log = FeedFetchLog(
            feed_id=source.id,
            fetched_at=fetched_at,
            status=FetchStatus.ERROR,
            error_message=str(exc),
        )
        return FeedPollResult(log=log, xml_text=None)

    if response.status_code == 304:
        logger.debug("Feed %s not modified (304).", source.id)
        log = FeedFetchLog(
            feed_id=source.id,
            fetched_at=fetched_at,
            status=FetchStatus.NOT_MODIFIED,
            http_status_code=304,
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
        )
        return FeedPollResult(log=log, xml_text=None)

    if not response.ok:
        logger.warning("Feed %s returned HTTP %s.", source.id, response.status_code)
        log = FeedFetchLog(
            feed_id=source.id,
            fetched_at=fetched_at,
            status=FetchStatus.ERROR,
            http_status_code=response.status_code,
            error_message=f"HTTP {response.status_code}",
        )
        return FeedPollResult(log=log, xml_text=None)

    xml_text = response.text
    log = FeedFetchLog(
        feed_id=source.id,
        fetched_at=fetched_at,
        status=FetchStatus.SUCCESS,
        http_status_code=response.status_code,
        etag=response.headers.get("ETag"),
        last_modified=response.headers.get("Last-Modified"),
    )
    logger.info("Successfully polled feed %s (%d chars).", source.id, len(xml_text))
    return FeedPollResult(log=log, xml_text=xml_text)


def poll_feed(
    source: FeedSource,
    *,
    timeout: int = 30,
    etag: str | None = None,
    last_modified: str | None = None,
) -> tuple[FeedFetchLog, str | None]:
    """Download the raw XML content of a single RSS/Atom feed.

    Thin wrapper around :func:`fetch_feed` using default HTTP settings.
    Preserved for backward compatibility with existing pipeline code.

    Args:
        source: The ``FeedSource`` to poll.
        timeout: HTTP request timeout in seconds.
        etag: Previously stored ETag for conditional GET.
        last_modified: Previously stored Last-Modified for conditional GET.

    Returns:
        A tuple of:
        - ``FeedFetchLog`` describing the outcome of this poll.
        - The raw XML text of the feed, or ``None`` if unchanged or on error.
    """
    from utils.config import AppSettings, HttpSettings

    settings = AppSettings(http=HttpSettings(timeout_seconds=timeout))
    result = fetch_feed(source, settings, etag=etag, last_modified=last_modified)
    return result.log, result.xml_text

