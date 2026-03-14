"""
validation.validator
====================
Deterministic structural and semantic validator for raw extractor outputs.

This module is the **validation gate** — it decides whether each stance event
candidate is structurally sound and semantically plausible before normalization
is applied.

Design principles
-----------------
* Completely deterministic — no LLM calls, no randomness.
* Fails loudly on hard contract violations; emits warnings on soft issues.
* Separates document-level errors from per-event errors.
* Produces typed result objects (see ``validation.models``).

Entry points
------------
validate_document(raw: dict | Any) -> DocumentValidationResult
    Validate an entire parsed extractor document.

validate_candidate(event: dict, index: int, doc_id: str) -> EventValidationResult
    Validate a single stance event dict.
"""

from __future__ import annotations

from typing import Any

from contracts.vocab import (
    EVIDENCE_ROLE_VALUES,
    EVENT_DATE_PRECISION_VALUES,
    STANCE_DIRECTION_VALUES,
    STANCE_MODE_VALUES,
    TOPIC_VALUES,
)
from validation.date_parser import parse_date, validate_precision_match
from validation.errors import ErrorCode, ValidationError, ValidationWarning, WarningCode
from validation.models import (
    DocumentValidationResult,
    EventValidationResult,
    ValidationStatus,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Required fields for a valid StanceEvent
_REQUIRED_EVENT_FIELDS: tuple[str, ...] = (
    "politician",
    "topic",
    "normalized_proposition",
    "stance_direction",
    "stance_mode",
    "evidence_role",
    "confidence",
)

# Evidence roles that require a quote or paraphrase
_QUOTE_REQUIRED_ROLES = frozenset({"direct_quote"})
_PARAPHRASE_EXPECTED_ROLES = frozenset({"reported_speech", "inferred_from_action"})

# Heuristic: if a proposition contains 3+ commas it likely merges multiple claims
_ATOMICITY_COMMA_THRESHOLD = 3

# Heuristic: maximum plausible length for a normalized_proposition
_MAX_PROPOSITION_LEN = 400


# ---------------------------------------------------------------------------
# Document-level validation
# ---------------------------------------------------------------------------


def validate_document(raw: Any) -> DocumentValidationResult:
    """Validate an entire parsed extractor document.

    Parameters
    ----------
    raw:
        The parsed JSON object (expected to be a ``dict``).  Passing a
        non-dict is handled gracefully.

    Returns
    -------
    DocumentValidationResult
        Aggregated result containing per-event outcomes and document-level
        errors.
    """
    doc_errors: list[ValidationError] = []
    event_results: list[EventValidationResult] = []

    # Guard: must be a dict
    if not isinstance(raw, dict):
        doc_errors.append(
            ValidationError(
                code=ErrorCode.SHAPE_MISSING_DOC_ID,
                field=None,
                message=(
                    f"Expected a JSON object (dict) at the top level, "
                    f"got {type(raw).__name__!r}."
                ),
            )
        )
        return DocumentValidationResult(
            doc_id=None,
            status=ValidationStatus.REJECTED,
            document_errors=doc_errors,
            raw_input=None,
        )

    # Validate doc_id
    doc_id: str | None = None
    raw_doc_id = raw.get("doc_id")
    if raw_doc_id is None:
        doc_errors.append(
            ValidationError(
                code=ErrorCode.SHAPE_MISSING_DOC_ID,
                field="doc_id",
                message="Required field 'doc_id' is missing.",
            )
        )
    elif not isinstance(raw_doc_id, str):
        doc_errors.append(
            ValidationError(
                code=ErrorCode.FIELD_WRONG_TYPE,
                field="doc_id",
                message=f"'doc_id' must be a string, got {type(raw_doc_id).__name__!r}.",
            )
        )
    elif not raw_doc_id.strip():
        doc_errors.append(
            ValidationError(
                code=ErrorCode.SHAPE_EMPTY_DOC_ID,
                field="doc_id",
                message="'doc_id' must not be empty.",
            )
        )
    else:
        doc_id = raw_doc_id.strip()

    # Validate stance_events presence
    if "stance_events" not in raw:
        doc_errors.append(
            ValidationError(
                code=ErrorCode.SHAPE_MISSING_STANCE_EVENTS,
                field="stance_events",
                message="Required field 'stance_events' is missing.",
            )
        )
        return DocumentValidationResult(
            doc_id=doc_id,
            status=ValidationStatus.REJECTED,
            document_errors=doc_errors,
            raw_input=raw,
        )

    stance_events = raw["stance_events"]
    if not isinstance(stance_events, list):
        doc_errors.append(
            ValidationError(
                code=ErrorCode.SHAPE_STANCE_EVENTS_NOT_LIST,
                field="stance_events",
                message=(
                    f"'stance_events' must be an array, "
                    f"got {type(stance_events).__name__!r}."
                ),
            )
        )
        return DocumentValidationResult(
            doc_id=doc_id,
            status=ValidationStatus.REJECTED,
            document_errors=doc_errors,
            raw_input=raw,
        )

    # If doc-level errors exist at this point, reject entire document
    if doc_errors:
        return DocumentValidationResult(
            doc_id=doc_id,
            status=ValidationStatus.REJECTED,
            document_errors=doc_errors,
            raw_input=raw,
        )

    # Validate each event
    for idx, raw_event in enumerate(stance_events):
        result = validate_candidate(raw_event, index=idx, doc_id=doc_id or "")
        event_results.append(result)

    # Determine overall document status
    status = _aggregate_document_status(doc_errors, event_results)

    return DocumentValidationResult(
        doc_id=doc_id,
        status=status,
        document_errors=doc_errors,
        event_results=event_results,
        raw_input=raw,
    )


# ---------------------------------------------------------------------------
# Per-event validation
# ---------------------------------------------------------------------------


def validate_candidate(
    raw_event: Any,
    index: int,
    doc_id: str,
) -> EventValidationResult:
    """Validate a single raw stance event dict.

    Parameters
    ----------
    raw_event:
        The event dict as parsed from the extractor output.
    index:
        0-based position within the ``stance_events`` array.
    doc_id:
        Parent document identifier (used for error messages).

    Returns
    -------
    EventValidationResult
        Per-event outcome with errors and warnings.
    """
    errors: list[ValidationError] = []
    warnings: list[ValidationWarning] = []

    # Guard: must be a dict
    if not isinstance(raw_event, dict):
        errors.append(
            ValidationError(
                code=ErrorCode.SHAPE_EVENT_NOT_OBJECT,
                field=None,
                message=(
                    f"Event at index {index} must be a JSON object, "
                    f"got {type(raw_event).__name__!r}."
                ),
            )
        )
        return EventValidationResult(
            index=index,
            raw_event={} if not isinstance(raw_event, dict) else raw_event,
            status=ValidationStatus.REJECTED,
            errors=errors,
            warnings=warnings,
        )

    # --- Required field presence ---
    for field_name in _REQUIRED_EVENT_FIELDS:
        if field_name not in raw_event:
            errors.append(
                ValidationError(
                    code=ErrorCode.FIELD_MISSING_REQUIRED,
                    field=field_name,
                    message=f"Required field '{field_name}' is missing.",
                )
            )

    # If any required fields are absent, skip deeper checks
    if errors:
        return EventValidationResult(
            index=index,
            raw_event=raw_event,
            status=ValidationStatus.REJECTED,
            errors=errors,
            warnings=warnings,
        )

    # --- Politician ---
    _validate_politician(raw_event, errors, warnings)

    # --- topic ---
    _validate_vocab_field(raw_event, "topic", TOPIC_VALUES, errors)

    # --- normalized_proposition ---
    _validate_proposition(raw_event, errors, warnings)

    # --- stance_direction ---
    _validate_vocab_field(raw_event, "stance_direction", STANCE_DIRECTION_VALUES, errors)

    # --- stance_mode ---
    _validate_vocab_field(raw_event, "stance_mode", STANCE_MODE_VALUES, errors)

    # --- evidence_role ---
    _validate_vocab_field(raw_event, "evidence_role", EVIDENCE_ROLE_VALUES, errors)

    # --- confidence ---
    _validate_confidence(raw_event, errors, warnings)

    # --- event_date + event_date_precision (optional) ---
    _validate_date_fields(raw_event, errors, warnings)

    # --- evidence / quote ---
    _validate_evidence(raw_event, errors, warnings)

    # Determine status
    if errors:
        status = ValidationStatus.REJECTED
    elif warnings:
        status = ValidationStatus.VALID_WITH_WARNINGS
    else:
        status = ValidationStatus.VALID

    return EventValidationResult(
        index=index,
        raw_event=raw_event,
        status=status,
        errors=errors,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Field-level validators
# ---------------------------------------------------------------------------


def _validate_politician(
    event: dict[str, Any],
    errors: list[ValidationError],
    warnings: list[ValidationWarning],
) -> None:
    """Validate the ``politician`` field."""
    value = event.get("politician")
    if not isinstance(value, str):
        errors.append(
            ValidationError(
                code=ErrorCode.FIELD_WRONG_TYPE,
                field="politician",
                message=f"'politician' must be a string, got {type(value).__name__!r}.",
            )
        )
        return
    if not value.strip():
        errors.append(
            ValidationError(
                code=ErrorCode.FIELD_EMPTY_POLITICIAN,
                field="politician",
                message="'politician' must not be empty.",
            )
        )


def _validate_vocab_field(
    event: dict[str, Any],
    field_name: str,
    allowed: frozenset[str],
    errors: list[ValidationError],
) -> None:
    """Validate that *field_name* contains a value from *allowed*."""
    value = event.get(field_name)
    if not isinstance(value, str):
        errors.append(
            ValidationError(
                code=ErrorCode.FIELD_WRONG_TYPE,
                field=field_name,
                message=f"'{field_name}' must be a string, got {type(value).__name__!r}.",
            )
        )
        return

    code_map = {
        "topic": ErrorCode.FIELD_INVALID_TOPIC,
        "stance_direction": ErrorCode.FIELD_INVALID_STANCE_DIRECTION,
        "stance_mode": ErrorCode.FIELD_INVALID_STANCE_MODE,
        "evidence_role": ErrorCode.FIELD_INVALID_EVIDENCE_ROLE,
        "event_date_precision": ErrorCode.FIELD_INVALID_DATE_PRECISION,
    }
    error_code = code_map.get(field_name, ErrorCode.FIELD_WRONG_TYPE)

    if value not in allowed:
        errors.append(
            ValidationError(
                code=error_code,
                field=field_name,
                message=(
                    f"'{field_name}' value {value!r} is not in the controlled vocabulary. "
                    f"Allowed: {sorted(allowed)}."
                ),
            )
        )


def _validate_proposition(
    event: dict[str, Any],
    errors: list[ValidationError],
    warnings: list[ValidationWarning],
) -> None:
    """Validate the ``normalized_proposition`` field."""
    value = event.get("normalized_proposition")
    if not isinstance(value, str):
        errors.append(
            ValidationError(
                code=ErrorCode.FIELD_WRONG_TYPE,
                field="normalized_proposition",
                message=(
                    f"'normalized_proposition' must be a string, "
                    f"got {type(value).__name__!r}."
                ),
            )
        )
        return
    if not value.strip():
        errors.append(
            ValidationError(
                code=ErrorCode.FIELD_EMPTY_PROPOSITION,
                field="normalized_proposition",
                message="'normalized_proposition' must not be empty.",
            )
        )
        return

    # Atomicity heuristic: many commas suggest merged proposition
    comma_count = value.count(",")
    if comma_count >= _ATOMICITY_COMMA_THRESHOLD:
        errors.append(
            ValidationError(
                code=ErrorCode.ATOMICITY_MERGED_PROPOSITION,
                field="normalized_proposition",
                message=(
                    f"'normalized_proposition' contains {comma_count} commas, "
                    "which suggests multiple claims have been merged into one event. "
                    "Each event should express a single atomic proposition."
                ),
            )
        )

    # Length check
    if len(value) > _MAX_PROPOSITION_LEN:
        warnings.append(
            ValidationWarning(
                code=WarningCode.WARN_ATOMICITY_POSSIBLE_MERGE,
                field="normalized_proposition",
                message=(
                    f"'normalized_proposition' is {len(value)} characters long "
                    f"(threshold {_MAX_PROPOSITION_LEN}). This may indicate a "
                    "merged multi-claim proposition."
                ),
            )
        )


def _validate_confidence(
    event: dict[str, Any],
    errors: list[ValidationError],
    warnings: list[ValidationWarning],
) -> None:
    """Validate the ``confidence`` field."""
    value = event.get("confidence")
    if not isinstance(value, (int, float)):
        errors.append(
            ValidationError(
                code=ErrorCode.FIELD_CONFIDENCE_NOT_NUMBER,
                field="confidence",
                message=(
                    f"'confidence' must be a number (float), "
                    f"got {type(value).__name__!r}."
                ),
            )
        )
        return

    float_val = float(value)
    if float_val < 0.0 or float_val > 1.0:
        errors.append(
            ValidationError(
                code=ErrorCode.FIELD_CONFIDENCE_OUT_OF_RANGE,
                field="confidence",
                message=(
                    f"'confidence' value {float_val} is outside the allowed "
                    "range [0.0, 1.0]."
                ),
            )
        )


def _validate_date_fields(
    event: dict[str, Any],
    errors: list[ValidationError],
    warnings: list[ValidationWarning],
) -> None:
    """Validate optional ``event_date`` and ``event_date_precision`` fields."""
    raw_date = event.get("event_date")
    raw_precision = event.get("event_date_precision")

    # If both are absent, that's fine (both are optional)
    if raw_date is None and raw_precision is None:
        return

    # Validate event_date_precision if present
    if raw_precision is not None:
        _validate_vocab_field(
            {"event_date_precision": raw_precision},
            "event_date_precision",
            EVENT_DATE_PRECISION_VALUES,
            errors,
        )

    # Validate and parse event_date if present
    if raw_date is not None:
        parsed = parse_date(raw_date if isinstance(raw_date, str) else str(raw_date))
        if not parsed.ok:
            errors.append(
                ValidationError(
                    code=ErrorCode.FIELD_UNPARSEABLE_DATE,
                    field="event_date",
                    message=f"'event_date' could not be parsed: {parsed.error}",
                )
            )
        else:
            # Check precision consistency
            mismatch_msg = validate_precision_match(parsed, raw_precision)
            if mismatch_msg:
                errors.append(
                    ValidationError(
                        code=ErrorCode.FIELD_DATE_PRECISION_MISMATCH,
                        field="event_date_precision",
                        message=mismatch_msg,
                    )
                )
            # If precision was absent but date was parseable, note it
            if raw_precision is None and parsed.precision:
                warnings.append(
                    ValidationWarning(
                        code=WarningCode.WARN_DATE_PRECISION_INFERRED,
                        field="event_date_precision",
                        message=(
                            f"'event_date_precision' is absent; inferred "
                            f"'{parsed.precision}' from date '{raw_date}'."
                        ),
                    )
                )


def _validate_evidence(
    event: dict[str, Any],
    errors: list[ValidationError],
    warnings: list[ValidationWarning],
) -> None:
    """Validate evidence fields: quote_text, quote spans, paraphrase."""
    evidence_role = event.get("evidence_role")
    quote_text = event.get("quote_text")
    quote_start = event.get("quote_start_char")
    quote_end = event.get("quote_end_char")
    paraphrase = event.get("paraphrase")

    # direct_quote: quote_text is required and must be non-empty
    if evidence_role in _QUOTE_REQUIRED_ROLES:
        if quote_text is None:
            errors.append(
                ValidationError(
                    code=ErrorCode.EVIDENCE_MISSING_QUOTE,
                    field="quote_text",
                    message=(
                        f"'quote_text' is required when 'evidence_role' is "
                        f"'{evidence_role}'."
                    ),
                )
            )
        elif not isinstance(quote_text, str) or not quote_text.strip():
            errors.append(
                ValidationError(
                    code=ErrorCode.EVIDENCE_EMPTY_QUOTE,
                    field="quote_text",
                    message=(
                        f"'quote_text' must be a non-empty string when "
                        f"'evidence_role' is '{evidence_role}'."
                    ),
                )
            )

    # Validate quote span consistency if span is provided
    if quote_start is not None or quote_end is not None:
        if quote_text is None:
            errors.append(
                ValidationError(
                    code=ErrorCode.EVIDENCE_SPAN_WITHOUT_TEXT,
                    field="quote_start_char",
                    message=(
                        "Quote span offsets (quote_start_char / quote_end_char) "
                        "are provided but 'quote_text' is absent."
                    ),
                )
            )
        else:
            _validate_quote_span(quote_start, quote_end, quote_text, errors)

    # Warn if reported_speech / inferred_from_action lacks paraphrase
    if evidence_role in _PARAPHRASE_EXPECTED_ROLES:
        if paraphrase is None or (isinstance(paraphrase, str) and not paraphrase.strip()):
            warnings.append(
                ValidationWarning(
                    code=WarningCode.WARN_MISSING_EVIDENCE_PARAPHRASE,
                    field="paraphrase",
                    message=(
                        f"'paraphrase' is absent or empty for evidence_role "
                        f"'{evidence_role}'. A paraphrase is strongly recommended."
                    ),
                )
            )


def _validate_quote_span(
    start: Any,
    end: Any,
    quote_text: str,
    errors: list[ValidationError],
) -> None:
    """Check that quote span indices are structurally plausible."""
    if not isinstance(start, int) or not isinstance(end, int):
        errors.append(
            ValidationError(
                code=ErrorCode.EVIDENCE_IMPLAUSIBLE_SPAN,
                field="quote_start_char",
                message=(
                    "Quote span offsets must be integers; "
                    f"got start={type(start).__name__!r}, end={type(end).__name__!r}."
                ),
            )
        )
        return

    if start < 0:
        errors.append(
            ValidationError(
                code=ErrorCode.EVIDENCE_IMPLAUSIBLE_SPAN,
                field="quote_start_char",
                message=f"'quote_start_char' must be >= 0, got {start}.",
            )
        )
    if end < 0:
        errors.append(
            ValidationError(
                code=ErrorCode.EVIDENCE_IMPLAUSIBLE_SPAN,
                field="quote_end_char",
                message=f"'quote_end_char' must be >= 0, got {end}.",
            )
        )
    if start >= 0 and end >= 0 and start >= end:
        errors.append(
            ValidationError(
                code=ErrorCode.EVIDENCE_IMPLAUSIBLE_SPAN,
                field="quote_start_char",
                message=(
                    f"'quote_start_char' ({start}) must be strictly less than "
                    f"'quote_end_char' ({end})."
                ),
            )
        )
    # Note: span offsets are into the original article body, not into
    # quote_text itself. We therefore only check structural plausibility
    # (non-negative, start < end) and do not require span_len == len(quote_text).


# ---------------------------------------------------------------------------
# Status aggregation
# ---------------------------------------------------------------------------


def _aggregate_document_status(
    doc_errors: list[ValidationError],
    event_results: list[EventValidationResult],
) -> ValidationStatus:
    """Compute the overall document status from document and event errors."""
    if doc_errors:
        return ValidationStatus.REJECTED

    if not event_results:
        # Zero events is a valid document
        return ValidationStatus.VALID

    all_valid = all(r.status == ValidationStatus.VALID for r in event_results)
    any_rejected = any(r.status == ValidationStatus.REJECTED for r in event_results)
    any_warnings = any(r.status == ValidationStatus.VALID_WITH_WARNINGS for r in event_results)

    if all_valid:
        return ValidationStatus.VALID
    if any_rejected and not any(r.is_accepted for r in event_results):
        # Every event was rejected
        return ValidationStatus.REJECTED
    if any_warnings or any_rejected:
        return ValidationStatus.VALID_WITH_WARNINGS
    return ValidationStatus.VALID
