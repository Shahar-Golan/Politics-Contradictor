"""
validation.normalizer
=====================
Normalization orchestrator for validated stance event candidates.

This module takes the output of the validator (a ``DocumentValidationResult``)
and produces ``NormalizedStanceEvent`` objects by:

1. Skipping rejected events.
2. Normalizing politician names (via ``politician_normalization``).
3. Normalizing topics (via ``topic_normalization``).
4. Normalizing propositions (via ``proposition_normalization``).
5. Parsing and standardizing dates (via ``date_parser``).
6. Normalizing confidence to [0.0, 1.0] (clamping if needed).
7. Normalizing optional string fields (whitespace stripping).
8. Propagating warnings from validation through to the output.

Entry points
------------
normalize_document(result: DocumentValidationResult) -> list[NormalizedStanceEvent]
    Normalize all accepted events in a validated document.

normalize_candidate(
    event_result: EventValidationResult,
    doc_id: str,
) -> NormalizedStanceEvent | None
    Normalize a single accepted event result.  Returns ``None`` for rejected
    events.
"""

from __future__ import annotations

from typing import Any

from validation.date_parser import parse_date
from validation.errors import ValidationWarning, WarningCode
from validation.models import (
    DocumentValidationResult,
    EventValidationResult,
    NormalizedStanceEvent,
    ValidationStatus,
)
from validation.politician_normalization import resolve_politician
from validation.proposition_normalization import normalize_proposition
from validation.topic_normalization import normalize_topic

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def normalize_document(
    result: DocumentValidationResult,
) -> list[NormalizedStanceEvent]:
    """Normalize all accepted events in a validated document.

    Rejected events are silently skipped.

    Parameters
    ----------
    result:
        The output of :func:`validation.validator.validate_document`.

    Returns
    -------
    list[NormalizedStanceEvent]
        One normalized event for each accepted event in the document.
        May be empty if the document was fully rejected or had zero events.
    """
    if result.doc_id is None:
        return []

    normalized: list[NormalizedStanceEvent] = []
    for event_result in result.accepted_events:
        norm = normalize_candidate(event_result, doc_id=result.doc_id)
        if norm is not None:
            normalized.append(norm)
    return normalized


