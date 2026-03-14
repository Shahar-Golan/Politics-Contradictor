"""
test_contract
=============
Tests for the stance extraction contract.

Covers:
- JSON schema accepts all valid fixtures
- JSON schema rejects invalid fixtures where appropriate
- Controlled vocabularies are internally consistent (Python ↔ JSON ↔ schema enum)
- Zero-event output is a valid top-level structure
- Multi-event output is a valid top-level structure
- All required fields are enforced
- Controlled vocabulary enum values are enforced
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_BASE = Path(__file__).parent.parent  # statement-processor/
_SCHEMA_PATH = _BASE / "schemas" / "stance_extraction.schema.json"
_FIXTURES_VALID = _BASE / "tests" / "fixtures" / "valid"
_FIXTURES_INVALID = _BASE / "tests" / "fixtures" / "invalid"
_VOCAB_JSON = _BASE / "src" / "contracts" / "vocab.json"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def _load_fixture(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate(instance: dict, schema: dict) -> None:
    """Validate *instance* against *schema*, raising jsonschema.ValidationError on failure."""
    validator_cls = jsonschema.validators.validator_for(schema)
    validator = validator_cls(schema)
    validator.validate(instance)


# ---------------------------------------------------------------------------
# Schema file presence
# ---------------------------------------------------------------------------


class TestSchemaFileExists:
    def test_schema_file_present(self) -> None:
        assert _SCHEMA_PATH.exists(), f"Schema file not found: {_SCHEMA_PATH}"

    def test_schema_is_valid_json(self) -> None:
        schema = _load_schema()
        assert isinstance(schema, dict)

    def test_schema_has_required_top_level_keys(self) -> None:
        schema = _load_schema()
        assert "properties" in schema
        assert "doc_id" in schema["properties"]
        assert "stance_events" in schema["properties"]


# ---------------------------------------------------------------------------
# Valid fixture tests
# ---------------------------------------------------------------------------


class TestValidFixtures:
    """Each valid fixture must pass jsonschema validation."""

    @pytest.fixture(autouse=True)
    def schema(self) -> dict:
        self._schema = _load_schema()

    def _assert_valid(self, fixture_name: str) -> dict:
        path = _FIXTURES_VALID / fixture_name
        assert path.exists(), f"Fixture not found: {path}"
        instance = _load_fixture(path)
        _validate(instance, self._schema)
        return instance

    def test_zero_events_is_valid(self) -> None:
        doc = self._assert_valid("zero_events.json")
        assert doc["stance_events"] == []

    def test_single_direct_quote_is_valid(self) -> None:
        doc = self._assert_valid("single_direct_quote.json")
        assert len(doc["stance_events"]) == 1
        event = doc["stance_events"][0]
        assert event["evidence_role"] == "direct_quote"
        assert event["stance_mode"] == "statement"

    def test_multiple_events_is_valid(self) -> None:
        doc = self._assert_valid("multiple_events.json")
        assert len(doc["stance_events"]) == 2

    def test_policy_action_is_valid(self) -> None:
        doc = self._assert_valid("policy_action.json")
        assert len(doc["stance_events"]) == 1
        event = doc["stance_events"][0]
        assert event["stance_mode"] == "action"
        assert event["evidence_role"] == "inferred_from_action"

    def test_reported_speech_is_valid(self) -> None:
        doc = self._assert_valid("reported_speech.json")
        assert len(doc["stance_events"]) == 1
        event = doc["stance_events"][0]
        assert event["evidence_role"] == "reported_speech"


# ---------------------------------------------------------------------------
# Invalid fixture tests
# ---------------------------------------------------------------------------


class TestInvalidFixtures:
    """Invalid fixtures must either fail to parse as JSON or fail schema validation."""

    @pytest.fixture(autouse=True)
    def schema(self) -> dict:
        self._schema = _load_schema()

    def test_malformed_json_cannot_be_parsed(self) -> None:
        path = _FIXTURES_INVALID / "malformed_json.txt"
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            json.loads(content)

    def test_unsupported_vocab_fails_validation(self) -> None:
        path = _FIXTURES_INVALID / "unsupported_vocab.json"
        assert path.exists()
        instance = _load_fixture(path)
        with pytest.raises(jsonschema.ValidationError):
            _validate(instance, self._schema)

    def test_missing_required_fields_fails_validation(self) -> None:
        path = _FIXTURES_INVALID / "missing_required_fields.json"
        assert path.exists()
        instance = _load_fixture(path)
        with pytest.raises(jsonschema.ValidationError):
            _validate(instance, self._schema)

    def test_text_outside_json_cannot_be_parsed(self) -> None:
        path = _FIXTURES_INVALID / "text_outside_json.txt"
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            json.loads(content)

    def test_merged_propositions_fails_length_note(self) -> None:
        """
        merged_propositions.json is structurally valid JSON and passes the
        schema (the schema cannot enforce single-proposition atomicity), but
        the normalized_proposition is far too long – it captures multiple
        distinct claims. This test documents the atomicity violation.
        """
        path = _FIXTURES_INVALID / "merged_propositions.json"
        assert path.exists()
        instance = _load_fixture(path)
        event = instance["stance_events"][0]
        # The violation: the proposition contains multiple claims separated by commas.
        # A valid atomic proposition has no internal list of separate claims.
        assert event["normalized_proposition"].count(",") >= 3, (
            "Expected multiple comma-separated claims indicating a merged proposition."
        )


# ---------------------------------------------------------------------------
# Vocabulary consistency tests
# ---------------------------------------------------------------------------


class TestVocabularyConsistency:
    """Python vocab, JSON vocab, and schema enums must all agree."""

    @pytest.fixture(autouse=True)
    def _load(self) -> None:
        self._schema = _load_schema()
        self._vocab_json = json.loads(_VOCAB_JSON.read_text(encoding="utf-8"))
        # Import Python vocab
        import sys
        src_dir = str(_BASE / "src")
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)
        from contracts.vocab import ALL_VOCABULARIES
        self._py_vocab = ALL_VOCABULARIES

    def _schema_enum(self, field: str) -> set[str]:
        props = self._schema["$defs"]["StanceEvent"]["properties"]
        return set(props[field]["enum"])

    def test_topic_vocab_matches_schema(self) -> None:
        assert self._schema_enum("topic") == set(self._vocab_json["topic"])
        assert self._schema_enum("topic") == self._py_vocab["topic"]

    def test_stance_direction_vocab_matches_schema(self) -> None:
        assert self._schema_enum("stance_direction") == set(self._vocab_json["stance_direction"])
        assert self._schema_enum("stance_direction") == self._py_vocab["stance_direction"]

    def test_stance_mode_vocab_matches_schema(self) -> None:
        assert self._schema_enum("stance_mode") == set(self._vocab_json["stance_mode"])
        assert self._schema_enum("stance_mode") == self._py_vocab["stance_mode"]

    def test_evidence_role_vocab_matches_schema(self) -> None:
        assert self._schema_enum("evidence_role") == set(self._vocab_json["evidence_role"])
        assert self._schema_enum("evidence_role") == self._py_vocab["evidence_role"]

    def test_event_date_precision_vocab_matches_schema(self) -> None:
        assert self._schema_enum("event_date_precision") == set(self._vocab_json["event_date_precision"])
        assert self._schema_enum("event_date_precision") == self._py_vocab["event_date_precision"]

    def test_no_vocab_key_is_empty(self) -> None:
        for key, values in self._py_vocab.items():
            assert len(values) > 0, f"Vocabulary '{key}' must not be empty."


# ---------------------------------------------------------------------------
# Schema structure tests
# ---------------------------------------------------------------------------


class TestSchemaStructure:
    """Verify the schema is structured correctly for downstream validators."""

    @pytest.fixture(autouse=True)
    def schema(self) -> None:
        self._schema = _load_schema()
        self._event_schema = self._schema["$defs"]["StanceEvent"]

    def test_required_fields_defined(self) -> None:
        required = set(self._event_schema["required"])
        expected = {
            "politician",
            "topic",
            "normalized_proposition",
            "stance_direction",
            "stance_mode",
            "evidence_role",
            "confidence",
        }
        assert expected.issubset(required)

    def test_confidence_has_bounds(self) -> None:
        conf = self._event_schema["properties"]["confidence"]
        assert conf["minimum"] == 0.0
        assert conf["maximum"] == 1.0

    def test_additional_properties_disallowed(self) -> None:
        assert self._event_schema.get("additionalProperties") is False

    def test_top_level_additional_properties_disallowed(self) -> None:
        assert self._schema.get("additionalProperties") is False

    def test_stance_events_is_array(self) -> None:
        prop = self._schema["properties"]["stance_events"]
        assert prop["type"] == "array"

    def test_doc_id_is_required(self) -> None:
        assert "doc_id" in self._schema["required"]
        assert "stance_events" in self._schema["required"]


# ---------------------------------------------------------------------------
# Inline schema validation tests (hand-crafted instances)
# ---------------------------------------------------------------------------


class TestInlineValidation:
    """Validate hand-crafted instances to exercise the schema directly."""

    @pytest.fixture(autouse=True)
    def schema(self) -> None:
        self._schema = _load_schema()

    def _minimal_event(self, **overrides) -> dict:
        base = {
            "politician": "Test Politician",
            "topic": "economy",
            "normalized_proposition": "Test proposition sentence.",
            "stance_direction": "support",
            "stance_mode": "statement",
            "evidence_role": "direct_quote",
            "confidence": 0.9,
        }
        base.update(overrides)
        return base

    def test_minimal_valid_instance_passes(self) -> None:
        instance = {"doc_id": "test-001", "stance_events": [self._minimal_event()]}
        _validate(instance, self._schema)

    def test_empty_doc_id_fails(self) -> None:
        instance = {"doc_id": "", "stance_events": []}
        with pytest.raises(jsonschema.ValidationError):
            _validate(instance, self._schema)

    def test_missing_doc_id_fails(self) -> None:
        instance = {"stance_events": []}
        with pytest.raises(jsonschema.ValidationError):
            _validate(instance, self._schema)

    def test_missing_stance_events_fails(self) -> None:
        instance = {"doc_id": "test-001"}
        with pytest.raises(jsonschema.ValidationError):
            _validate(instance, self._schema)

    def test_confidence_above_1_fails(self) -> None:
        instance = {"doc_id": "test-001", "stance_events": [self._minimal_event(confidence=1.1)]}
        with pytest.raises(jsonschema.ValidationError):
            _validate(instance, self._schema)

    def test_confidence_below_0_fails(self) -> None:
        instance = {"doc_id": "test-001", "stance_events": [self._minimal_event(confidence=-0.1)]}
        with pytest.raises(jsonschema.ValidationError):
            _validate(instance, self._schema)

    def test_invalid_topic_fails(self) -> None:
        instance = {"doc_id": "test-001", "stance_events": [self._minimal_event(topic="sports")]}
        with pytest.raises(jsonschema.ValidationError):
            _validate(instance, self._schema)

    def test_invalid_stance_direction_fails(self) -> None:
        instance = {"doc_id": "test-001", "stance_events": [self._minimal_event(stance_direction="maybe")]}
        with pytest.raises(jsonschema.ValidationError):
            _validate(instance, self._schema)

    def test_invalid_stance_mode_fails(self) -> None:
        instance = {"doc_id": "test-001", "stance_events": [self._minimal_event(stance_mode="speech")]}
        with pytest.raises(jsonschema.ValidationError):
            _validate(instance, self._schema)

    def test_invalid_evidence_role_fails(self) -> None:
        instance = {"doc_id": "test-001", "stance_events": [self._minimal_event(evidence_role="quote")]}
        with pytest.raises(jsonschema.ValidationError):
            _validate(instance, self._schema)

    def test_extra_top_level_field_fails(self) -> None:
        instance = {"doc_id": "test-001", "stance_events": [], "extra_field": "unexpected"}
        with pytest.raises(jsonschema.ValidationError):
            _validate(instance, self._schema)

    def test_extra_event_field_fails(self) -> None:
        event = self._minimal_event()
        event["unknown_field"] = "unexpected"
        instance = {"doc_id": "test-001", "stance_events": [event]}
        with pytest.raises(jsonschema.ValidationError):
            _validate(instance, self._schema)

    def test_all_topic_values_are_valid(self) -> None:
        import sys
        src_dir = str(_BASE / "src")
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)
        from contracts.vocab import TOPIC_VALUES
        for topic in TOPIC_VALUES:
            instance = {"doc_id": "test-topic", "stance_events": [self._minimal_event(topic=topic)]}
            _validate(instance, self._schema)

    def test_all_stance_direction_values_are_valid(self) -> None:
        import sys
        src_dir = str(_BASE / "src")
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)
        from contracts.vocab import STANCE_DIRECTION_VALUES
        for direction in STANCE_DIRECTION_VALUES:
            instance = {
                "doc_id": "test-dir",
                "stance_events": [self._minimal_event(stance_direction=direction)],
            }
            _validate(instance, self._schema)

    def test_all_stance_mode_values_are_valid(self) -> None:
        import sys
        src_dir = str(_BASE / "src")
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)
        from contracts.vocab import STANCE_MODE_VALUES
        for mode in STANCE_MODE_VALUES:
            instance = {
                "doc_id": "test-mode",
                "stance_events": [self._minimal_event(stance_mode=mode)],
            }
            _validate(instance, self._schema)

    def test_all_evidence_role_values_are_valid(self) -> None:
        import sys
        src_dir = str(_BASE / "src")
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)
        from contracts.vocab import EVIDENCE_ROLE_VALUES
        for role in EVIDENCE_ROLE_VALUES:
            instance = {
                "doc_id": "test-role",
                "stance_events": [self._minimal_event(evidence_role=role)],
            }
            _validate(instance, self._schema)
