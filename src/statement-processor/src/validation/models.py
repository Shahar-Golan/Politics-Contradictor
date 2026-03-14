"""
validation.models
=================
Typed data models for validation and normalization results.

These models represent the output of the deterministic validation layer.
They are separate from the extractor's ``CandidateStanceEvent`` models and are
designed to be safe for downstream persistence.

Design notes
------------
* ``ValidationStatus`` uses an Enum for unambiguous status comparison.
* ``EventValidationResult`` wraps a single event's outcome (accepted/rejected).
* ``DocumentValidationResult`` aggregates all per-event outcomes for an article.
* ``NormalizedStanceEvent`` is the final, clean output ready for persistence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from validation.errors import ValidationError, ValidationWarning


# ---------------------------------------------------------------------------
# Validation status
# ---------------------------------------------------------------------------


class ValidationStatus(str, Enum):
    """Overall validation outcome for a stance event or document.

    Attributes
    ----------
    VALID
        All required fields are present, all values conform to the contract,
        and no warnings were raised.
    VALID_WITH_WARNINGS
        The event is accepted, but one or more non-critical normalizations or
        ambiguities were noted.  Downstream code should inspect ``warnings``.
    REJECTED
        The event has one or more hard errors and must not be persisted.
    """

    VALID = "valid"
    VALID_WITH_WARNINGS = "valid_with_warnings"
    REJECTED = "rejected"


# ---------------------------------------------------------------------------
# Per-event validation result
# ---------------------------------------------------------------------------


@dataclass
class EventValidationResult:
    """Outcome of validating a single stance event candidate.

    Attributes
    ----------
    index:
        0-based position of this event within the document's ``stance_events``
        array.  Useful for tracing errors back to the raw input.
    raw_event:
        The original (untrusted) event dict exactly as received.
    status:
        Validation outcome (VALID, VALID_WITH_WARNINGS, or REJECTED).
    errors:
        List of hard validation errors.  Non-empty iff ``status == REJECTED``.
    warnings:
        List of non-fatal warnings / normalization notes.
    """

    index: int
    raw_event: dict[str, Any]
    status: ValidationStatus
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationWarning] = field(default_factory=list)

    @property
    def is_accepted(self) -> bool:
        """``True`` iff the event was accepted (valid or valid-with-warnings)."""
        return self.status != ValidationStatus.REJECTED


# ---------------------------------------------------------------------------
# Document-level validation result
# ---------------------------------------------------------------------------


@dataclass
class DocumentValidationResult:
    """Aggregated validation result for a complete extractor document.

    Attributes
    ----------
    doc_id:
        The document identifier from the raw input.  May be ``None`` if the
        input was missing ``doc_id``.
    status:
        Overall document status:
        - VALID: all events accepted, no warnings.
        - VALID_WITH_WARNINGS: accepted with warnings (or zero events).
        - REJECTED: entire document rejected (bad top-level shape).
    document_errors:
        Hard errors at the document level (e.g. missing ``doc_id``).
    document_warnings:
        Warnings at the document level.
    event_results:
        Per-event validation outcomes.
    raw_input:
        The original (untrusted) parsed JSON as a dict.
    """

    doc_id: str | None
    status: ValidationStatus
    document_errors: list[ValidationError] = field(default_factory=list)
    document_warnings: list[ValidationWarning] = field(default_factory=list)
    event_results: list[EventValidationResult] = field(default_factory=list)
    raw_input: dict[str, Any] | None = None

    @property
    def accepted_events(self) -> list[EventValidationResult]:
        """Event results with VALID or VALID_WITH_WARNINGS status."""
        return [r for r in self.event_results if r.is_accepted]

    @property
    def rejected_events(self) -> list[EventValidationResult]:
        """Event results with REJECTED status."""
        return [r for r in self.event_results if not r.is_accepted]

    @property
    def accepted_count(self) -> int:
        """Number of accepted events."""
        return len(self.accepted_events)

    @property
    def rejected_count(self) -> int:
        """Number of rejected events."""
        return len(self.rejected_events)

    @property
    def total_count(self) -> int:
        """Total number of events (accepted + rejected)."""
        return len(self.event_results)


# ---------------------------------------------------------------------------
# Normalized stance event (final clean output)
# ---------------------------------------------------------------------------


@dataclass
class NormalizedStanceEvent:
    """A fully validated and normalized stance event ready for persistence.

    All fields in this model have already been:
    - validated against the contract,
    - normalized to canonical forms,
    - de-aliased (politician names, topics, etc.).

    Original raw values are preserved alongside normalized values so that
    auditors can trace any transformation.

    Attributes
    ----------
    doc_id:
        Source article identifier.
    index:
        0-based position within the source document's ``stance_events`` array.

    Normalized required fields
    --------------------------
    politician:
        Canonical politician name (e.g. ``"Donald Trump"``).
    topic:
        Canonical topic from controlled vocabulary.
    normalized_proposition:
        Canonicalized proposition string.
    stance_direction:
        Canonical stance direction.
    stance_mode:
        Canonical stance mode.
    evidence_role:
        Canonical evidence role.
    confidence:
        Normalized confidence value in [0.0, 1.0].

    Normalized optional fields
    --------------------------
    subtopic:
        Optional subtopic string (normalized whitespace).
    speaker:
        Speaker name (normalized whitespace).
    target_entity:
        Target entity (normalized whitespace).
    event_date:
        Standardized date string (ISO-8601 compatible: YYYY-MM-DD, YYYY-MM,
        or YYYY) or ``None``.
    event_date_precision:
        Canonical date precision value, or ``None``.
    quote_text:
        Verbatim quote text (whitespace-normalized), or ``None``.
    quote_start_char:
        Quote start character offset, or ``None``.
    quote_end_char:
        Quote end character offset, or ``None``.
    paraphrase:
        Paraphrase text (whitespace-normalized), or ``None``.
    notes:
        Notes (whitespace-normalized), or ``None``.

    Raw / provenance fields
    -----------------------
    raw_politician:
        Politician name exactly as received from the extractor.
    raw_topic:
        Topic value exactly as received.
    raw_proposition:
        Proposition exactly as received.
    raw_event_date:
        Date value exactly as received (before parsing/normalization).
    validation_status:
        Per-event validation status.
    validation_warnings:
        Warnings raised during validation/normalization.
    """

    # Provenance
    doc_id: str
    index: int

    # Normalized required fields
    politician: str
    topic: str
    normalized_proposition: str
    stance_direction: str
    stance_mode: str
    evidence_role: str
    confidence: float

    # Normalized optional fields
    subtopic: str | None = None
    speaker: str | None = None
    target_entity: str | None = None
    event_date: str | None = None
    event_date_precision: str | None = None
    quote_text: str | None = None
    quote_start_char: int | None = None
    quote_end_char: int | None = None
    paraphrase: str | None = None
    notes: str | None = None

    # Raw / provenance fields
    raw_politician: str | None = None
    raw_topic: str | None = None
    raw_proposition: str | None = None
    raw_event_date: str | None = None
    validation_status: ValidationStatus = ValidationStatus.VALID
    validation_warnings: list[ValidationWarning] = field(default_factory=list)
