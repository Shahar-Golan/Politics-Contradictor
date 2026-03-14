"""
validation.errors
=================
Error and warning codes, typed error objects, and rejection reasons for the
deterministic validation layer.

Design notes
------------
* Error codes use a ``SCREAMING_SNAKE_CASE`` prefix that groups related codes:
  ``SHAPE_*`` for structural issues, ``FIELD_*`` for per-field issues,
  ``EVIDENCE_*`` for evidence-related issues, and ``ATOMICITY_*`` for
  merged-proposition violations.
* Warnings follow the same pattern with a ``WARN_*`` prefix.
* All objects are frozen dataclasses so they can be safely hashed/compared.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


# ---------------------------------------------------------------------------
# Error codes
# ---------------------------------------------------------------------------


class ErrorCode(str, Enum):
    """Canonical error codes produced by the validator."""

    # Top-level / document shape
    SHAPE_MISSING_DOC_ID = "SHAPE_MISSING_DOC_ID"
    SHAPE_EMPTY_DOC_ID = "SHAPE_EMPTY_DOC_ID"
    SHAPE_MISSING_STANCE_EVENTS = "SHAPE_MISSING_STANCE_EVENTS"
    SHAPE_STANCE_EVENTS_NOT_LIST = "SHAPE_STANCE_EVENTS_NOT_LIST"
    SHAPE_EVENT_NOT_OBJECT = "SHAPE_EVENT_NOT_OBJECT"

    # Required field presence
    FIELD_MISSING_REQUIRED = "FIELD_MISSING_REQUIRED"

    # Type errors
    FIELD_WRONG_TYPE = "FIELD_WRONG_TYPE"

    # Controlled vocabulary violations
    FIELD_INVALID_TOPIC = "FIELD_INVALID_TOPIC"
    FIELD_INVALID_STANCE_DIRECTION = "FIELD_INVALID_STANCE_DIRECTION"
    FIELD_INVALID_STANCE_MODE = "FIELD_INVALID_STANCE_MODE"
    FIELD_INVALID_EVIDENCE_ROLE = "FIELD_INVALID_EVIDENCE_ROLE"
    FIELD_INVALID_DATE_PRECISION = "FIELD_INVALID_DATE_PRECISION"

    # Confidence range
    FIELD_CONFIDENCE_OUT_OF_RANGE = "FIELD_CONFIDENCE_OUT_OF_RANGE"
    FIELD_CONFIDENCE_NOT_NUMBER = "FIELD_CONFIDENCE_NOT_NUMBER"

    # Date issues
    FIELD_UNPARSEABLE_DATE = "FIELD_UNPARSEABLE_DATE"
    FIELD_DATE_PRECISION_MISMATCH = "FIELD_DATE_PRECISION_MISMATCH"

    # Evidence issues
    EVIDENCE_MISSING_QUOTE = "EVIDENCE_MISSING_QUOTE"
    EVIDENCE_EMPTY_QUOTE = "EVIDENCE_EMPTY_QUOTE"
    EVIDENCE_IMPLAUSIBLE_SPAN = "EVIDENCE_IMPLAUSIBLE_SPAN"
    EVIDENCE_SPAN_WITHOUT_TEXT = "EVIDENCE_SPAN_WITHOUT_TEXT"
    EVIDENCE_MISSING_PARAPHRASE = "EVIDENCE_MISSING_PARAPHRASE"

    # Atomicity
    ATOMICITY_MERGED_PROPOSITION = "ATOMICITY_MERGED_PROPOSITION"

    # Politician
    FIELD_EMPTY_POLITICIAN = "FIELD_EMPTY_POLITICIAN"
    FIELD_AMBIGUOUS_POLITICIAN = "FIELD_AMBIGUOUS_POLITICIAN"

    # Proposition
    FIELD_EMPTY_PROPOSITION = "FIELD_EMPTY_PROPOSITION"


# ---------------------------------------------------------------------------
# Warning codes
# ---------------------------------------------------------------------------


class WarningCode(str, Enum):
    """Canonical warning codes produced by the validator (non-fatal)."""

    # Normalization warnings
    WARN_POLITICIAN_NORMALIZED = "WARN_POLITICIAN_NORMALIZED"
    WARN_TOPIC_NORMALIZED = "WARN_TOPIC_NORMALIZED"
    WARN_PROPOSITION_NORMALIZED = "WARN_PROPOSITION_NORMALIZED"
    WARN_DATE_NORMALIZED = "WARN_DATE_NORMALIZED"
    WARN_CONFIDENCE_CLAMPED = "WARN_CONFIDENCE_CLAMPED"
    WARN_UNKNOWN_POLITICIAN = "WARN_UNKNOWN_POLITICIAN"
    WARN_TOPIC_MAPPED_TO_OTHER = "WARN_TOPIC_MAPPED_TO_OTHER"
    WARN_DATE_PRECISION_INFERRED = "WARN_DATE_PRECISION_INFERRED"
    WARN_MISSING_EVIDENCE_PARAPHRASE = "WARN_MISSING_EVIDENCE_PARAPHRASE"
    WARN_ATOMICITY_POSSIBLE_MERGE = "WARN_ATOMICITY_POSSIBLE_MERGE"


# ---------------------------------------------------------------------------
# Typed error / warning objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationError:
    """A single validation error attached to a stance event.

    Attributes
    ----------
    code:
        Machine-readable error code.
    field:
        The field name that caused the error, or ``None`` for document-level
        errors.
    message:
        Human-readable explanation.
    """

    code: ErrorCode
    message: str
    field: str | None = None


@dataclass(frozen=True)
class ValidationWarning:
    """A single non-fatal validation warning attached to a stance event.

    Attributes
    ----------
    code:
        Machine-readable warning code.
    field:
        The field name that triggered the warning, or ``None`` for
        document-level warnings.
    message:
        Human-readable explanation.
    """

    code: WarningCode
    message: str
    field: str | None = None
