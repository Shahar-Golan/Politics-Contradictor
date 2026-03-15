"""
test_profile_updater
====================
Unit tests for ``agents.profile_updater``.

All Supabase and LLM interactions are mocked so no live credentials are
needed.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from agents.profile_updater import (
    ArticleForProfile,
    ProfileUpdateResult,
    _call_llm_for_profile_update,
    _fetch_profile,
    _normalize_speaker_id,
    _update_dataset_insights,
    _upsert_profile,
    build_articles_text,
    update_speaker_profiles,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_article() -> ArticleForProfile:
    """A realistic ArticleForProfile for testing."""
    return ArticleForProfile(
        doc_id="abc123",
        title="Trump signs new executive order",
        body="President Trump signed an executive order on immigration today.",
        date="2025-10-15",
        link="https://example.com/article/1",
    )


@pytest.fixture()
def sample_articles(sample_article: ArticleForProfile) -> list[ArticleForProfile]:
    """A list of two articles."""
    second = ArticleForProfile(
        doc_id="def456",
        title="Trump at UN speech",
        body="Trump addressed the United Nations General Assembly.",
        date="2025-10-16",
        link="https://example.com/article/2",
    )
    return [sample_article, second]


@pytest.fixture()
def existing_profile() -> dict:
    """A minimal existing profile dict."""
    return {
        "name": "Donald Trump",
        "bio": {
            "full_name": "Donald John Trump",
            "born": "1946-06-14",
            "party": "Republican",
            "current_role": "President of the United States (47th)",
            "net_worth_estimate": "",
            "previous_roles": [],
            "education": [],
        },
        "notable_topics": [],
        "timeline_highlights": [],
        "controversies": [],
        "relationships": {
            "allies": [],
            "opponents": [],
            "co_mentioned_figures": {},
            "relationship_context": "",
        },
        "public_perception": {
            "approval_trend": "",
            "base_support": "",
            "opposition": "",
            "key_narratives": [],
        },
        "media_profile": {
            "coverage_volume": "",
            "top_covering_states": {},
            "media_narrative": "",
            "sentiment_trend": "",
        },
        "dataset_insights": {
            "total_articles": 5,
            "date_range": "",
            "top_title_keywords": {},
            "geographic_focus": "",
        },
    }


# ---------------------------------------------------------------------------
# _update_dataset_insights
# ---------------------------------------------------------------------------


class TestUpdateDatasetInsights:
    def test_increments_total_articles(
        self, sample_articles: list[ArticleForProfile]
    ) -> None:
        profile = {"dataset_insights": {"total_articles": 10, "date_range": ""}}
        updated = _update_dataset_insights(profile, sample_articles)
        assert updated["dataset_insights"]["total_articles"] == 12

    def test_total_articles_starts_at_zero_when_missing(
        self, sample_articles: list[ArticleForProfile]
    ) -> None:
        updated = _update_dataset_insights({}, sample_articles)
        assert updated["dataset_insights"]["total_articles"] == 2

    def test_date_range_set_from_articles(
        self, sample_articles: list[ArticleForProfile]
    ) -> None:
        updated = _update_dataset_insights({}, sample_articles)
        date_range = updated["dataset_insights"]["date_range"]
        assert "2025-10-15" in date_range
        assert "2025-10-16" in date_range

    def test_date_range_extended_when_existing(
        self, sample_articles: list[ArticleForProfile]
    ) -> None:
        profile = {
            "dataset_insights": {
                "total_articles": 5,
                "date_range": "2025-09-01 – 2025-10-10",
            }
        }
        updated = _update_dataset_insights(profile, sample_articles)
        date_range = updated["dataset_insights"]["date_range"]
        assert "2025-09-01" in date_range  # existing min preserved
        assert "2025-10-16" in date_range  # new max from articles

    def test_undated_articles_counted_not_in_range(self) -> None:
        article = ArticleForProfile(
            doc_id="x1", title="T", body="B", date=None, link="http://x.com"
        )
        profile: dict[str, Any] = {}
        updated = _update_dataset_insights(profile, [article])
        assert updated["dataset_insights"]["total_articles"] == 1
        assert updated["dataset_insights"]["date_range"] == ""

    def test_does_not_mutate_original(
        self, sample_articles: list[ArticleForProfile]
    ) -> None:
        profile: dict = {"dataset_insights": {"total_articles": 3, "date_range": ""}}
        _update_dataset_insights(profile, sample_articles)
        assert profile["dataset_insights"]["total_articles"] == 3


# ---------------------------------------------------------------------------
# _normalize_speaker_id
# ---------------------------------------------------------------------------


class TestNormalizeSpeakerId:
    def test_hyphens_replaced_with_underscores(self) -> None:
        assert _normalize_speaker_id("donald-trump") == "donald_trump"

    def test_no_hyphens_unchanged(self) -> None:
        assert _normalize_speaker_id("joebiden") == "joebiden"

    def test_multiple_hyphens(self) -> None:
        assert _normalize_speaker_id("joe-h-biden") == "joe_h_biden"


# ---------------------------------------------------------------------------
# build_articles_text
# ---------------------------------------------------------------------------


class TestBuildArticlesText:
    def test_contains_title(self, sample_article: ArticleForProfile) -> None:
        text = build_articles_text([sample_article])
        assert "Trump signs new executive order" in text

    def test_contains_date(self, sample_article: ArticleForProfile) -> None:
        text = build_articles_text([sample_article])
        assert "2025-10-15" in text

    def test_contains_link(self, sample_article: ArticleForProfile) -> None:
        text = build_articles_text([sample_article])
        assert "https://example.com/article/1" in text

    def test_contains_body(self, sample_article: ArticleForProfile) -> None:
        text = build_articles_text([sample_article])
        assert "executive order" in text

    def test_multiple_articles_numbered(
        self, sample_articles: list[ArticleForProfile]
    ) -> None:
        text = build_articles_text(sample_articles)
        assert "[1]" in text
        assert "[2]" in text

    def test_respects_max_chars(
        self, sample_articles: list[ArticleForProfile]
    ) -> None:
        text = build_articles_text(sample_articles, max_chars=50)
        assert len(text) <= 500  # generous upper bound

    def test_none_date_shown_as_no_date(self) -> None:
        article = ArticleForProfile(
            doc_id="x1",
            title="Test",
            body="Some body text.",
            date=None,
            link="https://example.com",
        )
        text = build_articles_text([article])
        assert "no date" in text


# ---------------------------------------------------------------------------
# _fetch_profile
# ---------------------------------------------------------------------------


class TestFetchProfile:
    def test_returns_dict_when_found(self) -> None:
        profile = {"name": "Donald Trump"}
        client = MagicMock()
        client.table().select().eq().execute.return_value = MagicMock(
            data=[{"profile": profile}]
        )
        result = _fetch_profile(client, "donald_trump", "speaker_profiles")
        assert result == profile

    def test_parses_json_string(self) -> None:
        profile = {"name": "Joe Biden"}
        client = MagicMock()
        client.table().select().eq().execute.return_value = MagicMock(
            data=[{"profile": json.dumps(profile)}]
        )
        result = _fetch_profile(client, "joe_biden", "speaker_profiles")
        assert result == profile

    def test_returns_none_when_not_found(self) -> None:
        client = MagicMock()
        client.table().select().eq().execute.return_value = MagicMock(data=[])
        result = _fetch_profile(client, "unknown", "speaker_profiles")
        assert result is None

    def test_returns_none_on_exception(self) -> None:
        client = MagicMock()
        client.table().select().eq().execute.side_effect = Exception("DB error")
        result = _fetch_profile(client, "donald_trump", "speaker_profiles")
        assert result is None


# ---------------------------------------------------------------------------
# _upsert_profile
# ---------------------------------------------------------------------------


class TestUpsertProfile:
    def test_calls_upsert_with_correct_args(self) -> None:
        client = MagicMock()
        profile = {"name": "Donald Trump"}
        _upsert_profile(client, "donald_trump", profile, "speaker_profiles")
        client.table.assert_called_with("speaker_profiles")
        call_args = client.table().upsert.call_args
        row = call_args[0][0]
        assert row["speaker_id"] == "donald_trump"
        assert json.loads(row["profile"]) == profile


# ---------------------------------------------------------------------------
# _call_llm_for_profile_update
# ---------------------------------------------------------------------------


class TestCallLlmForProfileUpdate:
    def _make_llm(self, response_json: dict) -> MagicMock:
        llm = MagicMock()
        llm.invoke.return_value = MagicMock(
            content=json.dumps(response_json)
        )
        return llm

    def test_returns_updated_profile(
        self,
        sample_articles: list[ArticleForProfile],
        existing_profile: dict,
    ) -> None:
        updated = {**existing_profile, "name": "Donald J. Trump"}
        llm = self._make_llm({"updated": True, "profile": updated})
        result = _call_llm_for_profile_update(
            llm, "Donald Trump", existing_profile, sample_articles
        )
        assert result == updated

    def test_returns_none_when_no_update(
        self,
        sample_articles: list[ArticleForProfile],
        existing_profile: dict,
    ) -> None:
        llm = self._make_llm({"updated": False})
        result = _call_llm_for_profile_update(
            llm, "Donald Trump", existing_profile, sample_articles
        )
        assert result is None

    def test_returns_none_on_llm_exception(
        self,
        sample_articles: list[ArticleForProfile],
    ) -> None:
        llm = MagicMock()
        llm.invoke.side_effect = Exception("LLM failure")
        result = _call_llm_for_profile_update(
            llm, "Donald Trump", None, sample_articles
        )
        assert result is None

    def test_strips_markdown_fences(
        self,
        sample_articles: list[ArticleForProfile],
    ) -> None:
        profile = {"name": "Trump", "updated": True}
        wrapped = "```json\n" + json.dumps({"updated": True, "profile": profile}) + "\n```"
        llm = MagicMock()
        llm.invoke.return_value = MagicMock(content=wrapped)
        result = _call_llm_for_profile_update(
            llm, "Donald Trump", None, sample_articles
        )
        assert result == profile

    def test_handles_none_existing_profile(
        self,
        sample_articles: list[ArticleForProfile],
    ) -> None:
        new_profile = {"name": "Donald Trump", "bio": {}}
        llm = self._make_llm({"updated": True, "profile": new_profile})
        result = _call_llm_for_profile_update(
            llm, "Donald Trump", None, sample_articles
        )
        assert result == new_profile


# ---------------------------------------------------------------------------
# update_speaker_profiles (integration-style, everything mocked)
# ---------------------------------------------------------------------------


class TestUpdateSpeakerProfiles:
    """Tests for the public ``update_speaker_profiles`` function."""

    def _make_articles_map(
        self, articles: list[ArticleForProfile]
    ) -> dict[str, tuple[str, list[ArticleForProfile]]]:
        return {"donald-trump": ("Donald Trump", articles)}

    @patch("langchain_openai.ChatOpenAI")
    @patch("supabase.create_client")
    def test_updates_profile_when_llm_finds_new_info(
        self,
        mock_create_client: MagicMock,
        mock_chat_openai: MagicMock,
        sample_articles: list[ArticleForProfile],
        existing_profile: dict,
    ) -> None:
        updated_profile = {**existing_profile, "name": "Donald J. Trump"}

        # Mock Supabase client
        mock_client = MagicMock()
        mock_client.table().select().eq().execute.return_value = MagicMock(
            data=[{"profile": existing_profile}]
        )
        mock_create_client.return_value = mock_client

        # Mock LLM
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content=json.dumps({"updated": True, "profile": updated_profile})
        )
        mock_chat_openai.return_value = mock_llm

        result = update_speaker_profiles(
            articles_by_politician=self._make_articles_map(sample_articles),
            supabase_url="https://x.supabase.co",
            supabase_key="key",
            openai_api_key="sk-test",
            base_url="https://api.openai.com/v1",
            gpt_model="gpt-4o-mini",
        )

        assert result.politicians_processed == 1
        assert result.profiles_updated == 1
        assert result.profiles_skipped == 0
        assert result.errors == 0

    @patch("langchain_openai.ChatOpenAI")
    @patch("supabase.create_client")
    def test_skips_when_no_new_info(
        self,
        mock_create_client: MagicMock,
        mock_chat_openai: MagicMock,
        sample_articles: list[ArticleForProfile],
        existing_profile: dict,
    ) -> None:
        mock_client = MagicMock()
        mock_client.table().select().eq().execute.return_value = MagicMock(
            data=[{"profile": existing_profile}]
        )
        mock_create_client.return_value = mock_client

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content=json.dumps({"updated": False})
        )
        mock_chat_openai.return_value = mock_llm

        result = update_speaker_profiles(
            articles_by_politician=self._make_articles_map(sample_articles),
            supabase_url="https://x.supabase.co",
            supabase_key="key",
            openai_api_key="sk-test",
            base_url="https://api.openai.com/v1",
            gpt_model="gpt-4o-mini",
        )

        assert result.profiles_updated == 0
        assert result.profiles_skipped == 1
        # dataset_insights must still be upserted even when LLM found nothing new.
        assert result.datasets_only_updated == 1

    @patch("langchain_openai.ChatOpenAI")
    @patch("supabase.create_client")
    def test_upsert_called_even_when_no_new_info(
        self,
        mock_create_client: MagicMock,
        mock_chat_openai: MagicMock,
        sample_articles: list[ArticleForProfile],
        existing_profile: dict,
    ) -> None:
        """Upsert must always be called to keep article counts current."""
        mock_client = MagicMock()
        mock_client.table().select().eq().execute.return_value = MagicMock(
            data=[{"profile": existing_profile}]
        )
        mock_create_client.return_value = mock_client

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content=json.dumps({"updated": False})
        )
        mock_chat_openai.return_value = mock_llm

        update_speaker_profiles(
            articles_by_politician=self._make_articles_map(sample_articles),
            supabase_url="https://x.supabase.co",
            supabase_key="key",
            openai_api_key="sk-test",
            base_url="https://api.openai.com/v1",
            gpt_model="gpt-4o-mini",
        )

        # Upsert must have been called once (for dataset_insights refresh).
        assert mock_client.table().upsert.call_count >= 1

    @patch("langchain_openai.ChatOpenAI")
    @patch("supabase.create_client")
    def test_article_count_incremented_in_upserted_profile(
        self,
        mock_create_client: MagicMock,
        mock_chat_openai: MagicMock,
        sample_articles: list[ArticleForProfile],
        existing_profile: dict,
    ) -> None:
        """The upserted profile must include the incremented article count."""
        mock_client = MagicMock()
        mock_client.table().select().eq().execute.return_value = MagicMock(
            data=[{"profile": existing_profile}]
        )
        mock_create_client.return_value = mock_client

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content=json.dumps({"updated": False})
        )
        mock_chat_openai.return_value = mock_llm

        update_speaker_profiles(
            articles_by_politician=self._make_articles_map(sample_articles),
            supabase_url="https://x.supabase.co",
            supabase_key="key",
            openai_api_key="sk-test",
            base_url="https://api.openai.com/v1",
            gpt_model="gpt-4o-mini",
        )

        upsert_call = mock_client.table().upsert.call_args
        row = upsert_call[0][0]
        upserted_profile = json.loads(row["profile"])
        # existing profile had total_articles=5, we added 2 sample articles
        assert upserted_profile["dataset_insights"]["total_articles"] == 7

    @patch("langchain_openai.ChatOpenAI")
    @patch("supabase.create_client")
    def test_dry_run_skips_upsert(
        self,
        mock_create_client: MagicMock,
        mock_chat_openai: MagicMock,
        sample_articles: list[ArticleForProfile],
    ) -> None:
        mock_client = MagicMock()
        mock_client.table().select().eq().execute.return_value = MagicMock(data=[])
        mock_create_client.return_value = mock_client

        new_profile = {"name": "Donald Trump"}
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content=json.dumps({"updated": True, "profile": new_profile})
        )
        mock_chat_openai.return_value = mock_llm

        result = update_speaker_profiles(
            articles_by_politician=self._make_articles_map(sample_articles),
            supabase_url="https://x.supabase.co",
            supabase_key="key",
            openai_api_key="sk-test",
            base_url="https://api.openai.com/v1",
            gpt_model="gpt-4o-mini",
            dry_run=True,
        )

        # Profile counted as updated (the LLM said yes), but upsert must not
        # have been called.
        assert result.profiles_updated == 1
        upsert_calls = mock_client.table().upsert.call_count
        assert upsert_calls == 0

    @patch("langchain_openai.ChatOpenAI")
    @patch("supabase.create_client")
    def test_empty_articles_not_processed(
        self,
        mock_create_client: MagicMock,
        mock_chat_openai: MagicMock,
    ) -> None:
        result = update_speaker_profiles(
            articles_by_politician={"donald-trump": ("Donald Trump", [])},
            supabase_url="https://x.supabase.co",
            supabase_key="key",
            openai_api_key="sk-test",
            base_url="https://api.openai.com/v1",
            gpt_model="gpt-4o-mini",
        )
        assert result.politicians_processed == 0

    @patch("langchain_openai.ChatOpenAI")
    @patch("supabase.create_client")
    def test_upsert_error_counted(
        self,
        mock_create_client: MagicMock,
        mock_chat_openai: MagicMock,
        sample_articles: list[ArticleForProfile],
    ) -> None:
        mock_client = MagicMock()
        mock_client.table().select().eq().execute.return_value = MagicMock(data=[])
        # Make upsert raise
        mock_client.table().upsert().execute.side_effect = Exception("DB error")
        mock_create_client.return_value = mock_client

        new_profile = {"name": "Donald Trump"}
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content=json.dumps({"updated": True, "profile": new_profile})
        )
        mock_chat_openai.return_value = mock_llm

        result = update_speaker_profiles(
            articles_by_politician=self._make_articles_map(sample_articles),
            supabase_url="https://x.supabase.co",
            supabase_key="key",
            openai_api_key="sk-test",
            base_url="https://api.openai.com/v1",
            gpt_model="gpt-4o-mini",
        )

        assert result.errors == 1
        assert result.profiles_updated == 0

    @patch("langchain_openai.ChatOpenAI")
    @patch("supabase.create_client")
    def test_recent_news_stored_inside_profile(
        self,
        mock_create_client: MagicMock,
        mock_chat_openai: MagicMock,
        sample_articles: list[ArticleForProfile],
        existing_profile: dict,
    ) -> None:
        """recent_news items must be merged into the upserted profile JSON."""
        mock_client = MagicMock()
        mock_client.table().select().eq().execute.return_value = MagicMock(
            data=[{"profile": existing_profile}]
        )
        mock_create_client.return_value = mock_client

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content=json.dumps({"updated": False})
        )
        mock_chat_openai.return_value = mock_llm

        news_items = [
            {"point": "Trump signed a new order.", "article_refs": []},
        ]
        update_speaker_profiles(
            articles_by_politician=self._make_articles_map(sample_articles),
            supabase_url="https://x.supabase.co",
            supabase_key="key",
            openai_api_key="sk-test",
            base_url="https://api.openai.com/v1",
            gpt_model="gpt-4o-mini",
            recent_news_by_politician={"donald-trump": news_items},
        )

        upsert_call = mock_client.table().upsert.call_args
        row = upsert_call[0][0]
        upserted_profile = json.loads(row["profile"])
        assert "recent_news" in upserted_profile
        assert upserted_profile["recent_news"] == news_items

    @patch("langchain_openai.ChatOpenAI")
    @patch("supabase.create_client")
    def test_no_recent_news_key_when_not_provided(
        self,
        mock_create_client: MagicMock,
        mock_chat_openai: MagicMock,
        sample_articles: list[ArticleForProfile],
        existing_profile: dict,
    ) -> None:
        """When recent_news_by_politician is None, no recent_news key is added."""
        mock_client = MagicMock()
        mock_client.table().select().eq().execute.return_value = MagicMock(
            data=[{"profile": existing_profile}]
        )
        mock_create_client.return_value = mock_client

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(
            content=json.dumps({"updated": False})
        )
        mock_chat_openai.return_value = mock_llm

        update_speaker_profiles(
            articles_by_politician=self._make_articles_map(sample_articles),
            supabase_url="https://x.supabase.co",
            supabase_key="key",
            openai_api_key="sk-test",
            base_url="https://api.openai.com/v1",
            gpt_model="gpt-4o-mini",
            recent_news_by_politician=None,
        )

        upsert_call = mock_client.table().upsert.call_args
        row = upsert_call[0][0]
        upserted_profile = json.loads(row["profile"])
        # existing_profile has no recent_news key; we should not have injected one.
        assert "recent_news" not in upserted_profile


# ---------------------------------------------------------------------------
# ArticleForProfile dataclass
# ---------------------------------------------------------------------------


class TestArticleForProfile:
    def test_fields_accessible(self) -> None:
        a = ArticleForProfile(
            doc_id="x1",
            title="Title",
            body="Body",
            date="2025-01-01",
            link="https://example.com",
        )
        assert a.doc_id == "x1"
        assert a.title == "Title"
        assert a.body == "Body"
        assert a.date == "2025-01-01"
        assert a.link == "https://example.com"

    def test_date_can_be_none(self) -> None:
        a = ArticleForProfile(
            doc_id="x2", title="T", body="B", date=None, link="http://x.com"
        )
        assert a.date is None
