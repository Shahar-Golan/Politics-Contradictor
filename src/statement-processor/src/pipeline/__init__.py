"""
pipeline
========
Pipeline orchestration and artifact management for the bulk Option-A
processing workflow.

The pipeline executes the following stages:

1. Deterministic pre-filtering (:mod:`selection`)
2. Triage batch preparation (:mod:`triage.batch_requests`)
3. Triage batch ingestion (:mod:`triage.batch_ingest`)
4. Extraction batch preparation (:mod:`extraction.batch_requests`)
5. Extraction batch ingestion (:mod:`extraction.batch_ingest`)

Artifacts from each stage are written to a structured local directory so
that the pipeline is auditable and resumable.

Public API
----------
- :func:`~pipeline.artifacts.resolve_run_dir`
- :func:`~pipeline.artifacts.write_artifact`
- :func:`~pipeline.artifacts.write_jsonl_artifact`
- :func:`~pipeline.artifacts.write_summary`
- :class:`~pipeline.bulk_option_a.BulkPipelineConfig`
- :func:`~pipeline.bulk_option_a.run_select`
- :func:`~pipeline.bulk_option_a.run_prepare_triage`
- :func:`~pipeline.bulk_option_a.run_ingest_triage`
- :func:`~pipeline.bulk_option_a.run_prepare_extraction`
- :func:`~pipeline.bulk_option_a.run_ingest_extraction`
"""

from __future__ import annotations

from .artifacts import resolve_run_dir, write_artifact, write_jsonl_artifact, write_summary
from .bulk_option_a import (
    BulkPipelineConfig,
    run_ingest_extraction,
    run_ingest_triage,
    run_prepare_extraction,
    run_prepare_triage,
    run_select,
)

__all__ = [
    "BulkPipelineConfig",
    "resolve_run_dir",
    "run_ingest_extraction",
    "run_ingest_triage",
    "run_prepare_extraction",
    "run_prepare_triage",
    "run_select",
    "write_artifact",
    "write_jsonl_artifact",
    "write_summary",
]
