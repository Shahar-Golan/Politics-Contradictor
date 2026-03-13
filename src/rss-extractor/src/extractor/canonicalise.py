"""
extractor.canonicalise
======================
Canonical URL resolution for article pages.

Determines the preferred (canonical) URL for an article as declared in the
HTML, using ``<link rel="canonical">`` or the Open Graph ``og:url`` meta tag.
Falls back to the fetch URL when neither is present.
"""

from __future__ import annotations

import logging

from bs4 import BeautifulSoup  # type: ignore[import]

from src.utils.urls import normalise_url

logger = logging.getLogger(__name__)


def get_canonical_url(html: str, fetch_url: str) -> str:
    """Resolve the canonical URL for an article page.

    Checks HTML metadata in the following priority order:

    1. ``<link rel="canonical" href="...">``
    2. ``<meta property="og:url" content="...">``
    3. The ``fetch_url`` as a last resort.

    The result is always passed through :func:`utils.urls.normalise_url` to
    remove tracking parameters and ensure a consistent form.

    Args:
        html: Raw HTML content of the article page.
        fetch_url: URL that was used to fetch the page (used as fallback).

    Returns:
        Normalised canonical URL string.
    """
    soup = BeautifulSoup(html, "html.parser")

    # 1. <link rel="canonical">
    canonical_tag = soup.find("link", rel="canonical")
    if canonical_tag and canonical_tag.get("href"):
        return normalise_url(str(canonical_tag["href"]))

    # 2. og:url meta tag
    og_url_tag = soup.find("meta", attrs={"property": "og:url"})
    if og_url_tag and og_url_tag.get("content"):
        return normalise_url(str(og_url_tag["content"]))

    # 3. Fall back to the fetch URL
    logger.debug(
        "No canonical link or og:url found for %s; falling back to fetch URL.",
        fetch_url,
    )
    return normalise_url(fetch_url)
