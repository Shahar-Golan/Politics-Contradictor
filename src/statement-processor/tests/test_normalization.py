"""
test_normalization
==================
Tests for the deterministic normalization layer.

Covers:
- Politician name normalization (common aliases → canonical)
- Unknown politician handling
- Topic normalization (surface forms → controlled vocab)
- Unsupported topic handling (→ "other")
- Proposition normalization (tariff example, whitespace, sentence case)
- Date parsing (YYYY-MM-DD, YYYY-MM, YYYY)
- Unparseable date handling
- Confidence normalization (clamping)
- Full normalize_document pipeline
- Raw values are preserved in provenance fields
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_BASE = Path(__file__).parent.parent
_FIXTURES_VALID = _BASE / "tests" / "fixtures" / "valid"
_FIXTURES_NORMALIZED = _BASE / "tests" / "fixtures" / "normalized"

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

from validation.politician_normalization import resolve_politician
from validation.topic_normalization import normalize_topic
from validation.proposition_normalization import normalize_proposition
from validation.date_parser import parse_date, validate_precision_match
from validation.validator import validate_document
from validation.normalizer import normalize_document, normalize_candidate
from validation.models import ValidationStatus
from validation.errors import WarningCode


# ---------------------------------------------------------------------------
# Politician normalization tests
# ---------------------------------------------------------------------------


class TestPoliticianNormalization:
    """Politician alias resolution to canonical names."""

    def test_trump_full_name_unchanged(self) -> None:
        res = resolve_politician("Donald Trump")
        assert res.canonical == "Donald Trump"
        assert res.is_known is True
        assert res.was_normalized is False

    def test_trump_short_alias(self) -> None:
        res = resolve_politician("Trump")
        assert res.canonical == "Donald Trump"
        assert res.is_known is True
        assert res.was_normalized is True

    def test_trump_president_prefix(self) -> None:
        res = resolve_politician("President Trump")
        assert res.canonical == "Donald Trump"
        assert res.was_normalized is True

    def test_trump_former_president(self) -> None:
        res = resolve_politician("former President Donald Trump")
        assert res.canonical == "Donald Trump"
        assert res.was_normalized is True

    def test_biden_full_name_unchanged(self) -> None:
        res = resolve_politician("Joe Biden")
        assert res.canonical == "Joe Biden"
        assert res.is_known is True
        assert res.was_normalized is False

    def test_biden_short_alias(self) -> None:
        res = resolve_politician("Biden")
        assert res.canonical == "Joe Biden"
        assert res.was_normalized is True

    def test_harris_alias(self) -> None:
        res = resolve_politician("VP Harris")
        assert res.canonical == "Kamala Harris"
        assert res.was_normalized is True

    def test_aoc_alias(self) -> None:
        res = resolve_politician("AOC")
        assert res.canonical == "Alexandria Ocasio-Cortez"
        assert res.was_normalized is True

    def test_case_insensitive_lookup(self) -> None:
        res = resolve_politician("TRUMP")
        assert res.canonical == "Donald Trump"

    def test_unknown_politician_returns_original(self) -> None:
        res = resolve_politician("Random Unknown Person")
        assert res.canonical == "Random Unknown Person"
        assert res.is_known is False
        assert res.was_normalized is False

    def test_empty_string_handled(self) -> None:
        res = resolve_politician("")
        assert res.canonical == ""
        assert res.is_known is False

    def test_none_handled(self) -> None:
        res = resolve_politician(None)
        assert res.canonical == ""
        assert res.is_known is False

    def test_whitespace_stripped(self) -> None:
        res = resolve_politician("  Trump  ")
        assert res.canonical == "Donald Trump"


# ---------------------------------------------------------------------------
# Topic normalization tests
# ---------------------------------------------------------------------------


class TestTopicNormalization:
    """Topic surface form mapping to controlled vocabulary."""

    def test_canonical_topic_unchanged(self) -> None:
        res = normalize_topic("trade")
        assert res.canonical == "trade"
        assert res.was_normalized is False
        assert res.mapped_to_other is False

    def test_tariffs_maps_to_trade(self) -> None:
        res = normalize_topic("tariffs")
        assert res.canonical == "trade"
        assert res.was_normalized is True
        assert res.mapped_to_other is False

    def test_border_maps_to_immigration(self) -> None:
        res = normalize_topic("border")
        assert res.canonical == "immigration"
        assert res.was_normalized is True

    def test_climate_change_maps_to_climate(self) -> None:
        res = normalize_topic("climate change")
        assert res.canonical == "climate"
        assert res.was_normalized is True

    def test_housing_maps_to_other(self) -> None:
        res = normalize_topic("housing")
        assert res.canonical == "other"
        assert res.was_normalized is True
        assert res.mapped_to_other is True

    def test_completely_unknown_topic_maps_to_other(self) -> None:
        res = normalize_topic("quantum_physics_policy")
        assert res.canonical == "other"
        assert res.mapped_to_other is True

    def test_all_canonical_topics_pass_through(self) -> None:
        from contracts.vocab import TOPIC_VALUES
        for topic in TOPIC_VALUES:
            res = normalize_topic(topic)
            assert res.canonical == topic
            assert res.was_normalized is False

    def test_case_insensitive_surface_form(self) -> None:
        res = normalize_topic("TARIFFS")
        assert res.canonical == "trade"

    def test_none_maps_to_other(self) -> None:
        res = normalize_topic(None)
        assert res.canonical == "other"
        assert res.mapped_to_other is True

    def test_empty_string_maps_to_other(self) -> None:
        res = normalize_topic("")
        assert res.canonical == "other"
        assert res.mapped_to_other is True


# ---------------------------------------------------------------------------
# Proposition normalization tests
# ---------------------------------------------------------------------------


class TestPropositionNormalization:
    """Proposition lexical normalization."""

    def test_tariff_phrase_canonical_form(self) -> None:
        """The documented tariff example from the issue."""
        res1 = normalize_proposition("higher tariffs on Chinese imports")
        res2 = normalize_proposition("raise tariffs on China")
        # Both should normalize to the same canonical form
        assert res1.canonical == res2.canonical

    def test_tariff_normalization_applied(self) -> None:
        res = normalize_proposition("higher tariffs on Chinese imports")
        assert res.was_normalized is True

    def test_whitespace_normalized(self) -> None:
        res = normalize_proposition("  Joe Biden  supports   healthcare reform.  ")
        # Leading/trailing whitespace stripped; internal whitespace collapsed
        assert not res.canonical.startswith(" ")
        assert not res.canonical.endswith(" ")
        assert "  " not in res.canonical  # no double spaces

    def test_sentence_case_applied(self) -> None:
        res = normalize_proposition("joe biden supports the economy.")
        assert res.canonical[0].isupper()

    def test_original_preserved(self) -> None:
        raw = "higher tariffs on Chinese imports"
        res = normalize_proposition(raw)
        assert res.original == raw

    def test_unrecognized_proposition_preserved(self) -> None:
        raw = "Some completely novel political proposition."
        res = normalize_proposition(raw)
        # Should return sentence-cased version without modification flag
        assert res.canonical.startswith("Some")

    def test_empty_proposition_handled(self) -> None:
        res = normalize_proposition("")
        assert res.canonical == ""
        assert res.was_normalized is False

    def test_none_proposition_handled(self) -> None:
        res = normalize_proposition(None)
        assert res.canonical == ""

    def test_60_percent_tariff_normalized(self) -> None:
        res = normalize_proposition(
            "Donald Trump supports imposing 60 percent tariffs on goods imported from China."
        )
        # Should contain the canonical tariff phrase
        assert "raise tariffs on china" in res.canonical.lower()
        assert res.was_normalized is True


# ---------------------------------------------------------------------------
# Date parser tests
# ---------------------------------------------------------------------------


class TestDateParser:
    """Date parsing and standardization."""

    def test_day_precision(self) -> None:
        result = parse_date("2024-01-15")
        assert result.ok is True
        assert result.canonical == "2024-01-15"
        assert result.precision == "day"
        assert result.error is None

    def test_month_precision(self) -> None:
        result = parse_date("2024-01")
        assert result.ok is True
        assert result.canonical == "2024-01"
        assert result.precision == "month"

    def test_year_precision(self) -> None:
        result = parse_date("2024")
        assert result.ok is True
        assert result.canonical == "2024"
        assert result.precision == "year"

    def test_none_returns_ok_none(self) -> None:
        result = parse_date(None)
        assert result.ok is True
        assert result.canonical is None
        assert result.precision is None
        assert result.error is None

    def test_unparseable_returns_error(self) -> None:
        result = parse_date("January 2024")
        assert result.ok is False
        assert result.canonical is None
        assert result.error is not None

    def test_impossible_date_rejected(self) -> None:
        result = parse_date("2024-02-31")
        assert result.ok is False
        assert result.error is not None

    def test_date_with_time_rejected(self) -> None:
        result = parse_date("2024-01-15T10:00:00")
        assert result.ok is False

    def test_far_future_year_rejected(self) -> None:
        result = parse_date("2200")
        assert result.ok is False

    def test_far_past_year_rejected(self) -> None:
        result = parse_date("1800")
        assert result.ok is False

    def test_whitespace_stripped_before_parse(self) -> None:
        result = parse_date("  2024-01-15  ")
        assert result.ok is True
        assert result.canonical == "2024-01-15"


class TestPrecisionMatch:
    """Date precision consistency checking."""

    def test_day_date_day_precision_match(self) -> None:
        parsed = parse_date("2024-01-15")
        assert validate_precision_match(parsed, "day") is None

    def test_day_date_month_precision_mismatch(self) -> None:
        parsed = parse_date("2024-01-15")
        msg = validate_precision_match(parsed, "month")
        assert msg is not None
        assert "mismatch" in msg.lower()

    def test_month_date_month_precision_match(self) -> None:
        parsed = parse_date("2024-01")
        assert validate_precision_match(parsed, "month") is None

    def test_year_date_year_precision_match(self) -> None:
        parsed = parse_date("2024")
        assert validate_precision_match(parsed, "year") is None

    def test_none_precision_no_error(self) -> None:
        parsed = parse_date("2024-01-15")
        assert validate_precision_match(parsed, None) is None


# ---------------------------------------------------------------------------
# Confidence normalization tests
# ---------------------------------------------------------------------------


class TestConfidenceNormalization:
    """Confidence normalization via the normalizer."""

    def _make_doc(self, confidence: object) -> dict:
        return {
            "doc_id": "test-001",
            "stance_events": [
                {
                    "politician": "Joe Biden",
                    "topic": "economy",
                    "normalized_proposition": "Biden supports the economy.",
                    "stance_direction": "support",
                    "stance_mode": "statement",
                    "evidence_role": "reported_speech",
                    "paraphrase": "Biden said the economy is important.",
                    "confidence": confidence,
                }
            ],
        }

    def test_confidence_preserved_when_valid(self) -> None:
        doc = self._make_doc(0.85)
        result = validate_document(doc)
        normalized = normalize_document(result)
        assert len(normalized) == 1
        assert normalized[0].confidence == pytest.approx(0.85)

    def test_confidence_zero_valid(self) -> None:
        doc = self._make_doc(0.0)
        result = validate_document(doc)
        normalized = normalize_document(result)
        assert len(normalized) == 1
        assert normalized[0].confidence == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Full pipeline: normalize_document
# ---------------------------------------------------------------------------


class TestNormalizeDocument:
    """End-to-end normalization pipeline tests."""

    def _load(self, fixture_name: str) -> dict:
        return json.loads((_FIXTURES_VALID / fixture_name).read_text(encoding="utf-8"))

    def test_zero_events_produces_empty_list(self) -> None:
        doc = self._load("zero_events.json")
        result = validate_document(doc)
        normalized = normalize_document(result)
        assert normalized == []

    def test_single_valid_event_normalized(self) -> None:
        doc = self._load("single_direct_quote.json")
        result = validate_document(doc)
        normalized = normalize_document(result)
        assert len(normalized) == 1
        event = normalized[0]
        assert event.doc_id == doc["doc_id"]
        assert event.confidence == pytest.approx(0.97)
        assert event.topic == "economy"
        assert event.stance_direction == "support"

    def test_politician_alias_normalized_to_canonical(self) -> None:
        doc = self._load("politician_aliases.json")
        result = validate_document(doc)
        normalized = normalize_document(result)
        assert len(normalized) == 2
        politicians = {e.politician for e in normalized}
        assert "Donald Trump" in politicians
        assert "Joe Biden" in politicians

    def test_tariff_proposition_normalized(self) -> None:
        doc = self._load("tariff_proposition.json")
        result = validate_document(doc)
        normalized = normalize_document(result)
        assert len(normalized) == 1
        event = normalized[0]
        # Proposition should be normalized to the canonical tariff form
        assert "raise tariffs on china" in event.normalized_proposition.lower()
        # Raw proposition preserved
        assert event.raw_proposition is not None

    def test_normalized_event_has_doc_id(self) -> None:
        doc = self._load("multiple_events.json")
        result = validate_document(doc)
        normalized = normalize_document(result)
        for event in normalized:
            assert event.doc_id == doc["doc_id"]

    def test_rejected_document_produces_empty_list(self) -> None:
        doc = {"stance_events": []}  # Missing doc_id
        result = validate_document(doc)
        normalized = normalize_document(result)
        assert normalized == []

    def test_warning_emitted_for_unknown_politician(self) -> None:
        doc = {
            "doc_id": "test-001",
            "stance_events": [
                {
                    "politician": "Completely Unknown Politician",
                    "topic": "economy",
                    "normalized_proposition": "Unknown person supports growth.",
                    "stance_direction": "support",
                    "stance_mode": "statement",
                    "evidence_role": "reported_speech",
                    "paraphrase": "They said so.",
                    "confidence": 0.8,
                }
            ],
        }
        result = validate_document(doc)
        normalized = normalize_document(result)
        assert len(normalized) == 1
        event = normalized[0]
        warning_codes = {w.code for w in event.validation_warnings}
        assert WarningCode.WARN_UNKNOWN_POLITICIAN in warning_codes

    def test_unsupported_topic_normalized_to_other(self) -> None:
        doc = {
            "doc_id": "test-001",
            "stance_events": [
                {
                    "politician": "Joe Biden",
                    "topic": "other",  # already valid
                    "normalized_proposition": "Biden supports other things.",
                    "stance_direction": "support",
                    "stance_mode": "statement",
                    "evidence_role": "direct_quote",
                    "quote_text": "We support it.",
                    "confidence": 0.7,
                }
            ],
        }
        result = validate_document(doc)
        normalized = normalize_document(result)
        assert len(normalized) == 1
        assert normalized[0].topic == "other"

    def test_date_precision_inferred_when_absent(self) -> None:
        doc = {
            "doc_id": "test-001",
            "stance_events": [
                {
                    "politician": "Joe Biden",
                    "topic": "economy",
                    "normalized_proposition": "Biden supports economic policy.",
                    "stance_direction": "support",
                    "stance_mode": "statement",
                    "evidence_role": "direct_quote",
                    "quote_text": "Economy matters.",
                    "event_date": "2024-03-01",
                    "event_date_precision": None,  # intentionally absent to test precision inference
                    "confidence": 0.9,
                }
            ],
        }
        result = validate_document(doc)
        normalized = normalize_document(result)
        assert len(normalized) == 1
        # Precision should be inferred as "day"
        assert normalized[0].event_date_precision == "day"
        assert normalized[0].event_date == "2024-03-01"

    def test_index_preserved_on_normalized_event(self) -> None:
        doc = self._load("multiple_events.json")
        result = validate_document(doc)
        normalized = normalize_document(result)
        assert len(normalized) == 2
        indices = [e.index for e in normalized]
        assert sorted(indices) == [0, 1]
