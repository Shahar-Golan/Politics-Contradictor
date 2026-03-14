"""
triage
======
First-pass cheap LLM triage classifier for the bulk Option-A pipeline.

The triage stage sits between deterministic pre-filtering (selection) and
expensive full stance extraction.  It answers a small set of structured
questions to decide whether an article is worth sending to the full
extractor.

Public API
----------
- :class:`~triage.models.TriageArticle`
- :class:`~triage.models.TriageDecision`
- :class:`~triage.models.TriageResult`
- :class:`~triage.models.TriageBatchIngestionResult`
- :class:`~triage.models.TriageConfig`
- :func:`~triage.batch_requests.build_triage_batch_requests`
- :func:`~triage.batch_requests.write_triage_batch_jsonl`
- :func:`~triage.batch_ingest.ingest_triage_batch_output`
"""

from __future__ import annotations

from .batch_ingest import ingest_triage_batch_output
from .batch_requests import build_triage_batch_requests, write_triage_batch_jsonl
from .models import (
    TriageArticle,
    TriageBatchIngestionResult,
    TriageConfig,
    TriageDecision,
    TriageResult,
)

__all__ = [
    "TriageArticle",
    "TriageBatchIngestionResult",
    "TriageConfig",
    "TriageDecision",
    "TriageResult",
    "build_triage_batch_requests",
    "ingest_triage_batch_output",
    "write_triage_batch_jsonl",
]
