"""
selection.models
================
Typed data models for the article selection layer.

All classes are dataclasses so they are lightweight, comparable, and easy
to serialise to dicts/JSON for downstream consumers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True, order=True)
class ScoredArticle:
    """A single article together with its selection score and rule matches.

    Attributes
    ----------
    doc_id:
        Unique article identifier (matches ``news_articles.doc_id``).
    title:
        Article headline, or ``None`` if not available.
    matched_politician:
        Canonical politician name that triggered this article's selection.
    score:
        Integer eligibility score.  Higher scores indicate a stronger
        signal that the article contains meaningful stance content.
        A score of 0 means the article passed the minimum politician-filter
        but had no additional positive signals.
    matched_rules:
        Ordered list of human-readable rule names that contributed to the
        score.  Useful for inspection and debugging.
    is_eligible:
        ``True`` when ``score >= SelectionConfig.min_score``.
    """

    doc_id: str
    title: Optional[str]
    matched_politician: str
    score: int
    matched_rules: tuple[str, ...]
    is_eligible: bool


@dataclass
class SelectionConfig:
    """Configuration for the article selection process.

    All fields have sensible defaults that can be overridden by callers.

    Attributes
    ----------
    politicians:
        Sequence of canonical politician names to filter by.  Must match
        keys in :data:`~selection.keywords.POLITICIAN_ALIASES`.
        Defaults to ``["Trump", "Biden"]``.
    min_score:
        Minimum score threshold for an article to be considered eligible.
        Articles with a score below this threshold are included in the
        result set but flagged as ``is_eligible=False``.
        Defaults to ``1`` (at least one positive signal beyond the base
        politician mention).
    max_results:
        Maximum number of eligible articles to return.  ``None`` means no
        limit.  Applied after scoring and sorting, so the highest-scoring
        articles are returned first.
        Defaults to ``None``.
    min_text_length:
        Articles whose ``text`` is shorter than this threshold (characters)
        are penalised.  Defaults to
        :data:`~selection.keywords.MIN_TEXT_LENGTH`.
    date_from:
        Optional ISO-8601 date string (``YYYY-MM-DD``) to restrict
        articles to those published on or after this date.
    date_to:
        Optional ISO-8601 date string (``YYYY-MM-DD``) to restrict
        articles to those published on or before this date.
    """

    politicians: list[str] = field(default_factory=lambda: ["Trump", "Biden"])
    min_score: int = 1
    max_results: Optional[int] = None
    min_text_length: int = 150
    date_from: Optional[str] = None
    date_to: Optional[str] = None


@dataclass
class SelectionResult:
    """Aggregated output from a single run of the article selector.

    Attributes
    ----------
    articles:
        All scored articles, sorted by ``score`` descending.  Includes
        both eligible and ineligible results so callers can inspect the
        full picture.
    config:
        The :class:`SelectionConfig` used for this run.
    total_candidates:
        Number of articles that passed the initial politician filter
        before scoring.
    eligible_count:
        Number of articles that met the ``min_score`` threshold.
    """

    articles: list[ScoredArticle]
    config: SelectionConfig
    total_candidates: int
    eligible_count: int

    @property
    def eligible_articles(self) -> list[ScoredArticle]:
        """Return only articles flagged as eligible."""
        return [a for a in self.articles if a.is_eligible]
