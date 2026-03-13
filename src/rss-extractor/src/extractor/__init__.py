"""
extractor
=========
The Extractor package transforms raw HTML pages into structured article records.

Responsibilities:
- Canonical URL resolution
- Article body extraction from raw HTML
- Text cleaning and normalization
- Metadata extraction (title, byline, date, section, tags)
- Politician relevance scoring
- Quote and statement candidate extraction
- Lightweight topic tagging

This package does NOT perform feed polling, HTTP fetching, or scheduling.
Those responsibilities belong to the ``scout`` package.
"""

from src.extractor.models import (
    ArticleMetadata,
    ExtractedArticle,
    PoliticianMention,
    RelevanceLevel,
    StatementCandidate,
)
from src.extractor.quotes import extract_statements

__all__ = [
    "ArticleMetadata",
    "ExtractedArticle",
    "PoliticianMention",
    "RelevanceLevel",
    "StatementCandidate",
    "extract_statements",
]
