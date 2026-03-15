"""
agents.recent_news_builder
==========================
LLM-powered recent-news summariser for the RSS ingestion pipeline.

For each politician with newly ingested articles, this module calls an LLM to
generate a set of concise key points that highlight the most important recent
developments.  Each key point is backed by citation(s) to source articles.

The resulting data is designed to populate the ``recent_news`` field in the
``figure_pages`` Supabase table (Phase 4), and is also written to a standalone
JSON output file for inspection after each pipeline run.

Usage
-----
::

    from src.agents.recent_news_builder import build_recent_news
    from src.agents.profile_updater import ArticleForProfile

    articles_by_politician = {
        "donald-trump": ("Donald Trump", [ArticleForProfile(...)]),
    }
    news = build_recent_news(
        articles_by_politician=articles_by_politician,
        openai_api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        gpt_model=os.environ.get("GPT_MODEL", "gpt-4o-mini"),
    )
    # news == {"Donald Trump": [RecentNewsItem(point="...", article_refs=[...])]}
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from src.agents.profile_updater import ArticleForProfile, build_articles_text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM prompt
# ---------------------------------------------------------------------------

_RECENT_NEWS_PROMPT = """\
You are a political intelligence analyst. Summarise the most important recent
news about {politician_name} based on the articles listed below.

Articles:
---
{articles_text}
---

Generate between 3 and 7 concise key points. Each key point must:
- Highlight a specific, newsworthy development or piece of information about
  {politician_name}.
- Be written as a single, complete sentence.
- Be backed by at least one of the source articles above.

Respond ONLY with a valid JSON array — no markdown fences, no explanation:
[
  {{
    "point": "One-sentence summary of the news item.",
    "article_refs": [
      {{"title": "Article title", "link": "https://...", "date": "YYYY-MM-DD or null"}}
    ]
  }}
]
"""


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------


@dataclass
class RecentNewsItem:
    """A single key-point entry in a politician's recent-news summary.

    Attributes:
        point: One-sentence summary of the newsworthy development.
        article_refs: Source article references backing this point.  Each
            element is a dict with ``"title"``, ``"link"``, and ``"date"``
            keys (``"date"`` may be ``None``).
    """

    point: str
    article_refs: list[dict[str, str | None]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict suitable for JSON output.

        Returns:
            A dict with ``"point"`` and ``"article_refs"`` keys.
        """
        return {"point": self.point, "article_refs": list(self.article_refs)}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _call_llm_for_recent_news(
    llm: Any,
    politician_name: str,
    articles: list[ArticleForProfile],
) -> list[RecentNewsItem]:
    """Call the LLM to generate recent-news key points for one politician.

    Args:
        llm: A ``ChatOpenAI``-compatible LLM instance.
        politician_name: Canonical name of the politician.
        articles: Newly ingested articles to summarise.

    Returns:
        A list of :class:`RecentNewsItem` objects.  Returns an empty list if
        the LLM call fails or returns malformed output.
    """
    articles_text = build_articles_text(articles)
    prompt = _RECENT_NEWS_PROMPT.format(
        politician_name=politician_name,
        articles_text=articles_text,
    )

    try:
        response = llm.invoke(prompt)
        content = response.content.strip()
        # Strip Markdown code fences if the LLM wraps the JSON.
        if content.startswith("```"):
            lines = content.splitlines()
            content = "\n".join(lines[1:])
            if content.endswith("```"):
                content = content[: content.rfind("```")]
            content = content.strip()
        raw_items: list[Any] = json.loads(content)
        if not isinstance(raw_items, list):
            logger.warning(
                "LLM returned non-list for recent news of %s.", politician_name
            )
            return []
        items: list[RecentNewsItem] = []
        for item in raw_items:
            if isinstance(item, dict) and item.get("point"):
                items.append(
                    RecentNewsItem(
                        point=str(item["point"]),
                        article_refs=list(item.get("article_refs") or []),
                    )
                )
        return items
    except Exception:
        logger.exception(
            "LLM call failed while building recent news for %s.", politician_name
        )
        return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_recent_news(
    articles_by_politician: dict[str, tuple[str, list[ArticleForProfile]]],
    openai_api_key: str,
    base_url: str,
    gpt_model: str,
) -> dict[str, list[RecentNewsItem]]:
    """Build per-politician recent-news summaries from newly ingested articles.

    For each politician who has at least one new article, calls an LLM to
    generate 3–7 concise key points summarising the most important recent
    developments.  Each key point is backed by citation(s) to source articles.

    Args:
        articles_by_politician: Mapping of ``politician_id`` (from
            ``config/politicians.yaml``) to a tuple of
            ``(politician_name, articles_list)``.
        openai_api_key: OpenAI-compatible API key (``OPENAI_API_KEY``).
        base_url: LLM API base URL (e.g. ``https://api.openai.com/v1``).
        gpt_model: LLM model identifier (e.g. ``"gpt-4o-mini"``).

    Returns:
        A dict mapping ``politician_name`` → list of :class:`RecentNewsItem`.
        Politicians with no articles or whose LLM call fails are absent from
        the result.

    Raises:
        RuntimeError: If the ``langchain-openai`` package is not installed.
    """
    try:
        from langchain_openai import ChatOpenAI  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            f"Required package not installed: {exc}. Install 'langchain-openai'."
        ) from exc

    llm = ChatOpenAI(
        model=gpt_model,
        base_url=base_url,
        api_key=openai_api_key,
        temperature=0,
        max_tokens=1_500,
    )

    result: dict[str, list[RecentNewsItem]] = {}

    for _politician_id, (politician_name, articles) in articles_by_politician.items():
        if not articles:
            continue

        logger.info(
            "Building recent news for %s: %d article(s).",
            politician_name,
            len(articles),
        )
        items = _call_llm_for_recent_news(llm, politician_name, articles)
        if items:
            result[politician_name] = items
            logger.info(
                "Generated %d news item(s) for %s.", len(items), politician_name
            )
        else:
            logger.warning(
                "No recent news items generated for %s.", politician_name
            )

    return result


def recent_news_to_dict(
    recent_news: dict[str, list[RecentNewsItem]],
) -> dict[str, list[dict[str, Any]]]:
    """Serialise recent-news data to a plain dict suitable for JSON output.

    Args:
        recent_news: Mapping returned by :func:`build_recent_news`.

    Returns:
        A JSON-serialisable dict with the same structure.
    """
    return {
        name: [item.to_dict() for item in items]
        for name, items in recent_news.items()
    }
