"""
extractor.article_extractor
============================
Main orchestrator for extracting clean article text and metadata from raw HTML.

This module coordinates the extraction pipeline:
1. Extract raw text using the configured backend (Trafilatura preferred).
2. Clean and normalise the extracted text.
3. Extract page metadata (title, byline, dates, etc.).
4. Resolve the canonical URL.

The result is an ``ExtractedArticle`` ready for relevance scoring and
statement extraction.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone

from src.extractor.canonicalise import get_canonical_url
from src.extractor.cleaner import clean_text
from src.extractor.metadata import extract_metadata
from src.extractor.models import ArticleMetadata, ExtractedArticle
from src.scout.models import RawArticle
from src.utils.config import AppSettings

logger = logging.getLogger(__name__)


def extract_article(raw: RawArticle, settings: AppSettings) -> ExtractedArticle:
    """Extract clean text and metadata from a raw HTML page.

    Attempts extraction using the backend configured in ``settings``. Falls back
    to BeautifulSoup-based extraction if the preferred backend yields
    insufficient content. If all backends fail, returns a partial
    ``ExtractedArticle`` with an empty body and logs a warning.

    Args:
        raw: The fetched ``RawArticle`` containing HTML content and fetch metadata.
        settings: Application settings (controls backend, min body length, etc.).

    Returns:
        An ``ExtractedArticle``. The ``body`` field is empty if extraction fails.
    """
    url = raw.final_url or raw.url
    html = raw.html
    min_length = settings.extraction.min_body_length
    preferred_backend = settings.extraction.preferred_backend

    body, used_backend = _extract_body(html, url, preferred_backend, min_length)

    if not body:
        logger.warning(
            "Extraction yielded insufficient content for %s (all backends exhausted).",
            url,
        )
        metadata = extract_metadata(html, url)
        metadata.canonical_url = get_canonical_url(html, url)
        return ExtractedArticle(
            article_id=raw.article_id,
            url=url,
            body="",
            metadata=metadata,
            word_count=0,
            extraction_backend="none",
            extracted_at=datetime.now(tz=timezone.utc),
        )

    body = clean_text(body)
    metadata = extract_metadata(html, url)
    metadata.canonical_url = get_canonical_url(html, url)
    word_count = len(body.split())

    logger.debug(
        "Extracted article %s using backend %s (%d words).",
        url,
        used_backend,
        word_count,
    )

    return ExtractedArticle(
        article_id=raw.article_id,
        url=url,
        body=body,
        metadata=metadata,
        word_count=word_count,
        extraction_backend=used_backend,
        extracted_at=datetime.now(tz=timezone.utc),
    )


def _extract_body(html: str, url: str, backend: str, min_length: int) -> tuple[str, str]:
    """Attempt to extract the article body using the given backend.

    Falls back through available backends if the primary one fails.

    Args:
        html: Raw HTML content.
        url: Page URL (used by some backends for context).
        backend: Preferred extraction backend name.
        min_length: Minimum character length to consider an extraction valid.

    Returns:
        A tuple of (extracted body text, name of backend actually used).
        Returns ``("", "none")`` if no backend produces sufficient content.
    """
    extractors = _ordered_extractors(backend)
    for name, fn in extractors:
        try:
            result = fn(html, url)
            if result:
                result_len = len(result)
                if result_len >= min_length:
                    return result, name
        except Exception as exc:  # noqa: BLE001
            logger.debug("Backend %s failed for %s: %s", name, url, exc)

    return "", "none"


def _ordered_extractors(preferred: str) -> list[tuple[str, Callable[[str, str], str]]]:
    """Return extractors in order of preference, with preferred first."""
    all_extractors: dict[str, Callable[[str, str], str]] = {
        "trafilatura": _extract_with_trafilatura,
        "beautifulsoup": _extract_with_beautifulsoup,
    }
    ordered: list[tuple[str, Callable[[str, str], str]]] = (
        [(preferred, all_extractors[preferred])] if preferred in all_extractors else []
    )
    for name, fn in all_extractors.items():
        if name != preferred:
            ordered.append((name, fn))
    return ordered


def _extract_with_trafilatura(html: str, url: str) -> str:
    """Extract article text using the Trafilatura library."""
    try:
        import trafilatura  # type: ignore[import]

        result = trafilatura.extract(html, url=url, include_comments=False, include_tables=False)
        return result or ""
    except ImportError:
        logger.debug("Trafilatura not installed.")
        return ""


def _extract_with_beautifulsoup(html: str, url: str) -> str:
    """Extract article text using BeautifulSoup as a fallback."""
    from bs4 import BeautifulSoup  # type: ignore[import]

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()

    article_tag = soup.find("article") or soup.find("main") or soup.body
    if article_tag is None:
        return ""

    paragraphs = article_tag.find_all("p")
    text = "\n\n".join(p.get_text(separator=" ", strip=True) for p in paragraphs)
    return text
