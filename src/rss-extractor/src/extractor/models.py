"""
extractor.models
================
Typed domain models for the Extractor output layer.

These dataclasses represent the structured records produced after raw HTML
has been processed: extracted articles, politician mentions, and statement
candidates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class RelevanceLevel(str, Enum):
    """How materially a target politician figures in an article."""

    PRIMARY = "primary"        # Politician is the main subject
    SECONDARY = "secondary"    # Politician is a significant but secondary subject
    INCIDENTAL = "incidental"  # Politician is briefly mentioned
    IRRELEVANT = "irrelevant"  # Politician is not meaningfully present


@dataclass
class ArticleMetadata:
    """Structured metadata extracted from an article page.

    Attributes:
        title: Article headline.
        byline: Author name(s) as a string, if present.
        published_at: Normalised publication datetime, if found.
        site_name: Name of the publishing site.
        section: Section or category label from the page, if any.
        language: BCP-47 language tag detected in the page (e.g. "en").
        tags: Topic tags or keywords extracted from the page metadata.
        canonical_url: The canonical URL for the article, if provided.
    """

    title: str = ""
    byline: str | None = None
    published_at: datetime | None = None
    site_name: str | None = None
    section: str | None = None
    language: str | None = None
    tags: list[str] = field(default_factory=list)
    canonical_url: str | None = None


@dataclass
class ExtractedArticle:
    """A fully extracted and normalised article record.

    This is the primary output of the Extractor pipeline stage.

    Attributes:
        article_id: Fingerprint hash matching the ``RawArticle``.
        url: Final resolved URL of the article.
        body: Clean, extracted article body text.
        metadata: Structured metadata from the page.
        word_count: Number of words in the extracted body.
        extraction_backend: Name of the extraction library used.
        extracted_at: UTC timestamp when extraction was performed.
    """

    article_id: str
    url: str
    body: str
    metadata: ArticleMetadata
    word_count: int = 0
    extraction_backend: str = ""
    extracted_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


@dataclass
class PoliticianMention:
    """A record of a politician being mentioned in an extracted article.

    Attributes:
        politician_id: ID from ``config/politicians.yaml``.
        politician_name: Canonical name of the politician.
        article_id: ID of the ``ExtractedArticle`` containing the mention.
        relevance: How prominently the politician features in the article.
        relevance_score: Numeric score in the range 0.0–1.0.
        mention_count: How many times the politician is mentioned.
        matched_aliases: Which name aliases were found in the text.
    """

    politician_id: str
    politician_name: str
    article_id: str
    relevance: RelevanceLevel
    relevance_score: float
    mention_count: int = 0
    matched_aliases: list[str] = field(default_factory=list)


@dataclass
class StatementCandidate:
    """A candidate quote or statement attributed to a politician.

    Attributes:
        statement_id: Deterministic hash of the statement text.
        article_id: ID of the source ``ExtractedArticle``.
        politician_id: ID of the attributed politician.
        text: The raw text of the statement or quote.
        is_direct_quote: True if the statement appears to be a direct quote.
        context: The surrounding sentence(s) providing attribution context.
        char_offset: Character offset in the article body where the statement begins.
    """

    statement_id: str
    article_id: str
    politician_id: str
    text: str
    is_direct_quote: bool = False
    context: str = ""
    char_offset: int | None = None