def normalize_candidate(
    event_result: EventValidationResult,
    doc_id: str,
) -> NormalizedStanceEvent | None:
    """Normalize a single accepted event.

    Parameters
    ----------
    event_result:
        The per-event validation outcome.  Rejected events return ``None``.
    doc_id:
        Parent document identifier.

    Returns
    -------
    NormalizedStanceEvent | None
        The normalized event, or ``None`` if the event was rejected.
    """
    if not event_result.is_accepted:
        return None

    raw = event_result.raw_event
    # Start with warnings already emitted by the validator
    warnings: list[ValidationWarning] = list(event_result.warnings)

    # --- Politician ---
    raw_politician: str = raw.get("politician", "") or ""
    politician_res = resolve_politician(raw_politician)
    if politician_res.was_normalized:
        warnings.append(
            ValidationWarning(
                code=WarningCode.WARN_POLITICIAN_NORMALIZED,
                field="politician",
                message=(
                    f"Politician name normalized: {raw_politician!r} → "
                    f"{politician_res.canonical!r}."
                ),
            )
        )
    if not politician_res.is_known:
        warnings.append(
            ValidationWarning(
                code=WarningCode.WARN_UNKNOWN_POLITICIAN,
                field="politician",
                message=(
                    f"Politician {raw_politician!r} is not in the known alias "
                    "map. Keeping original name."
                ),
            )
        )

    # --- Topic ---
    raw_topic: str = raw.get("topic", "") or ""
    topic_res = normalize_topic(raw_topic)
    if topic_res.was_normalized:
        if topic_res.mapped_to_other:
            warnings.append(
                ValidationWarning(
                    code=WarningCode.WARN_TOPIC_MAPPED_TO_OTHER,
                    field="topic",
                    message=(
                        f"Topic {raw_topic!r} is not in the controlled vocabulary "
                        "and was mapped to 'other'."
                    ),
                )
            )
        else:
            warnings.append(
                ValidationWarning(
                    code=WarningCode.WARN_TOPIC_NORMALIZED,
                    field="topic",
                    message=(
                        f"Topic normalized: {raw_topic!r} → {topic_res.canonical!r}."
                    ),
                )
            )

    # --- Proposition ---
    raw_proposition: str = raw.get("normalized_proposition", "") or ""
    prop_res = normalize_proposition(raw_proposition)
    if prop_res.was_normalized:
        warnings.append(
            ValidationWarning(
                code=WarningCode.WARN_PROPOSITION_NORMALIZED,
                field="normalized_proposition",
                message=(
                    f"Proposition normalized: {raw_proposition!r} → "
                    f"{prop_res.canonical!r}."
                ),
            )
        )

    # --- Confidence ---
    raw_confidence: Any = raw.get("confidence", 0.0)
    confidence = _normalize_confidence(raw_confidence, warnings)

    # --- Date ---
    raw_date: str | None = raw.get("event_date")
    raw_precision: str | None = raw.get("event_date_precision")
    event_date, event_date_precision = _normalize_date(
        raw_date, raw_precision, warnings
    )

    # --- Optional string fields ---
    subtopic = _normalize_optional_str(raw.get("subtopic"))
    speaker = _normalize_optional_str(raw.get("speaker"))
    target_entity = _normalize_optional_str(raw.get("target_entity"))
    quote_text = _normalize_optional_str(raw.get("quote_text"))
    paraphrase = _normalize_optional_str(raw.get("paraphrase"))
    notes = _normalize_optional_str(raw.get("notes"))

    # --- Quote spans ---
    quote_start_char: int | None = _normalize_optional_int(raw.get("quote_start_char"))
    quote_end_char: int | None = _normalize_optional_int(raw.get("quote_end_char"))

    # --- Determine final status ---
    final_status = (
        ValidationStatus.VALID_WITH_WARNINGS
        if warnings
        else ValidationStatus.VALID
    )

    return NormalizedStanceEvent(
        doc_id=doc_id,
        index=event_result.index,
        # Normalized required fields
        politician=politician_res.canonical,
        topic=topic_res.canonical,
        normalized_proposition=prop_res.canonical,
        stance_direction=raw.get("stance_direction", ""),
        stance_mode=raw.get("stance_mode", ""),
        evidence_role=raw.get("evidence_role", ""),
        confidence=confidence,
        # Normalized optional fields
        subtopic=subtopic,
        speaker=speaker,
        target_entity=target_entity,
        event_date=event_date,
        event_date_precision=event_date_precision,
        quote_text=quote_text,
        quote_start_char=quote_start_char,
        quote_end_char=quote_end_char,
        paraphrase=paraphrase,
        notes=notes,
        # Raw / provenance fields
        raw_politician=raw_politician if politician_res.was_normalized else None,
        raw_topic=raw_topic if topic_res.was_normalized else None,
        raw_proposition=raw_proposition if prop_res.was_normalized else None,
        raw_event_date=raw_date if (event_date != raw_date) else None,
        validation_status=final_status,
        validation_warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _normalize_confidence(
    raw: Any,
    warnings: list[ValidationWarning],
) -> float:
    """Return a confidence value clamped to [0.0, 1.0].

    If *raw* cannot be coerced to float, returns 0.0 and emits a warning.
    """
    try:
        value = float(raw)
    except (TypeError, ValueError):
        warnings.append(
            ValidationWarning(
                code=WarningCode.WARN_CONFIDENCE_CLAMPED,
                field="confidence",
                message=(
                    f"'confidence' value {raw!r} could not be coerced to float; "
                    "defaulting to 0.0."
                ),
            )
        )
        return 0.0

    if value < 0.0 or value > 1.0:
        clamped = max(0.0, min(1.0, value))
        warnings.append(
            ValidationWarning(
                code=WarningCode.WARN_CONFIDENCE_CLAMPED,
                field="confidence",
                message=(
                    f"'confidence' {value} is outside [0.0, 1.0]; "
                    f"clamped to {clamped}."
                ),
            )
        )
        return clamped
    return value


def _normalize_date(
    raw_date: str | None,
    raw_precision: str | None,
    warnings: list[ValidationWarning],
) -> tuple[str | None, str | None]:
    """Parse and standardize the event date.

    Returns
    -------
    tuple[str | None, str | None]
        ``(canonical_date, canonical_precision)``
    """
    if raw_date is None:
        return None, raw_precision

    parsed = parse_date(raw_date)
    if not parsed.ok:
        # Already flagged as an error by the validator; just return None
        return None, raw_precision

    canonical_date = parsed.canonical
    # If precision was missing, infer from parsed result
    canonical_precision = raw_precision if raw_precision is not None else parsed.precision

    if raw_date != canonical_date:
        warnings.append(
            ValidationWarning(
                code=WarningCode.WARN_DATE_NORMALIZED,
                field="event_date",
                message=(
                    f"Date normalized: {raw_date!r} → {canonical_date!r}."
                ),
            )
        )

    return canonical_date, canonical_precision


def _normalize_optional_str(value: Any) -> str | None:
    """Return stripped string or ``None``."""
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else None
    return None


def _normalize_optional_int(value: Any) -> int | None:
    """Return integer or ``None``."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    return None
