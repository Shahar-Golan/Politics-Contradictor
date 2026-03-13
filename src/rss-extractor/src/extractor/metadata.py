"""
extractor.metadata
==================
Article metadata extraction from raw HTML pages.

Extracts structured metadata fields such as title, byline, publication time,
site name, section, language, and Open Graph / JSON-LD tags.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup  # type: ignore[import]

from src.extractor.canonicalise import get_canonical_url
from src.extractor.models import ArticleMetadata
from src.utils.time import parse_datetime_string

logger = logging.getLogger(__name__)


def extract_metadata(html: str, url: str) -> ArticleMetadata:
    """Extract structured metadata from a raw HTML page.

    Attempts to read metadata from (in priority order):
    1. JSON-LD structured data
    2. Open Graph meta tags
    3. Standard HTML meta/title tags

    Args:
        html: Raw HTML content of the article page.
        url: URL of the page (used as fallback canonical URL).

    Returns:
        An ``ArticleMetadata`` record. Fields not found are ``None`` or empty.
    """
    soup = BeautifulSoup(html, "lxml")
    meta = ArticleMetadata()

    _apply_jsonld(soup, meta)
    _apply_opengraph(soup, meta)
    _apply_html_meta(soup, meta)

    # Resolve canonical URL using the dedicated helper
    meta.canonical_url = get_canonical_url(html, url)

    return meta


def _apply_jsonld(soup: BeautifulSoup, meta: ArticleMetadata) -> None:
    """Populate ``meta`` from JSON-LD structured data if present."""
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, AttributeError):
            continue

        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            _type = item.get("@type", "")
            if _type not in ("NewsArticle", "Article", "WebPage", "BlogPosting"):
                continue

            if not meta.title and item.get("headline"):
                meta.title = str(item["headline"])
            if not meta.byline:
                author = item.get("author")
                if isinstance(author, dict):
                    meta.byline = author.get("name")
                elif isinstance(author, list) and author:
                    meta.byline = author[0].get("name") if isinstance(author[0], dict) else None
                elif isinstance(author, str):
                    meta.byline = author
            if not meta.published_at and item.get("datePublished"):
                try:
                    meta.published_at = parse_datetime_string(str(item["datePublished"]))
                except (ValueError, TypeError):
                    pass
            if not meta.site_name and item.get("publisher"):
                publisher = item["publisher"]
                if isinstance(publisher, dict):
                    meta.site_name = publisher.get("name")
            break


def _apply_opengraph(soup: BeautifulSoup, meta: ArticleMetadata) -> None:
    """Populate ``meta`` from Open Graph meta tags."""
    og_tags: dict[str, str] = {}
    for tag in soup.find_all("meta", attrs={"property": re.compile(r"^(og:|article:)")}):
        prop = tag.get("property", "")
        content = tag.get("content", "")
        if prop and content:
            og_tags[prop] = content

    if not meta.title and og_tags.get("og:title"):
        meta.title = og_tags["og:title"]
    if not meta.site_name and og_tags.get("og:site_name"):
        meta.site_name = og_tags["og:site_name"]
    if not meta.published_at and og_tags.get("article:published_time"):
        try:
            meta.published_at = parse_datetime_string(og_tags["article:published_time"])
        except (ValueError, TypeError):
            pass
    if not meta.section and og_tags.get("article:section"):
        meta.section = og_tags["article:section"]


def _apply_html_meta(soup: BeautifulSoup, meta: ArticleMetadata) -> None:
    """Populate ``meta`` from standard HTML title and meta tags."""
    if not meta.title:
        title_tag = soup.find("title")
        if title_tag:
            meta.title = title_tag.get_text(strip=True)

    lang_tag = soup.find("html")
    if lang_tag and not meta.language:
        meta.language = lang_tag.get("lang") or None

    if not meta.tags:
        # Try <meta name="keywords"> first
        keywords_tag = soup.find("meta", attrs={"name": "keywords"})
        if keywords_tag:
            content = keywords_tag.get("content", "") or ""
            keyword_tags = [t.strip() for t in content.split(",") if t.strip()]
            if keyword_tags:
                meta.tags = keyword_tags
                logger.debug("Extracted %d tag(s) from <meta name='keywords'>.", len(keyword_tags))

    if not meta.tags:
        # Fall back to <meta property="article:tag"> (may appear multiple times)
        tag_metas = soup.find_all("meta", attrs={"property": "article:tag"})
        article_tags = [t.get("content", "") for t in tag_metas if t.get("content")]
        if article_tags:
            meta.tags = article_tags
            logger.debug("Extracted %d tag(s) from <meta property='article:tag'>.", len(article_tags))
