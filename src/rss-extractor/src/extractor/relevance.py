"""
extractor.relevance
===================
Politician relevance scoring for extracted articles.

Determines whether a target politician is materially discussed in an article
by counting alias matches and estimating their significance.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from src.extractor.models import PoliticianMention, RelevanceLevel

logger = logging.getLogger(__name__)


@dataclass
class PoliticianConfig:
    """Minimal runtime config for a single politician.

    Attributes:
        id: Unique slug identifier.
        name: Canonical full name.
        aliases: List of name variants and nicknames.
    """

    id: str
    name: str
    aliases: list[str]


def score_relevance(
    article_id: str,
    body: str,
    title: str,
    politician: PoliticianConfig,
) -> PoliticianMention:
    """Score how relevant an article is to a given politician.

    Uses keyword matching against the article title and body.
    Title matches are weighted more heavily than body matches.

    Args:
        article_id: ID of the ``ExtractedArticle``.
        body: Clean article body text.
        title: Article headline.
        politician: Configuration for the target politician.

    Returns:
        A ``PoliticianMention`` with relevance level and score.
    """
    all_text = body.lower()
    title_lower = title.lower()

    matched_aliases: list[str] = []
    body_count = 0
    title_count = 0

    for alias in politician.aliases:
        alias_lower = alias.lower()
        pattern = re.compile(r"\b" + re.escape(alias_lower) + r"\b")

        body_matches = len(pattern.findall(all_text))
        title_matches = len(pattern.findall(title_lower))

        if body_matches > 0 or title_matches > 0:
            matched_aliases.append(alias)
            body_count += body_matches
            title_count += title_matches

    total_words = max(len(body.split()), 1)
    # Score: title match is worth 0.3 base, body mentions scale by density
    body_density = min(body_count / total_words * 500, 1.0)
    title_bonus = min(title_count * 0.15, 0.3)
    score = min(body_density + title_bonus, 1.0)

    relevance = _classify(score)

    logger.debug(
        "Politician %s relevance for article %s: %s (score=%.2f, body=%d, title=%d).",
        politician.id,
        article_id,
        relevance.value,
        score,
        body_count,
        title_count,
    )

    return PoliticianMention(
        politician_id=politician.id,
        politician_name=politician.name,
        article_id=article_id,
        relevance=relevance,
        relevance_score=round(score, 4),
        mention_count=body_count + title_count,
        matched_aliases=matched_aliases,
    )


def find_mentions(
    article_id: str,
    body: str,
    title: str,
    politicians: list[PoliticianConfig],
    min_score: float = 0.0,
) -> list[PoliticianMention]:
    """Score all politicians and return those above the minimum relevance threshold.

    Calls :func:`score_relevance` for each politician and filters the results
    to those whose ``relevance_score`` meets or exceeds ``min_score``.
    Results are sorted by descending ``relevance_score``.

    Args:
        article_id: ID of the ``ExtractedArticle``.
        body: Clean article body text.
        title: Article headline.
        politicians: List of politician configurations to evaluate.
        min_score: Minimum ``relevance_score`` (0.0–1.0) to include a mention.

    Returns:
        A list of :class:`~extractor.models.PoliticianMention` records for
        politicians whose score is ≥ ``min_score``, sorted by score descending.
    """
    mentions: list[PoliticianMention] = []
    for politician in politicians:
        mention = score_relevance(article_id, body, title, politician)
        if mention.relevance_score >= min_score:
            mentions.append(mention)
    return sorted(mentions, key=lambda m: m.relevance_score, reverse=True)


def _classify(score: float) -> RelevanceLevel:
    """Map a numeric score to a ``RelevanceLevel`` enum value.

    Thresholds:
        - ``IRRELEVANT``: score < 0.05
        - ``INCIDENTAL``: 0.05 ≤ score < 0.2
        - ``SECONDARY``: 0.2 ≤ score < 0.5
        - ``PRIMARY``: score ≥ 0.5
    """
    if score < 0.05:
        return RelevanceLevel.IRRELEVANT
    if score < 0.2:
        return RelevanceLevel.INCIDENTAL
    if score < 0.5:
        return RelevanceLevel.SECONDARY
    return RelevanceLevel.PRIMARY
