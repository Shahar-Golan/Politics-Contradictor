"""
contracts
=========
Extraction contract definitions for the stance extractor.

Exports the controlled vocabularies and schema path so that downstream
extractor, validator, and test code share a single authoritative source.
"""

from .vocab import (
    TOPIC_VALUES,
    STANCE_DIRECTION_VALUES,
    STANCE_MODE_VALUES,
    EVIDENCE_ROLE_VALUES,
    EVENT_DATE_PRECISION_VALUES,
    ALL_VOCABULARIES,
)

__all__ = [
    "TOPIC_VALUES",
    "STANCE_DIRECTION_VALUES",
    "STANCE_MODE_VALUES",
    "EVIDENCE_ROLE_VALUES",
    "EVENT_DATE_PRECISION_VALUES",
    "ALL_VOCABULARIES",
]
