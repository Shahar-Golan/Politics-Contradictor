"""
test_article_selection
======================
Tests for the deterministic article selection layer.

Covers:
- score_article_for_extraction: rule matching for individual articles
- select_candidate_articles: end-to-end selection against a SQLite fixture
- Politician filtering works for Trump and Biden
- Obvious positive examples are selected (score >= min_score)
- Obvious irrelevant examples are rejected (score < min_score)
- Repeated runs on the same input produce the same output (determinism)
- Scoring rule explanations are stable
- SQLite-backed selection works against fixture data
- SelectionConfig options (min_score, max_results, date range)
- Unknown politician raises ValueError
- Missing database raises FileNotFoundError
- ScoredArticle.is_eligible reflects min_score threshold
- SelectionResult.eligible_articles filters correctly
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from db.init_db import init_db
from selection.article_selector import select_candidate_articles
from selection.keywords import POLITICIAN_ALIASES
from selection.models import ScoredArticle, SelectionConfig, SelectionResult
from selection.scoring import score_article_for_extraction

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_row(
    doc_id: str = "doc-001",
    title: str = "Test Article",
    text: str = "Body text. " * 20,
    speakers_mentioned: str = "[]",
    date: str = "2025-01-01",
) -> dict[str, Any]:
    """Return a minimal article dict compatible with score_article_for_extraction."""
    return {
        "doc_id": doc_id,
        "title": title,
        "text": text,
        "speakers_mentioned": speakers_mentioned,
        "date": date,
    }


def _insert_article(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    """Insert a single article dict directly into news_articles."""
    conn.execute(
        """
        INSERT OR IGNORE INTO news_articles
            (doc_id, title, text, date, speakers_mentioned)
        VALUES (:doc_id, :title, :text, :date, :speakers_mentioned)
        """,
        row,
    )
    conn.commit()


@pytest.fixture()
def tmp_db(tmp_path: Path) -> Path:
    """Return a path for a fresh, schema-initialised temporary SQLite database."""
    db = tmp_path / "test_selection.db"
    init_db(db)
    return db


@pytest.fixture()
def populated_db(tmp_db: Path) -> Path:
    """
    Populate the test database with a variety of articles:

    trump-strong  : Trump in speakers_mentioned + title has 'announces' + policy
    trump-weak    : Trump in title only, no extra signals
    biden-strong  : Biden in speakers_mentioned + quote marker + policy
    biden-poll    : Biden mentioned but title is a polling article (low priority)
    irrelevant    : Neither politician mentioned, no stance signals
    both          : Both Trump and Biden in speakers_mentioned
    """
    conn = sqlite3.connect(str(tmp_db))
    conn.row_factory = sqlite3.Row

    articles = [
        {
            "doc_id": "trump-strong",
            "title": "Trump announces new immigration plan",
            "text": (
                'President Trump said "We will build the wall" at a rally. '
                "The executive order on immigration will take effect next week. " * 5
            ),
            "speakers_mentioned": json.dumps(["Donald Trump", "Press Secretary"]),
            "date": "2025-03-01",
        },
        {
            "doc_id": "trump-weak",
            "title": "Trump seen at golf club",
            "text": "Donald Trump was spotted at his golf club over the weekend.",
            "speakers_mentioned": "[]",
            "date": "2025-02-15",
        },
        {
            "doc_id": "biden-strong",
            "title": "Biden vows to expand healthcare access",
            "text": (
                'President Biden declared "Every American deserves healthcare." '
                "His administration proposed a new Medicare expansion bill. " * 5
            ),
            "speakers_mentioned": json.dumps(["Joe Biden", "Surgeon General"]),
            "date": "2025-03-05",
        },
        {
            "doc_id": "biden-poll",
            "title": "Biden approval rating drops in new poll",
            "text": (
                "A new poll shows Biden's approval rating has fallen. "
                "The horse race between Biden and his opponents continues. " * 5
            ),
            "speakers_mentioned": json.dumps(["Joe Biden"]),
            "date": "2025-02-20",
        },
        {
            "doc_id": "irrelevant",
            "title": "Local sports team wins championship",
            "text": "The home team celebrated their victory at the stadium. " * 10,
            "speakers_mentioned": "[]",
            "date": "2025-01-10",
        },
        {
            "doc_id": "both",
            "title": "Trump and Biden clash over economy",
            "text": (
                'Trump said "The economy was better under me." '
                'Biden countered "We\'ve created millions of jobs." '
                "The trade tariff dispute heated up. " * 5
            ),
            "speakers_mentioned": json.dumps(["Donald Trump", "Joe Biden"]),
            "date": "2025-03-10",
        },
        {
            "doc_id": "short",
            "title": "Trump speaks",
            "text": "Trump spoke.",
            "speakers_mentioned": "[]",
            "date": "2025-01-05",
        },
    ]

    for art in articles:
        _insert_article(conn, art)

    conn.close()
    return tmp_db


# ---------------------------------------------------------------------------
# Tests: score_article_for_extraction
# ---------------------------------------------------------------------------


class TestScoringRules:
    """Verify individual scoring rules in score_article_for_extraction."""

    def test_politician_in_speakers_adds_score(self) -> None:
        row = _make_row(
            doc_id="s1",
            speakers_mentioned=json.dumps(["Donald Trump"]),
        )
        result = score_article_for_extraction(row, "Trump")
        assert "politician_in_speakers" in result.matched_rules
        assert result.score >= 3

    def test_politician_not_in_speakers(self) -> None:
        row = _make_row(doc_id="s2", speakers_mentioned="[]")
        result = score_article_for_extraction(row, "Trump")
        assert "politician_in_speakers" not in result.matched_rules

    def test_reporting_verb_in_title(self) -> None:
        row = _make_row(doc_id="s3", title="Trump announces new policy")
        result = score_article_for_extraction(row, "Trump")
        assert "reporting_verb_in_title" in result.matched_rules

    def test_policy_topic_in_title(self) -> None:
        row = _make_row(doc_id="s4", title="Biden's plan on immigration")
        result = score_article_for_extraction(row, "Biden")
        assert "policy_topic_in_title" in result.matched_rules

    def test_policy_topic_in_text(self) -> None:
        row = _make_row(
            doc_id="s5",
            text="The healthcare reform bill was discussed. " * 10,
        )
        result = score_article_for_extraction(row, "Biden")
        assert "policy_topic_in_text" in result.matched_rules

    def test_quote_marker_in_text(self) -> None:
        row = _make_row(
            doc_id="s6",
            text='"We will fix the economy," said the president. ' * 10,
        )
        result = score_article_for_extraction(row, "Trump")
        assert "quote_marker_in_text" in result.matched_rules

    def test_text_length_ok(self) -> None:
        long_text = "Word " * 100  # well above 150 chars
        row = _make_row(doc_id="s7", text=long_text)
        result = score_article_for_extraction(row, "Trump")
        assert "text_length_ok" in result.matched_rules
        assert "text_too_short" not in result.matched_rules

    def test_text_too_short_penalty(self) -> None:
        row = _make_row(doc_id="s8", text="Short.")
        result = score_article_for_extraction(row, "Trump")
        assert "text_too_short" in result.matched_rules
        assert "text_length_ok" not in result.matched_rules

    def test_low_priority_signal_in_title_penalty(self) -> None:
        row = _make_row(doc_id="s9", title="New poll shows Trump ahead")
        result = score_article_for_extraction(row, "Trump")
        assert "low_priority_signal_in_title" in result.matched_rules

    def test_low_priority_signal_in_text_penalty(self) -> None:
        row = _make_row(
            doc_id="s10",
            text="Approval rating polls show mixed results. " * 10,
        )
        result = score_article_for_extraction(row, "Biden")
        assert "low_priority_signal_in_text" in result.matched_rules

    def test_unknown_politician_raises(self) -> None:
        row = _make_row(doc_id="s11")
        with pytest.raises(KeyError, match="Unknown politician"):
            score_article_for_extraction(row, "Unknown Politician")

    def test_is_eligible_respects_min_score(self) -> None:
        config_strict = SelectionConfig(min_score=100)
        row = _make_row(doc_id="s12")
        result = score_article_for_extraction(row, "Trump", config=config_strict)
        assert not result.is_eligible

    def test_politician_in_title_adds_score(self) -> None:
        row = _make_row(doc_id="s13", title="Trump plans to reform the tax code")
        result = score_article_for_extraction(row, "Trump")
        assert "politician_in_title" in result.matched_rules

    def test_matched_rules_are_stable(self) -> None:
        """Scoring the same article twice must produce identical rule sets."""
        row = _make_row(
            doc_id="s14",
            title="Biden announces healthcare bill",
            text='"We need healthcare for all," Biden said. ' * 10,
            speakers_mentioned=json.dumps(["Joe Biden"]),
        )
        result1 = score_article_for_extraction(row, "Biden")
        result2 = score_article_for_extraction(row, "Biden")
        assert result1.matched_rules == result2.matched_rules
        assert result1.score == result2.score


# ---------------------------------------------------------------------------
# Tests: Politician alias coverage
# ---------------------------------------------------------------------------


class TestPoliticianAliases:
    """Verify that all expected politician aliases are recognised."""

    def test_trump_aliases_in_registry(self) -> None:
        assert "Trump" in POLITICIAN_ALIASES
        aliases = POLITICIAN_ALIASES["Trump"]
        assert "trump" in aliases
        assert "donald trump" in aliases

    def test_biden_aliases_in_registry(self) -> None:
        assert "Biden" in POLITICIAN_ALIASES
        aliases = POLITICIAN_ALIASES["Biden"]
        assert "biden" in aliases
        assert "joe biden" in aliases

    def test_trump_alias_detected_in_speakers(self) -> None:
        row = _make_row(
            doc_id="alias-t1",
            speakers_mentioned=json.dumps(["President Trump"]),
        )
        result = score_article_for_extraction(row, "Trump")
        assert "politician_in_speakers" in result.matched_rules

    def test_biden_alias_detected_in_speakers(self) -> None:
        row = _make_row(
            doc_id="alias-b1",
            speakers_mentioned=json.dumps(["Former President Biden"]),
        )
        result = score_article_for_extraction(row, "Biden")
        assert "politician_in_speakers" in result.matched_rules


# ---------------------------------------------------------------------------
# Tests: select_candidate_articles (SQLite-backed)
# ---------------------------------------------------------------------------


class TestSelectCandidateArticles:
    """End-to-end selection tests using a fixture SQLite database."""

    def test_returns_selection_result(self, populated_db: Path) -> None:
        result = select_candidate_articles(db_path=populated_db)
        assert isinstance(result, SelectionResult)

    def test_trump_strong_is_selected(self, populated_db: Path) -> None:
        config = SelectionConfig(politicians=["Trump"], min_score=2)
        result = select_candidate_articles(config=config, db_path=populated_db)
        eligible_ids = {a.doc_id for a in result.eligible_articles}
        assert "trump-strong" in eligible_ids

    def test_biden_strong_is_selected(self, populated_db: Path) -> None:
        config = SelectionConfig(politicians=["Biden"], min_score=2)
        result = select_candidate_articles(config=config, db_path=populated_db)
        eligible_ids = {a.doc_id for a in result.eligible_articles}
        assert "biden-strong" in eligible_ids

    def test_irrelevant_article_is_not_selected(self, populated_db: Path) -> None:
        config = SelectionConfig(politicians=["Trump", "Biden"], min_score=1)
        result = select_candidate_articles(config=config, db_path=populated_db)
        eligible_ids = {a.doc_id for a in result.eligible_articles}
        assert "irrelevant" not in eligible_ids

    def test_both_politician_article_is_selected(self, populated_db: Path) -> None:
        config = SelectionConfig(politicians=["Trump", "Biden"], min_score=2)
        result = select_candidate_articles(config=config, db_path=populated_db)
        eligible_ids = {a.doc_id for a in result.eligible_articles}
        assert "both" in eligible_ids

    def test_filter_trump_only(self, populated_db: Path) -> None:
        config = SelectionConfig(politicians=["Trump"], min_score=1)
        result = select_candidate_articles(config=config, db_path=populated_db)
        for article in result.eligible_articles:
            assert article.matched_politician == "Trump"

    def test_filter_biden_only(self, populated_db: Path) -> None:
        config = SelectionConfig(politicians=["Biden"], min_score=1)
        result = select_candidate_articles(config=config, db_path=populated_db)
        for article in result.eligible_articles:
            assert article.matched_politician == "Biden"

    def test_determinism_same_result_twice(self, populated_db: Path) -> None:
        """Running selection twice on the same DB must produce identical results."""
        config = SelectionConfig(politicians=["Trump", "Biden"], min_score=1)
        result1 = select_candidate_articles(config=config, db_path=populated_db)
        result2 = select_candidate_articles(config=config, db_path=populated_db)
        ids1 = [a.doc_id for a in result1.articles]
        ids2 = [a.doc_id for a in result2.articles]
        assert ids1 == ids2
        scores1 = [a.score for a in result1.articles]
        scores2 = [a.score for a in result2.articles]
        assert scores1 == scores2

    def test_max_results_caps_eligible(self, populated_db: Path) -> None:
        config = SelectionConfig(
            politicians=["Trump", "Biden"], min_score=1, max_results=1
        )
        result = select_candidate_articles(config=config, db_path=populated_db)
        assert len(result.eligible_articles) <= 1

    def test_eligible_count_correct(self, populated_db: Path) -> None:
        config = SelectionConfig(politicians=["Trump", "Biden"], min_score=1)
        result = select_candidate_articles(config=config, db_path=populated_db)
        assert result.eligible_count == len(
            [a for a in result.articles if a.is_eligible]
        )

    def test_articles_sorted_by_score_desc(self, populated_db: Path) -> None:
        config = SelectionConfig(politicians=["Trump", "Biden"], min_score=0)
        result = select_candidate_articles(config=config, db_path=populated_db)
        scores = [a.score for a in result.articles]
        assert scores == sorted(scores, reverse=True)

    def test_date_from_filter(self, populated_db: Path) -> None:
        config = SelectionConfig(
            politicians=["Trump", "Biden"],
            min_score=1,
            date_from="2025-03-01",
        )
        result = select_candidate_articles(config=config, db_path=populated_db)
        eligible_ids = {a.doc_id for a in result.eligible_articles}
        # Articles before the cutoff must not appear.
        assert "trump-weak" not in eligible_ids    # 2025-02-15
        assert "biden-poll" not in eligible_ids    # 2025-02-20
        assert "irrelevant" not in eligible_ids    # 2025-01-10
        assert "short" not in eligible_ids         # 2025-01-05
        # Articles on or after the cutoff with sufficient score must appear.
        assert "trump-strong" in eligible_ids      # 2025-03-01 (on cutoff)
        assert "biden-strong" in eligible_ids      # 2025-03-05

    def test_unknown_politician_raises(self, populated_db: Path) -> None:
        config = SelectionConfig(politicians=["UnknownPerson"])
        with pytest.raises(ValueError, match="Unknown politician"):
            select_candidate_articles(config=config, db_path=populated_db)

    def test_missing_database_raises(self, tmp_path: Path) -> None:
        missing_db = tmp_path / "does_not_exist.db"
        config = SelectionConfig(politicians=["Trump"])
        with pytest.raises(FileNotFoundError):
            select_candidate_articles(config=config, db_path=missing_db)

    def test_empty_database_returns_no_results(self, tmp_db: Path) -> None:
        config = SelectionConfig(politicians=["Trump", "Biden"], min_score=1)
        result = select_candidate_articles(config=config, db_path=tmp_db)
        assert result.total_candidates == 0
        assert result.eligible_count == 0
        assert result.articles == []


# ---------------------------------------------------------------------------
# Tests: SelectionResult helpers
# ---------------------------------------------------------------------------


class TestSelectionResult:
    """Verify SelectionResult properties and helpers."""

    def test_eligible_articles_property(self, populated_db: Path) -> None:
        config = SelectionConfig(politicians=["Trump", "Biden"], min_score=2)
        result = select_candidate_articles(config=config, db_path=populated_db)
        assert all(a.is_eligible for a in result.eligible_articles)

    def test_total_candidates_matches(self, populated_db: Path) -> None:
        config = SelectionConfig(politicians=["Trump"], min_score=0)
        result = select_candidate_articles(config=config, db_path=populated_db)
        assert result.total_candidates >= 1

    def test_config_preserved_in_result(self, populated_db: Path) -> None:
        config = SelectionConfig(politicians=["Biden"], min_score=3, max_results=10)
        result = select_candidate_articles(config=config, db_path=populated_db)
        assert result.config is config
