"""
extractor.topics
================
Lightweight keyword-based topic tagger for extracted articles.

Assigns topic labels from the configured taxonomy to an article based on
keyword matching in the title and body text.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TopicConfig:
    """A single topic definition from ``config/topics.yaml``.

    Attributes:
        id: Unique slug identifier.
        label: Human-readable label.
        keywords: Keywords/phrases associated with this topic.
    """

    id: str
    label: str
    keywords: list[str]


def tag_article(
    text: str,
    topics: dict[str, list[str]],
) -> list[str]:
    """Assign topic IDs to an article based on keyword matching.

    Accepts the ``dict[str, list[str]]`` mapping returned by
    :func:`utils.config.load_topics` directly, making it straightforward to
    combine config loading with topic tagging.

    Args:
        text: Article text to search (typically title and body concatenated).
        topics: Mapping of topic ID → list of keyword strings.

    Returns:
        A sorted list of matched topic IDs.
    """
    text_lower = text.lower()
    matched: list[str] = []

    for topic_id, keywords in topics.items():
        for keyword in keywords:
            pattern = re.compile(r"\b" + re.escape(keyword.lower()) + r"\b")
            if pattern.search(text_lower):
                matched.append(topic_id)
                logger.debug("Topic '%s' matched via keyword '%s'.", topic_id, keyword)
                break

    return sorted(matched)


def tag_topics(
    title: str,
    body: str,
    topics: list[TopicConfig],
) -> list[str]:
    """Assign topic IDs to an article based on keyword matching.

    Checks both the title and body for keyword matches. A topic is assigned
    if at least one of its keywords is found. Title matches count regardless
    of how many times they appear; body matches require at least one hit.

    Args:
        title: Article headline.
        body: Clean article body text.
        topics: List of ``TopicConfig`` objects from the taxonomy.

    Returns:
        A sorted list of matched topic IDs.
    """
    combined = f"{title} {body}".lower()
    matched: list[str] = []

    for topic in topics:
        for keyword in topic.keywords:
            pattern = re.compile(r"\b" + re.escape(keyword.lower()) + r"\b")
            if pattern.search(combined):
                matched.append(topic.id)
                logger.debug("Topic '%s' matched via keyword '%s'.", topic.id, keyword)
                break

    return sorted(matched)
