"""
test_recent_news_builder
========================
Unit tests for ``agents.recent_news_builder``.

All LLM interactions are mocked so no live credentials are needed.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from agents.profile_updater import ArticleForProfile
from agents.recent_news_builder import (
    RecentNewsItem,
    _call_llm_for_recent_news,
    build_recent_news,
    recent_news_to_dict,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_articles() -> list[ArticleForProfile]:
    """Two sample articles mentioning Donald Trump."""
    return [
        ArticleForProfile(
            doc_id="a1",
            title="Trump signs immigration order",
            body="The president signed a major immigration executive order.",
            date="2025-10-15",
            link="https://example.com/1",
        ),
        ArticleForProfile(
            doc_id="a2",
            title="Trump addresses UN",
            body="Trump spoke at the United Nations General Assembly.",
            date="2025-10-16",
            link="https://example.com/2",
        ),
    ]


@pytest.fixture()
def llm_news_response() -> list[dict]:
    """A well-formed LLM response for recent news."""
    return [
        {
            "point": "Trump signed a major executive order on immigration.",
            "article_refs": [
                {
                    "title": "Trump signs immigration order",
                    "link": "https://example.com/1",
                    "date": "2025-10-15",
                }
            ],
        },
        {
            "point": "Trump addressed the UN General Assembly.",
            "article_refs": [
                {
                    "title": "Trump addresses UN",
                    "link": "https://example.com/2",
                    "date": "2025-10-16",
                }
            ],
        },
    ]


# ---------------------------------------------------------------------------
# RecentNewsItem
# ---------------------------------------------------------------------------


class TestRecentNewsItem:
    def test_fields_accessible(self) -> None:
        item = RecentNewsItem(
            point="Some important news.",
            article_refs=[{"title": "Article", "link": "http://x.com", "date": "2025-01-01"}],
        )
        assert item.point == "Some important news."
        assert len(item.article_refs) == 1

    def test_default_article_refs_empty(self) -> None:
        item = RecentNewsItem(point="News.")
        assert item.article_refs == []

    def test_to_dict(self) -> None:
        refs = [{"title": "T", "link": "http://x.com", "date": None}]
        item = RecentNewsItem(point="Some news.", article_refs=refs)
        d = item.to_dict()
        assert d == {"point": "Some news.", "article_refs": refs}


# ---------------------------------------------------------------------------
# _call_llm_for_recent_news
# ---------------------------------------------------------------------------


class TestCallLlmForRecentNews:
    def _make_llm(self, response_content: str) -> MagicMock:
        llm = MagicMock()
        llm.invoke.return_value = MagicMock(content=response_content)
        return llm

    def test_returns_list_of_items(
        self,
        sample_articles: list[ArticleForProfile],
        llm_news_response: list[dict],
    ) -> None:
        llm = self._make_llm(json.dumps(llm_news_response))
        items = _call_llm_for_recent_news(llm, "Donald Trump", sample_articles)
        assert len(items) == 2
        assert all(isinstance(i, RecentNewsItem) for i in items)

    def test_item_point_text(
        self,
        sample_articles: list[ArticleForProfile],
        llm_news_response: list[dict],
    ) -> None:
        llm = self._make_llm(json.dumps(llm_news_response))
        items = _call_llm_for_recent_news(llm, "Donald Trump", sample_articles)
        assert "immigration" in items[0].point

    def test_item_article_refs(
        self,
        sample_articles: list[ArticleForProfile],
        llm_news_response: list[dict],
    ) -> None:
        llm = self._make_llm(json.dumps(llm_news_response))
        items = _call_llm_for_recent_news(llm, "Donald Trump", sample_articles)
        assert items[0].article_refs[0]["link"] == "https://example.com/1"

    def test_strips_markdown_fences(
        self,
        sample_articles: list[ArticleForProfile],
        llm_news_response: list[dict],
    ) -> None:
        wrapped = "```json\n" + json.dumps(llm_news_response) + "\n```"
        llm = self._make_llm(wrapped)
        items = _call_llm_for_recent_news(llm, "Donald Trump", sample_articles)
        assert len(items) == 2

    def test_returns_empty_on_llm_exception(
        self,
        sample_articles: list[ArticleForProfile],
    ) -> None:
        llm = MagicMock()
        llm.invoke.side_effect = Exception("timeout")
        items = _call_llm_for_recent_news(llm, "Donald Trump", sample_articles)
        assert items == []

    def test_returns_empty_on_malformed_json(
        self,
        sample_articles: list[ArticleForProfile],
    ) -> None:
        llm = self._make_llm("not-valid-json")
        items = _call_llm_for_recent_news(llm, "Donald Trump", sample_articles)
        assert items == []

    def test_returns_empty_when_llm_returns_non_list(
        self,
        sample_articles: list[ArticleForProfile],
    ) -> None:
        llm = self._make_llm(json.dumps({"error": "bad response"}))
        items = _call_llm_for_recent_news(llm, "Donald Trump", sample_articles)
        assert items == []

    def test_skips_items_without_point(
        self,
        sample_articles: list[ArticleForProfile],
    ) -> None:
        response = [
            {"point": "Valid point.", "article_refs": []},
            {"no_point": "Missing point key", "article_refs": []},
        ]
        llm = self._make_llm(json.dumps(response))
        items = _call_llm_for_recent_news(llm, "Donald Trump", sample_articles)
        assert len(items) == 1
        assert items[0].point == "Valid point."


# ---------------------------------------------------------------------------
# build_recent_news (integration-style, LLM mocked)
# ---------------------------------------------------------------------------


class TestBuildRecentNews:
    @patch("langchain_openai.ChatOpenAI")
    def test_returns_dict_keyed_by_name(
        self,
        mock_chat_openai: MagicMock,
        sample_articles: list[ArticleForProfile],
        llm_news_response: list[dict],
    ) -> None:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content=json.dumps(llm_news_response)
        )
        mock_chat_openai.return_value = mock_llm

        result = build_recent_news(
            articles_by_politician={"donald-trump": ("Donald Trump", sample_articles)},
            openai_api_key="sk-test",
            base_url="https://api.openai.com/v1",
            gpt_model="gpt-4o-mini",
        )

        assert "Donald Trump" in result
        assert len(result["Donald Trump"]) == 2

    @patch("langchain_openai.ChatOpenAI")
    def test_politician_absent_when_no_articles(
        self,
        mock_chat_openai: MagicMock,
    ) -> None:
        mock_llm = MagicMock()
        mock_chat_openai.return_value = mock_llm

        result = build_recent_news(
            articles_by_politician={"joe-biden": ("Joe Biden", [])},
            openai_api_key="sk-test",
            base_url="https://api.openai.com/v1",
            gpt_model="gpt-4o-mini",
        )

        assert "Joe Biden" not in result
        mock_llm.invoke.assert_not_called()

    @patch("langchain_openai.ChatOpenAI")
    def test_politician_absent_when_llm_fails(
        self,
        mock_chat_openai: MagicMock,
        sample_articles: list[ArticleForProfile],
    ) -> None:
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = Exception("API error")
        mock_chat_openai.return_value = mock_llm

        result = build_recent_news(
            articles_by_politician={
                "donald-trump": ("Donald Trump", sample_articles)
            },
            openai_api_key="sk-test",
            base_url="https://api.openai.com/v1",
            gpt_model="gpt-4o-mini",
        )

        assert "Donald Trump" not in result

    @patch("langchain_openai.ChatOpenAI")
    def test_multiple_politicians(
        self,
        mock_chat_openai: MagicMock,
        sample_articles: list[ArticleForProfile],
        llm_news_response: list[dict],
    ) -> None:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content=json.dumps(llm_news_response)
        )
        mock_chat_openai.return_value = mock_llm

        result = build_recent_news(
            articles_by_politician={
                "donald-trump": ("Donald Trump", sample_articles),
                "joe-biden": ("Joe Biden", sample_articles),
            },
            openai_api_key="sk-test",
            base_url="https://api.openai.com/v1",
            gpt_model="gpt-4o-mini",
        )

        assert "Donald Trump" in result
        assert "Joe Biden" in result
        # LLM should have been called once per politician.
        assert mock_llm.invoke.call_count == 2


# ---------------------------------------------------------------------------
# recent_news_to_dict
# ---------------------------------------------------------------------------


class TestRecentNewsToDict:
    def test_converts_to_plain_dicts(
        self, llm_news_response: list[dict]
    ) -> None:
        items = [
            RecentNewsItem(
                point=entry["point"],
                article_refs=entry["article_refs"],
            )
            for entry in llm_news_response
        ]
        serialised = recent_news_to_dict({"Donald Trump": items})
        assert isinstance(serialised, dict)
        assert isinstance(serialised["Donald Trump"], list)
        assert serialised["Donald Trump"][0]["point"] == items[0].point
        assert isinstance(serialised["Donald Trump"][0]["article_refs"], list)

    def test_json_serialisable(self, llm_news_response: list[dict]) -> None:
        items = [RecentNewsItem(point=e["point"]) for e in llm_news_response]
        serialised = recent_news_to_dict({"Trump": items})
        # Should not raise
        json_str = json.dumps(serialised)
        assert "Trump" in json_str

    def test_empty_input(self) -> None:
        assert recent_news_to_dict({}) == {}
