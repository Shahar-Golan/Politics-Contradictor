"""
selection
=========
Deterministic article selection / eligibility filtering for the
statement-processor pipeline.

Public API
----------
- :func:`~selection.article_selector.select_candidate_articles`
- :func:`~selection.scoring.score_article_for_extraction`
- :class:`~selection.models.ScoredArticle`
- :class:`~selection.models.SelectionConfig`
- :class:`~selection.models.SelectionResult`
"""

from .article_selector import select_candidate_articles
from .models import ScoredArticle, SelectionConfig, SelectionResult
from .scoring import score_article_for_extraction

__all__ = [
    "select_candidate_articles",
    "score_article_for_extraction",
    "ScoredArticle",
    "SelectionConfig",
    "SelectionResult",
]
