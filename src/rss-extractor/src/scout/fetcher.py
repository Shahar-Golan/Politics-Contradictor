"""
scout.fetcher
=============
Article page fetcher: downloads raw HTML from article URLs.

This module handles HTTP GET requests for individual article pages.
It records fetch metadata and returns a ``RawArticle`` record.
The fetcher does NOT perform article text extraction — that is the
job of the ``extractor`` package.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.scout.models import FeedItem, FetchStatus, RawArticle
from src.utils.config import AppSettings, HttpSettings
from src.utils.hashing import hash_url
from src.utils.urls import normalize_url

logger = logging.getLogger(__name__)

# Content-type prefixes accepted as HTML; everything else is rejected.
_ACCEPTED_CONTENT_TYPES = ("text/html", "application/xhtml")


def fetch_article(item: FeedItem, settings: AppSettings) -> RawArticle:
    """Download a single article page and return a ``RawArticle`` record.

    Follows redirects and records the final URL after any HTTP redirects.
    Non-HTML responses (PDFs, images, etc.) are returned with
    ``status=error``.

    Args:
        item: The ``FeedItem`` that references the URL to fetch.
        settings: Application settings used for HTTP configuration.

    Returns:
        A ``RawArticle`` with the fetched HTML and fetch metadata.
        On failure the ``html`` field is empty and ``status`` reflects
        the error type.
    """
    url = item.url
    # article_id is derived from the normalised *final* URL after redirects.
    # We compute it once we have the response; until then we use the original
    # URL as a fallback for early-exit error paths.
    fetched_at = datetime.now(tz=UTC)

    http = settings.http
    headers: dict[str, str] = {
        "User-Agent": http.user_agent,
        "Accept": "text/html,application/xhtml+xml",
    }

    retry_strategy = Retry(
        total=http.max_retries,
        backoff_factor=http.retry_backoff_seconds,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    logger.debug("Fetching article %s (item_id=%s).", url, item.item_id)
    try:
        response = session.get(
            url,
            headers=headers,
            timeout=http.timeout_seconds,
            allow_redirects=True,
        )
    except requests.Timeout:
        logger.warning("Timeout fetching article: %s", url)
        return RawArticle(
            article_id=hash_url(normalize_url(url)),
            feed_item_id=item.item_id,
            url=url,
            final_url=url,
            html="",
            fetched_at=fetched_at,
            status=FetchStatus.TIMEOUT,
            error_message="Request timed out.",
        )
    except requests.RequestException as exc:
        logger.error("Error fetching article %s: %s", url, exc)
        return RawArticle(
            article_id=hash_url(normalize_url(url)),
            feed_item_id=item.item_id,
            url=url,
            final_url=url,
            html="",
            fetched_at=fetched_at,
            status=FetchStatus.ERROR,
            error_message=str(exc),
        )

    final_url = response.url or url
    article_id = hash_url(normalize_url(final_url))
    content_type = response.headers.get("Content-Type", "")

    if not response.ok:
        logger.warning("Article fetch returned HTTP %s for %s.", response.status_code, url)
        return RawArticle(
            article_id=article_id,
            feed_item_id=item.item_id,
            url=url,
            final_url=final_url,
            html="",
            fetched_at=fetched_at,
            status=FetchStatus.ERROR,
            http_status_code=response.status_code,
            content_type=content_type,
            error_message=f"HTTP {response.status_code}",
        )

    # Reject non-HTML content (PDFs, images, XML feeds, etc.)
    content_type_lower = content_type.lower()
    if not any(content_type_lower.startswith(ct) for ct in _ACCEPTED_CONTENT_TYPES):
        logger.warning(
            "Unexpected content-type '%s' for %s — skipping.", content_type, url
        )
        return RawArticle(
            article_id=article_id,
            feed_item_id=item.item_id,
            url=url,
            final_url=final_url,
            html="",
            fetched_at=fetched_at,
            status=FetchStatus.ERROR,
            http_status_code=response.status_code,
            content_type=content_type,
            error_message=f"Non-HTML content-type: {content_type}",
        )

    logger.info("Fetched article %s (%d bytes).", url, len(response.content))
    return RawArticle(
        article_id=article_id,
        feed_item_id=item.item_id,
        url=url,
        final_url=final_url,
        html=response.text,
        fetched_at=fetched_at,
        status=FetchStatus.SUCCESS,
        http_status_code=response.status_code,
        content_type=content_type,
    )


def fetch_article_by_url(
    feed_item_id: str,
    url: str,
    *,
    timeout: int = 30,
) -> RawArticle:
    """Backward-compatible wrapper around :func:`fetch_article`.

    Constructs a minimal ``FeedItem`` and default ``AppSettings`` and
    delegates to the primary implementation.

    Args:
        feed_item_id: ID of the ``FeedItem`` that referenced this URL.
        url: The article URL to fetch.
        timeout: HTTP request timeout in seconds.

    Returns:
        A ``RawArticle`` as returned by :func:`fetch_article`.
    """
    from scout.models import FeedItem as _FeedItem  # avoid circular at module level

    item = _FeedItem(item_id=feed_item_id, feed_id="", title="", url=url)
    settings = AppSettings(http=HttpSettings(timeout_seconds=timeout))
    return fetch_article(item, settings)
