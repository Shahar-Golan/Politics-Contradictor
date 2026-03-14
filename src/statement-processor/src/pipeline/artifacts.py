"""
pipeline.artifacts
==================
Local artifact management for the bulk Option-A pipeline.

Each pipeline run writes its artifacts to a structured directory so that the
job is auditable and resumable:

    data/batch_artifacts/
        triage/
            <run_id>/
                selected_articles.jsonl    # articles after deterministic filter
                batch_input.jsonl          # triage batch API input
                batch_output.jsonl         # triage batch API output (user-placed)
                triage_results.jsonl       # parsed triage decisions
                positives.jsonl            # doc_ids that advance to extraction
                negatives.jsonl            # doc_ids that did not advance
                failures.jsonl             # request-level failures
                parse_errors.jsonl         # parse-error records
                summary.json               # stage summary counts
        extraction/
            <run_id>/
                articles_for_extraction.jsonl  # triage-positive articles
                batch_input.jsonl              # extraction batch API input
                batch_output.jsonl             # extraction batch API output (user-placed)
                raw_outputs.jsonl              # raw model outputs
                candidate_events.jsonl         # parsed candidate events (untrusted)
                failures.jsonl                 # request-level failures
                parse_errors.jsonl             # parse-error doc_ids
                summary.json                   # stage summary counts

Usage
-----
    from pipeline.artifacts import resolve_run_dir, write_jsonl_artifact, write_summary

    run_dir = resolve_run_dir("data/batch_artifacts/triage", run_id="run-001")
    write_jsonl_artifact(records, run_dir / "selected_articles.jsonl")
    write_summary({"total": 100}, run_dir / "summary.json")
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Run directory helpers
# ---------------------------------------------------------------------------


def resolve_run_dir(
    base_dir: Path | str,
    run_id: str | None = None,
) -> Path:
    """Resolve (and create) a run-specific artifact directory.

    Parameters
    ----------
    base_dir:
        Root artifact directory (e.g. ``data/batch_artifacts/triage``).
    run_id:
        Optional run identifier.  If ``None``, a timestamp-based ID is
        generated (``run-YYYYMMDD-HHMMSS``).

    Returns
    -------
    Path
        Absolute path to the run directory, created if it does not exist.
    """
    if run_id is None:
        run_id = datetime.now(timezone.utc).strftime("run-%Y%m%d-%H%M%S")
    run_dir = Path(base_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir.resolve()


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _serialise(obj: Any) -> Any:
    """Recursively convert dataclasses and known non-JSON-native types.

    Parameters
    ----------
    obj:
        Any Python object to serialise.

    Returns
    -------
    Any
        A JSON-serialisable representation.
    """
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: _serialise(v) for k, v in asdict(obj).items()}
    if isinstance(obj, (list, tuple)):
        return [_serialise(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _serialise(v) for k, v in obj.items()}
    if isinstance(obj, Path):
        return str(obj)
    return obj


# ---------------------------------------------------------------------------
# Public artifact writers
# ---------------------------------------------------------------------------


def write_artifact(
    data: Any,
    path: Path | str,
) -> Path:
    """Write a single JSON artifact to *path*.

    Parameters
    ----------
    data:
        Any JSON-serialisable object (dicts, lists, dataclasses).
    path:
        Destination file path.  Parent directories are created if needed.

    Returns
    -------
    Path
        Absolute resolved path to the written file.
    """
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8") as fh:
        json.dump(_serialise(data), fh, indent=2, ensure_ascii=False)
    return dest.resolve()


def write_jsonl_artifact(
    records: list[Any],
    path: Path | str,
) -> Path:
    """Write a list of records as JSONL to *path*.

    Each record is serialised to a single line.  Dataclasses are converted
    via ``dataclasses.asdict``.

    Parameters
    ----------
    records:
        List of JSON-serialisable objects.
    path:
        Destination file path.

    Returns
    -------
    Path
        Absolute resolved path to the written file.
    """
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(_serialise(record), ensure_ascii=False) + "\n")
    return dest.resolve()


def write_summary(
    summary: dict[str, Any],
    path: Path | str,
) -> Path:
    """Write a stage summary dict to *path* as pretty-printed JSON.

    Parameters
    ----------
    summary:
        Dict of summary counts and metadata.
    path:
        Destination file path.

    Returns
    -------
    Path
        Absolute resolved path to the written file.
    """
    return write_artifact(summary, path)
