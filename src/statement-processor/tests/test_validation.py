"""
test_validation
===============
Tests for the deterministic validation layer.

Covers:
- Valid fixture passes validation
- Invalid fixture fails with clear rejection reason
- Zero-event output is handled correctly
- Mixed valid/invalid multi-event output is handled correctly
- Structural shape errors (missing doc_id, missing stance_events, etc.)
- Vocabulary violations are rejected
- Required field absence is rejected
- Confidence out of range is rejected
- Date format violations are rejected
- Date precision mismatch is rejected
- Evidence span validation
- Atomicity (merged proposition) detection
- Direct quote evidence role requires quote_text
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
_FIXTURES_INVALID = _BASE / "tests" / "fixtures" / "invalid"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_fixture(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _doc(fixture_name: str) -> dict:
    """Load a fixture from the valid directory."""
    return _load_fixture(_FIXTURES_VALID / fixture_name)


def _invalid_doc(fixture_name: str) -> dict:
    """Load a fixture from the invalid directory."""
    return _load_fixture(_FIXTURES_INVALID / fixture_name)


# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

from validation.validator import validate_document, validate_candidate
from validation.models import ValidationStatus
from validation.errors import ErrorCode


# ---------------------------------------------------------------------------
# Valid fixture tests
# ---------------------------------------------------------------------------


class TestValidFixtures:
    """All valid fixtures must produce VALID or VALID_WITH_WARNINGS status."""

    def test_zero_events_is_valid(self) -> None:
        doc = _doc("zero_events.json")
        result = validate_document(doc)
        assert result.status in (ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS)
        assert result.doc_id == "article-no-stances-001"
        assert result.total_count == 0
        assert result.accepted_count == 0
        assert not result.document_errors

    def test_single_direct_quote_is_valid(self) -> None:
        doc = _doc("single_direct_quote.json")
        result = validate_document(doc)
        assert result.doc_id == "article-direct-quote-001"
        assert result.total_count == 1
        assert result.accepted_count == 1
        assert result.rejected_count == 0
        assert not result.document_errors

    def test_multiple_events_is_valid(self) -> None:
        doc = _doc("multiple_events.json")
        result = validate_document(doc)
        assert result.total_count == 2
        assert result.accepted_count == 2
        assert result.rejected_count == 0

    def test_policy_action_is_valid(self) -> None:
        doc = _doc("policy_action.json")
        result = validate_document(doc)
        assert result.accepted_count >= 1

    def test_reported_speech_is_valid(self) -> None:
        doc = _doc("reported_speech.json")
        result = validate_document(doc)
        assert result.accepted_count >= 1

    def test_tariff_proposition_is_valid(self) -> None:
        doc = _doc("tariff_proposition.json")
        result = validate_document(doc)
        assert result.accepted_count == 1

    def test_politician_aliases_is_valid(self) -> None:
        doc = _doc("politician_aliases.json")
        result = validate_document(doc)
        assert result.total_count == 2
        assert result.accepted_count == 2


# ---------------------------------------------------------------------------
# Invalid fixture tests
# ---------------------------------------------------------------------------


class TestInvalidFixtures:
    """Invalid fixtures must be rejected with clear error codes."""

    def test_missing_required_fields_rejected(self) -> None:
        doc = _invalid_doc("missing_required_fields.json")
        result = validate_document(doc)
        # Event must be rejected
        assert result.rejected_count >= 1
        rejected = result.rejected_events[0]
        error_codes = {e.code for e in rejected.errors}
        assert ErrorCode.FIELD_MISSING_REQUIRED in error_codes

    def test_unsupported_vocab_rejected(self) -> None:
        doc = _invalid_doc("unsupported_vocab.json")
        result = validate_document(doc)
        assert result.rejected_count >= 1
        rejected = result.rejected_events[0]
        error_codes = {e.code for e in rejected.errors}
        assert any(
            c in error_codes
            for c in (
                ErrorCode.FIELD_INVALID_TOPIC,
                ErrorCode.FIELD_INVALID_STANCE_DIRECTION,
                ErrorCode.FIELD_INVALID_STANCE_MODE,
                ErrorCode.FIELD_INVALID_EVIDENCE_ROLE,
            )
        )

    def test_merged_propositions_rejected(self) -> None:
        doc = _invalid_doc("merged_propositions.json")
        result = validate_document(doc)
        assert result.rejected_count >= 1
        rejected = result.rejected_events[0]
        error_codes = {e.code for e in rejected.errors}
        assert ErrorCode.ATOMICITY_MERGED_PROPOSITION in error_codes

    def test_bad_confidence_type_rejected(self) -> None:
        doc = _invalid_doc("bad_confidence_type.json")
        result = validate_document(doc)
        assert result.rejected_count >= 1
        rejected = result.rejected_events[0]
        error_codes = {e.code for e in rejected.errors}
        assert ErrorCode.FIELD_CONFIDENCE_NOT_NUMBER in error_codes

    def test_bad_date_format_rejected(self) -> None:
        doc = _invalid_doc("bad_date_format.json")
        result = validate_document(doc)
        assert result.rejected_count >= 1
        rejected = result.rejected_events[0]
        error_codes = {e.code for e in rejected.errors}
        assert ErrorCode.FIELD_UNPARSEABLE_DATE in error_codes


# ---------------------------------------------------------------------------
# Document-level shape tests
# ---------------------------------------------------------------------------


class TestDocumentShape:
    def test_non_dict_input_is_rejected(self) -> None:
        result = validate_document("not a dict")
        assert result.status == ValidationStatus.REJECTED
        assert result.doc_id is None

    def test_missing_doc_id_is_rejected(self) -> None:
        result = validate_document({"stance_events": []})
        assert result.status == ValidationStatus.REJECTED
        error_codes = {e.code for e in result.document_errors}
        assert ErrorCode.SHAPE_MISSING_DOC_ID in error_codes

    def test_empty_doc_id_is_rejected(self) -> None:
        result = validate_document({"doc_id": "", "stance_events": []})
        assert result.status == ValidationStatus.REJECTED
        error_codes = {e.code for e in result.document_errors}
        assert ErrorCode.SHAPE_EMPTY_DOC_ID in error_codes

    def test_missing_stance_events_is_rejected(self) -> None:
        result = validate_document({"doc_id": "test-001"})
        assert result.status == ValidationStatus.REJECTED
        error_codes = {e.code for e in result.document_errors}
        assert ErrorCode.SHAPE_MISSING_STANCE_EVENTS in error_codes

    def test_stance_events_not_list_is_rejected(self) -> None:
        result = validate_document({"doc_id": "test-001", "stance_events": "not-a-list"})
        assert result.status == ValidationStatus.REJECTED
        error_codes = {e.code for e in result.document_errors}
        assert ErrorCode.SHAPE_STANCE_EVENTS_NOT_LIST in error_codes

    def test_zero_events_document_is_valid(self) -> None:
        result = validate_document({"doc_id": "test-001", "stance_events": []})
        assert result.status == ValidationStatus.VALID
        assert result.total_count == 0


# ---------------------------------------------------------------------------
# Confidence validation tests
# ---------------------------------------------------------------------------


class TestConfidenceValidation:
    def _minimal_event(self, **overrides: object) -> dict:
        base: dict = {
            "politician": "Joe Biden",
            "topic": "economy",
            "normalized_proposition": "Biden supports economic growth.",
            "stance_direction": "support",
            "stance_mode": "statement",
            "evidence_role": "reported_speech",
            "confidence": 0.9,
        }
        base.update(overrides)
        return base

    def _doc(self, **event_overrides: object) -> dict:
        return {"doc_id": "test-001", "stance_events": [self._minimal_event(**event_overrides)]}

    def test_confidence_at_zero_is_valid(self) -> None:
        result = validate_document(self._doc(confidence=0.0))
        assert result.accepted_count == 1

    def test_confidence_at_one_is_valid(self) -> None:
        result = validate_document(self._doc(confidence=1.0))
        assert result.accepted_count == 1

    def test_confidence_above_one_is_rejected(self) -> None:
        result = validate_document(self._doc(confidence=1.1))
        assert result.rejected_count == 1
        error_codes = {e.code for e in result.rejected_events[0].errors}
        assert ErrorCode.FIELD_CONFIDENCE_OUT_OF_RANGE in error_codes

    def test_confidence_below_zero_is_rejected(self) -> None:
        result = validate_document(self._doc(confidence=-0.1))
        assert result.rejected_count == 1
        error_codes = {e.code for e in result.rejected_events[0].errors}
        assert ErrorCode.FIELD_CONFIDENCE_OUT_OF_RANGE in error_codes

    def test_confidence_as_string_is_rejected(self) -> None:
        result = validate_document(self._doc(confidence="high"))
        assert result.rejected_count == 1
        error_codes = {e.code for e in result.rejected_events[0].errors}
        assert ErrorCode.FIELD_CONFIDENCE_NOT_NUMBER in error_codes

    def test_confidence_as_int_is_valid(self) -> None:
        # Integer 1 should be accepted as 1.0
        result = validate_document(self._doc(confidence=1))
        assert result.accepted_count == 1


# ---------------------------------------------------------------------------
# Vocabulary validation tests
# ---------------------------------------------------------------------------


class TestVocabularyValidation:
    def _doc_with_event(self, **overrides: object) -> dict:
        base: dict = {
            "politician": "Donald Trump",
            "topic": "trade",
            "normalized_proposition": "Trump supports tariffs.",
            "stance_direction": "support",
            "stance_mode": "statement",
            "evidence_role": "reported_speech",
            "confidence": 0.85,
        }
        base.update(overrides)
        return {"doc_id": "test-001", "stance_events": [base]}

    def test_invalid_topic_rejected(self) -> None:
        result = validate_document(self._doc_with_event(topic="sports"))
        assert result.rejected_count == 1
        codes = {e.code for e in result.rejected_events[0].errors}
        assert ErrorCode.FIELD_INVALID_TOPIC in codes

    def test_invalid_stance_direction_rejected(self) -> None:
        result = validate_document(self._doc_with_event(stance_direction="yes"))
        assert result.rejected_count == 1
        codes = {e.code for e in result.rejected_events[0].errors}
        assert ErrorCode.FIELD_INVALID_STANCE_DIRECTION in codes

    def test_invalid_stance_mode_rejected(self) -> None:
        result = validate_document(self._doc_with_event(stance_mode="speech"))
        assert result.rejected_count == 1
        codes = {e.code for e in result.rejected_events[0].errors}
        assert ErrorCode.FIELD_INVALID_STANCE_MODE in codes

    def test_invalid_evidence_role_rejected(self) -> None:
        result = validate_document(self._doc_with_event(evidence_role="quote"))
        assert result.rejected_count == 1
        codes = {e.code for e in result.rejected_events[0].errors}
        assert ErrorCode.FIELD_INVALID_EVIDENCE_ROLE in codes


# ---------------------------------------------------------------------------
# Date validation tests
# ---------------------------------------------------------------------------


class TestDateValidation:
    def _doc_with_date(self, event_date: str | None, precision: str | None) -> dict:
        event: dict = {
            "politician": "Donald Trump",
            "topic": "trade",
            "normalized_proposition": "Trump supports tariffs.",
            "stance_direction": "support",
            "stance_mode": "statement",
            "evidence_role": "direct_quote",
            "quote_text": "We need tariffs.",
            "quote_start_char": 0,
            "quote_end_char": 16,
            "confidence": 0.9,
        }
        if event_date is not None:
            event["event_date"] = event_date
        if precision is not None:
            event["event_date_precision"] = precision
        return {"doc_id": "test-001", "stance_events": [event]}

    def test_valid_day_date_accepted(self) -> None:
        result = validate_document(self._doc_with_date("2024-01-15", "day"))
        assert result.accepted_count == 1

    def test_valid_month_date_accepted(self) -> None:
        result = validate_document(self._doc_with_date("2024-01", "month"))
        assert result.accepted_count == 1

    def test_valid_year_date_accepted(self) -> None:
        result = validate_document(self._doc_with_date("2024", "year"))
        assert result.accepted_count == 1

    def test_unparseable_date_rejected(self) -> None:
        result = validate_document(self._doc_with_date("January 2024", "day"))
        assert result.rejected_count == 1
        codes = {e.code for e in result.rejected_events[0].errors}
        assert ErrorCode.FIELD_UNPARSEABLE_DATE in codes

    def test_precision_mismatch_rejected(self) -> None:
        # "2024-01-15" is a day, but precision says "month"
        result = validate_document(self._doc_with_date("2024-01-15", "month"))
        assert result.rejected_count == 1
        codes = {e.code for e in result.rejected_events[0].errors}
        assert ErrorCode.FIELD_DATE_PRECISION_MISMATCH in codes

    def test_date_without_precision_emits_warning(self) -> None:
        result = validate_document(self._doc_with_date("2024-01-15", None))
        # Should be accepted with a warning about inferred precision
        assert result.accepted_count == 1
        accepted = result.accepted_events[0]
        warning_codes = {w.code for w in accepted.warnings}
        from validation.errors import WarningCode
        assert WarningCode.WARN_DATE_PRECISION_INFERRED in warning_codes

    def test_impossible_calendar_day_rejected(self) -> None:
        result = validate_document(self._doc_with_date("2024-02-31", "day"))
        assert result.rejected_count == 1
        codes = {e.code for e in result.rejected_events[0].errors}
        assert ErrorCode.FIELD_UNPARSEABLE_DATE in codes


# ---------------------------------------------------------------------------
# Evidence validation tests
# ---------------------------------------------------------------------------


class TestEvidenceValidation:
    def _base_event(self) -> dict:
        return {
            "politician": "Joe Biden",
            "topic": "economy",
            "normalized_proposition": "Biden supports the economy.",
            "stance_direction": "support",
            "stance_mode": "statement",
            "confidence": 0.85,
        }

    def _doc(self, event: dict) -> dict:
        return {"doc_id": "test-001", "stance_events": [event]}

    def test_direct_quote_without_quote_text_rejected(self) -> None:
        event = self._base_event()
        event["evidence_role"] = "direct_quote"
        # No quote_text provided
        result = validate_document(self._doc(event))
        assert result.rejected_count == 1
        codes = {e.code for e in result.rejected_events[0].errors}
        assert ErrorCode.EVIDENCE_MISSING_QUOTE in codes

    def test_direct_quote_with_empty_quote_text_rejected(self) -> None:
        event = self._base_event()
        event["evidence_role"] = "direct_quote"
        event["quote_text"] = "   "
        result = validate_document(self._doc(event))
        assert result.rejected_count == 1
        codes = {e.code for e in result.rejected_events[0].errors}
        assert ErrorCode.EVIDENCE_EMPTY_QUOTE in codes

    def test_direct_quote_with_valid_quote_text_accepted(self) -> None:
        event = self._base_event()
        event["evidence_role"] = "direct_quote"
        event["quote_text"] = "We will grow the economy."
        result = validate_document(self._doc(event))
        assert result.accepted_count == 1

    def test_span_without_quote_text_rejected(self) -> None:
        event = self._base_event()
        event["evidence_role"] = "reported_speech"
        event["quote_start_char"] = 0
        event["quote_end_char"] = 10
        result = validate_document(self._doc(event))
        assert result.rejected_count == 1
        codes = {e.code for e in result.rejected_events[0].errors}
        assert ErrorCode.EVIDENCE_SPAN_WITHOUT_TEXT in codes

    def test_implausible_span_start_ge_end_rejected(self) -> None:
        event = self._base_event()
        event["evidence_role"] = "direct_quote"
        event["quote_text"] = "Some quote here."
        event["quote_start_char"] = 10
        event["quote_end_char"] = 5
        result = validate_document(self._doc(event))
        assert result.rejected_count == 1
        codes = {e.code for e in result.rejected_events[0].errors}
        assert ErrorCode.EVIDENCE_IMPLAUSIBLE_SPAN in codes

    def test_span_start_negative_rejected(self) -> None:
        event = self._base_event()
        event["evidence_role"] = "direct_quote"
        event["quote_text"] = "Some quote."
        event["quote_start_char"] = -1
        event["quote_end_char"] = 11
        result = validate_document(self._doc(event))
        assert result.rejected_count == 1
        codes = {e.code for e in result.rejected_events[0].errors}
        assert ErrorCode.EVIDENCE_IMPLAUSIBLE_SPAN in codes

    def test_reported_speech_without_paraphrase_warns(self) -> None:
        event = self._base_event()
        event["evidence_role"] = "reported_speech"
        # No paraphrase
        result = validate_document(self._doc(event))
        assert result.accepted_count == 1
        accepted = result.accepted_events[0]
        warning_codes = {w.code for w in accepted.warnings}
        from validation.errors import WarningCode
        assert WarningCode.WARN_MISSING_EVIDENCE_PARAPHRASE in warning_codes


# ---------------------------------------------------------------------------
# Mixed valid/invalid event tests
# ---------------------------------------------------------------------------


class TestMixedEvents:
    """Documents with some valid and some invalid events."""

    def test_partial_rejection_preserves_valid_events(self) -> None:
        doc = {
            "doc_id": "mixed-001",
            "stance_events": [
                {
                    "politician": "Joe Biden",
                    "topic": "economy",
                    "normalized_proposition": "Biden supports the economy.",
                    "stance_direction": "support",
                    "stance_mode": "statement",
                    "evidence_role": "direct_quote",
                    "quote_text": "We grow together.",
                    "confidence": 0.9,
                },
                {
                    "politician": "Joe Biden",
                    "topic": "housing",  # not in vocab → will be normalized to "other"
                    "normalized_proposition": "Biden supports affordable housing.",
                    "stance_direction": "yes",  # invalid
                    "stance_mode": "statement",
                    "evidence_role": "direct_quote",
                    "quote_text": "Housing for all.",
                    "confidence": 0.8,
                },
            ],
        }
        result = validate_document(doc)
        assert result.accepted_count == 1
        assert result.rejected_count == 1
        # Overall status should be VALID_WITH_WARNINGS (some accepted, some rejected)
        assert result.status == ValidationStatus.VALID_WITH_WARNINGS

    def test_all_rejected_gives_rejected_status(self) -> None:
        doc = {
            "doc_id": "all-bad-001",
            "stance_events": [
                {
                    "politician": "Joe Biden",
                    "topic": "economy",
                    # Missing required fields
                    "confidence": 0.5,
                },
            ],
        }
        result = validate_document(doc)
        assert result.rejected_count == 1
        assert result.accepted_count == 0
        assert result.status == ValidationStatus.REJECTED


# ---------------------------------------------------------------------------
# Atomicity tests
# ---------------------------------------------------------------------------


class TestAtomicity:
    def test_merged_proposition_comma_threshold(self) -> None:
        event = {
            "politician": "Donald Trump",
            "topic": "immigration",
            "normalized_proposition": (
                "Trump opposes open borders, supports a border wall, "
                "wants to deport undocumented immigrants, and opposes birthright citizenship."
            ),
            "stance_direction": "oppose",
            "stance_mode": "statement",
            "evidence_role": "direct_quote",
            "quote_text": "We need to do all of this.",
            "confidence": 0.85,
        }
        result = validate_document({"doc_id": "test-001", "stance_events": [event]})
        assert result.rejected_count == 1
        codes = {e.code for e in result.rejected_events[0].errors}
        assert ErrorCode.ATOMICITY_MERGED_PROPOSITION in codes
