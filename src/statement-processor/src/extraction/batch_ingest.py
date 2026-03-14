"""
extraction.batch_ingest
=======================
Ingest completed OpenAI Batch API output files for the full extraction stage.

The Batch API writes a JSONL file where each line is the response to one
request.  Each line has the following structure::

    {
      "id": "<batch-request-id>",
      "custom_id": "extraction-<doc_id>-chunk<idx>of<total>",
      "response": {
        "status_code": 200,
        "body": {
          "choices": [{"message": {"content": "<extraction JSON>"}}]
        }
      },
      "error": null
    }

Important design constraint
----------------------------
This module stores extraction outputs as **raw candidate results**.  It does
**not** validate, normalise, or persist them as final stance events.  All
outputs are treated as untrusted until a later validation layer approves them.
This mirrors the behaviour of the synchronous extractor.

This module:
1. Reads the JSONL output file.
2. Maps each response back to the originating article via ``custom_id``.
3. Parses raw JSON from the model content (re-using
   :func:`~extraction.extractor._parse_raw_response`).
4. Builds :class:`~extraction.models.RawExtractionOutput` records.
5. Returns an :class:`ExtractionBatchIngestionResult`.

Usage
-----
    from extraction.batch_ingest import ingest_extraction_batch_output
    from pathlib import Path

    result = ingest_extraction_batch_output(
        output_jsonl=Path("data/batch_artifacts/extraction/run-001/batch_output.jsonl"),
        input_jsonl=Path("data/batch_artifacts/extraction/run-001/batch_input.jsonl"),
    )

    print(result.summary())
    for raw in result.raw_outputs:
        print(raw.doc_id, raw.parse_error)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .extractor import _parse_raw_response
from .models import CandidateStanceEvent, RawExtractionOutput

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CUSTOM_ID_PREFIX: str = "extraction-"

# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------


@dataclass
class ExtractionBatchIngestionResult:
    """Aggregated result of ingesting one completed extraction batch output file.

    All outputs are treated as **raw/intermediate candidates** – they have not
    been validated or normalised.

    Attributes
    ----------
    raw_outputs:
        One :class:`~extraction.models.RawExtractionOutput` per chunk
        response, regardless of parse success.
    candidate_events:
        Parsed :class:`~extraction.models.CandidateStanceEvent` objects
        from all successfully parsed responses.  Untrusted – for downstream
        validation only.
    failed_requests:
        ``custom_id`` values for requests that failed at the provider level.
    parse_error_ids:
        ``doc_id`` values for articles where the response was received but
        could not be parsed.
    """

    raw_outputs: list[RawExtractionOutput] = field(default_factory=list)
    candidate_events: list[CandidateStanceEvent] = field(default_factory=list)
    failed_requests: list[str] = field(default_factory=list)
    parse_error_ids: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        """Return a summary dict suitable for JSON serialisation."""
        return {
            "total_responses": len(self.raw_outputs),
            "candidate_events": len(self.candidate_events),
            "failed_requests": len(self.failed_requests),
            "parse_errors": len(self.parse_error_ids),
            "retry_candidates": len(self.failed_requests) + len(self.parse_error_ids),
        }


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_custom_id(custom_id: str) -> tuple[str, int, int]:
    """Decode the doc_id, chunk_index, and chunk_total from a ``custom_id``.

    Expected format: ``extraction-<doc_id>-chunk<idx>of<total>``

    Parameters
    ----------
    custom_id:
        The ``custom_id`` field from the Batch API response line.

    Returns
    -------
    tuple[str, int, int]
        ``(doc_id, chunk_index, chunk_total)``

    Raises
    ------
    ValueError
        If the format is unrecognised.
    """
    if not custom_id.startswith(_CUSTOM_ID_PREFIX):
        raise ValueError(f"custom_id does not start with {_CUSTOM_ID_PREFIX!r}: {custom_id!r}")

    rest = custom_id[len(_CUSTOM_ID_PREFIX):]  # e.g. "art-001-chunk0of1"

    # Find the last "-chunk" separator.
    marker = "-chunk"
    idx = rest.rfind(marker)
    if idx == -1:
        raise ValueError(f"custom_id missing '-chunk' marker: {custom_id!r}")

    doc_id = rest[:idx]
    chunk_part = rest[idx + len(marker):]  # e.g. "0of1"

    if "of" not in chunk_part:
        raise ValueError(f"custom_id chunk part malformed (no 'of'): {custom_id!r}")

    chunk_idx_str, chunk_total_str = chunk_part.split("of", 1)
    try:
        chunk_index = int(chunk_idx_str)
        chunk_total = int(chunk_total_str)
    except ValueError as exc:
        raise ValueError(f"custom_id chunk numbers not int: {custom_id!r}") from exc

    return doc_id, chunk_index, chunk_total


def _build_candidate_events(
    parsed_json: dict[str, Any],
    doc_id: str,
    chunk_index: int,
    chunk_total: int,
) -> list[CandidateStanceEvent]:
    """Build :class:`CandidateStanceEvent` objects from a parsed extraction JSON.

    This mirrors :func:`~extraction.extractor._build_candidate` but operates
    on the already-parsed dict from batch ingestion.

    Parameters
    ----------
    parsed_json:
        The already-parsed LLM JSON object.
    doc_id:
        Source article identifier.
    chunk_index:
        Chunk index for provenance.
    chunk_total:
        Total chunks for provenance.

    Returns
    -------
    list[CandidateStanceEvent]
        Zero or more untrusted candidate events.
    """
    events: list[CandidateStanceEvent] = []
    stance_events = parsed_json.get("stance_events", [])
    if not isinstance(stance_events, list):
        return events

    for event in stance_events:
        if not isinstance(event, dict):
            continue
        # Required fields
        politician = event.get("politician")
        topic = event.get("topic")
        norm_prop = event.get("normalized_proposition")
        direction = event.get("stance_direction")
        mode = event.get("stance_mode")
        evidence = event.get("evidence_role")
        confidence_raw = event.get("confidence", 0.0)

        if not all([politician, topic, norm_prop, direction, mode, evidence]):
            logger.debug("Skipping event with missing required fields: %s", event)
            continue

        try:
            confidence = float(confidence_raw)
        except (TypeError, ValueError):
            confidence = 0.0

        events.append(
            CandidateStanceEvent(
                doc_id=doc_id,
                politician=str(politician),
                topic=str(topic),
                normalized_proposition=str(norm_prop),
                stance_direction=str(direction),
                stance_mode=str(mode),
                evidence_role=str(evidence),
                confidence=confidence,
                subtopic=event.get("subtopic"),
                speaker=event.get("speaker"),
                target_entity=event.get("target_entity"),
                event_date=event.get("event_date"),
                event_date_precision=event.get("event_date_precision"),
                quote_text=event.get("quote_text"),
                quote_start_char=event.get("quote_start_char"),
                quote_end_char=event.get("quote_end_char"),
                paraphrase=event.get("paraphrase"),
                notes=event.get("notes"),
                chunk_index=chunk_index,
                chunk_total=chunk_total,
            )
        )
    return events


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def ingest_extraction_batch_output(
    output_jsonl: Path | str,
    input_jsonl: Path | str | None = None,
    model_name: str = "unknown",
) -> ExtractionBatchIngestionResult:
    """Ingest a completed extraction Batch API output file.

    All parsed events are stored as **raw/intermediate candidates**.  They
    are not validated, normalised, or persisted.

    Parameters
    ----------
    output_jsonl:
        Path to the completed Batch API output JSONL file.
    input_jsonl:
        Path to the matching batch input JSONL file.  Currently unused but
        reserved for future provenance enrichment.
    model_name:
        Model name to record in :class:`~extraction.models.RawExtractionOutput`
        objects.  Defaults to ``"unknown"`` if not provided.

    Returns
    -------
    ExtractionBatchIngestionResult
        Raw outputs, candidate events, failed requests, and parse errors.

    Raises
    ------
    FileNotFoundError
        If *output_jsonl* does not exist.
    """
    out_path = Path(output_jsonl)
    if not out_path.exists():
        raise FileNotFoundError(f"Extraction batch output not found: {out_path}")

    now = datetime.now(timezone.utc).isoformat()
    result = ExtractionBatchIngestionResult()

    with out_path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue

            try:
                entry: dict[str, Any] = json.loads(line)
            except json.JSONDecodeError as exc:
                logger.error("Skipping malformed line %d in %s: %s", lineno, out_path, exc)
                continue

            custom_id: str = entry.get("custom_id", "")

            # Parse doc_id and chunk info from custom_id.
            try:
                doc_id, chunk_index, chunk_total = _parse_custom_id(custom_id)
            except ValueError as exc:
                logger.warning("Cannot parse custom_id %r: %s", custom_id, exc)
                doc_id, chunk_index, chunk_total = custom_id, 0, 1

            # Handle provider-level request failure.
            error_field: Optional[dict[str, Any]] = entry.get("error")
            if error_field:
                logger.warning("Batch request failed for %r: %s", doc_id, error_field)
                result.failed_requests.append(custom_id)
                result.raw_outputs.append(
                    RawExtractionOutput(
                        doc_id=doc_id,
                        chunk_index=chunk_index,
                        chunk_total=chunk_total,
                        model_name=model_name,
                        raw_response="",
                        parsed_json=None,
                        parse_error=str(error_field),
                        extraction_timestamp=now,
                    )
                )
                continue

            # Extract raw content.
            response: dict[str, Any] = entry.get("response", {})
            status_code: int = response.get("status_code", 0)
            body: dict[str, Any] = response.get("body", {})

            if status_code != 200:
                logger.warning("Non-200 status %d for %r.", status_code, doc_id)
                result.failed_requests.append(custom_id)
                result.raw_outputs.append(
                    RawExtractionOutput(
                        doc_id=doc_id,
                        chunk_index=chunk_index,
                        chunk_total=chunk_total,
                        model_name=model_name,
                        raw_response="",
                        parsed_json=None,
                        parse_error=f"HTTP status {status_code}",
                        extraction_timestamp=now,
                    )
                )
                continue

            choices: list[dict[str, Any]] = body.get("choices", [])
            raw_content: str = ""
            if choices:
                raw_content = choices[0].get("message", {}).get("content", "") or ""

            # Try to infer model name from response metadata.
            response_model: str = body.get("model", model_name)

            # Parse the raw extraction response.
            parsed_json, parse_error = _parse_raw_response(raw_content, doc_id)

            raw_out = RawExtractionOutput(
                doc_id=doc_id,
                chunk_index=chunk_index,
                chunk_total=chunk_total,
                model_name=response_model,
                raw_response=raw_content,
                parsed_json=parsed_json,
                parse_error=parse_error,
                extraction_timestamp=now,
            )
            result.raw_outputs.append(raw_out)

            if parse_error:
                logger.warning("Parse error for %r chunk %d: %s", doc_id, chunk_index, parse_error)
                result.parse_error_ids.append(doc_id)
                continue

            if parsed_json is not None:
                candidates = _build_candidate_events(
                    parsed_json, doc_id, chunk_index, chunk_total
                )
                result.candidate_events.extend(candidates)

    logger.info("Extraction ingestion complete: %s", result.summary())
    return result
