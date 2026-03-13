"""
scout
=====
The Scout package is responsible for feed discovery and raw content acquisition.

Responsibilities:
- Polling configured RSS/Atom feeds
- Parsing feed XML into typed domain records
- Deduplicating feed items
- Fetching linked article pages
- Recording acquisition metadata (fetch timestamps, ETags, status codes)

This package does NOT perform text extraction, relevance scoring, or analysis.
Those responsibilities belong to the ``extractor`` package.
"""

from src.scout.models import (
    FeedFetchLog,
    FeedItem,
    FeedSource,
    FetchStatus,
    RawArticle,
)

__all__ = [
    "FeedFetchLog",
    "FeedItem",
    "FeedSource",
    "FetchStatus",
    "RawArticle",
]
