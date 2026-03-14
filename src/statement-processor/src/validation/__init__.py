"""
validation
==========
Deterministic validation and normalization layer for raw extractor outputs.

This package converts untrusted LLM extraction results (``CandidateStanceEvent``
objects) into clean, standardized, validated outputs ready for safe downstream
persistence.

Sub-modules
-----------
models
    Typed result models for validation and normalization outcomes.
errors
    Error/warning codes and typed error objects.
validator
    Deterministic structural and semantic validator.
normalizer
    Normalization orchestrator — delegates to specialist sub-modules.
date_parser
    Date parsing and precision standardization.
politician_normalization
    Canonical politician name resolution from aliases.
topic_normalization
    Surface-form topic mapping to controlled vocabulary.
proposition_normalization
    Deterministic lexical proposition normalization.

Typical usage
-------------
    from validation.validator import validate_document
    from validation.normalizer import normalize_document

    result = validate_document(raw_json)
    normalized = normalize_document(result)
"""

from __future__ import annotations

from validation.validator import validate_document, validate_candidate
from validation.normalizer import normalize_document, normalize_candidate
from validation.models import (
    DocumentValidationResult,
    EventValidationResult,
    ValidationStatus,
    NormalizedStanceEvent,
)

__all__ = [
    "validate_document",
    "validate_candidate",
    "normalize_document",
    "normalize_candidate",
    "DocumentValidationResult",
    "EventValidationResult",
    "ValidationStatus",
    "NormalizedStanceEvent",
]
