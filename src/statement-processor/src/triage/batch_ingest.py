"""
triage.batch_ingest
===================
Ingest completed OpenAI Batch API output files for the triage stage.

The Batch API writes a JSONL file where each line is the response to one
request.  Each line has the following structure::

    {
      "id": "<batch-request-id>",
      "custom_id": "triage-<doc_id>",
      "response": {
        "status_code": 200,
        "body": {
          "choices": [{"message": {"content": "<JSON triage decision>"}}]
        }
      },
      "error": null
    }

This module:
1. Reads the JSONL output file.
2. Maps each response back to the originating article via ``custom_id``.
3. Parses the structured triage decision from the model's content.
4. Classifies each result as positive, negative, failed, or parse-error.
5. Returns a :class:`~triage.models.TriageBatchIngestionResult`.

The provenance mapping uses a ``request_index`` dict built from the original
batch input file (``batch_input.jsonl``) so that every response can be linked
back to the article it came from.

Usage
-----
    from triage.batch_ingest import ingest_triage_batch_output
    from pathlib import Path

    result = ingest_triage_batch_output(
        output_jsonl=Path("data/batch_artifacts/triage/run-001/batch_output.jsonl"),
        input_jsonl=Path("data/batch_artifacts/triage/run-001/batch_input.jsonl"),
    )

    print(result.summary())
    for pos in result.positives:
        print(pos.doc_id, pos.decision.rationale)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from .models import (
    TriageBatchIngestionResult,
    TriageDecision,
    TriageResult,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CUSTOM_ID_PREFIX: str = "triage-"

# Required boolean keys in the triage decision JSON.
_REQUIRED_BOOL_KEYS: frozenset[str] = frozenset(
    [
        "has_stance_statement",
        "has_policy_position",
        "has_politician_action",
        "has_contradiction_signal",
        "advance",
    ]
)

# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _doc_id_from_custom_id(custom_id: str) -> str:
    """Strip the ``triage-`` prefix from a Batch API ``custom_id``.

    Parameters
    ----------
    custom_id:
        The ``custom_id`` field from the Batch API response line.

    Returns
    -------
    str
        The original ``doc_id``.
    """
    if custom_id.startswith(_CUSTOM_ID_PREFIX):
        return custom_id[len(_CUSTOM_ID_PREFIX) :]
    return custom_id


def _parse_triage_decision(
    raw: str,
    doc_id: str,
) -> tuple[Optional[TriageDecision], Optional[str]]:
    """Parse a triage decision JSON string from the model output.

    Parameters
    ----------
    raw:
        Raw text returned by the model.
    doc_id:
        Article identifier used only for error messages.

    Returns
    -------
    tuple[Optional[TriageDecision], Optional[str]]
        ``(decision, error_message)`` – exactly one of these will be
        non-``None``.
    """
    if not raw or not raw.strip():
        return None, "empty response"

    # Strip leading/trailing whitespace; try to isolate a JSON object if the
    # model added extra prose.
    text = raw.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None, f"no JSON object found in response for {doc_id!r}"
    text = text[start : end + 1]

    try:
        parsed: dict[str, Any] = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"JSON parse error for {doc_id!r}: {exc}"

    # Validate required keys.
    missing = _REQUIRED_BOOL_KEYS - parsed.keys()
    if missing:
        return None, f"missing required keys {sorted(missing)} for {doc_id!r}"

    # Coerce boolean fields – the model may return string "true"/"false".
    def _coerce_bool(val: Any, key: str) -> tuple[bool, Optional[str]]:
        if isinstance(val, bool):
            return val, None
        if isinstance(val, str):
            lower = val.lower()
            if lower in ("true", "1", "yes"):
                return True, None
            if lower in ("false", "0", "no"):
                return False, None
        return False, f"unexpected value {val!r} for key {key!r} in {doc_id!r}"

    errors: list[str] = []
    bool_values: dict[str, bool] = {}
    for key in _REQUIRED_BOOL_KEYS:
        coerced, err = _coerce_bool(parsed[key], key)
        if err:
            errors.append(err)
        bool_values[key] = coerced

    if errors:
        return None, "; ".join(errors)

    rationale: Optional[str] = parsed.get("rationale")
    if rationale and not isinstance(rationale, str):
        rationale = str(rationale)

    return (
        TriageDecision(
            has_stance_statement=bool_values["has_stance_statement"],
            has_policy_position=bool_values["has_policy_position"],
            has_politician_action=bool_values["has_politician_action"],
            has_contradiction_signal=bool_values["has_contradiction_signal"],
            advance=bool_values["advance"],
            rationale=rationale,
        ),
        None,
    )


# ---------------------------------------------------------------------------
# Index building from input file
# ---------------------------------------------------------------------------


def _build_provenance_index(
    input_jsonl: Path,
) -> dict[str, dict[str, Optional[str]]]:
    """Read the batch input JSONL and build a ``custom_id → provenance`` map.

    The provenance map stores the article metadata embedded in the user
    prompt so that the ingestion stage can reconstruct full
    :class:`~triage.models.TriageResult` objects without needing the
    original database.

    Parameters
    ----------
    input_jsonl:
        Path to the ``batch_input.jsonl`` file written by
        :func:`~triage.batch_requests.write_triage_batch_jsonl`.

    Returns
    -------
    dict[str, dict[str, Optional[str]]]
        Maps ``custom_id`` → ``{"doc_id": …, "title": …, "link": …,
        "date": …, "matched_politician": …}``.
    """
    index: dict[str, dict[str, Optional[str]]] = {}
    if not input_jsonl.exists():
        logger.warning("Input JSONL not found: %s; provenance will be partial.", input_jsonl)
        return index

    with input_jsonl.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                req: dict[str, Any] = json.loads(line)
            except json.JSONDecodeError as exc:
                logger.warning("Skipping malformed line %d in %s: %s", lineno, input_jsonl, exc)
                continue
            custom_id: str = req.get("custom_id", "")
            doc_id = _doc_id_from_custom_id(custom_id)

            # Extract provenance from the user message content.
            # The rendered prompt embeds "ARTICLE DOC_ID: {doc_id}" and
            # "ARTICLE TITLE: {title}" in the user message.
            messages: list[dict[str, Any]] = req.get("body", {}).get("messages", [])
            user_content: str = ""
            for msg in messages:
                if msg.get("role") == "user":
                    user_content = msg.get("content", "")
                    break

            title: Optional[str] = None
            for msg_line in user_content.splitlines():
                if msg_line.startswith("ARTICLE TITLE:"):
                    title = msg_line.split(":", 1)[1].strip() or None
                    break

            index[custom_id] = {
                "doc_id": doc_id,
                "title": title,
                "link": None,
                "date": None,
                "matched_politician": None,
            }

    return index


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def ingest_triage_batch_output(
    output_jsonl: Path | str,
    input_jsonl: Path | str | None = None,
    provenance: dict[str, dict[str, Optional[str]]] | None = None,
) -> TriageBatchIngestionResult:
    """Ingest a completed triage Batch API output file.

    Parameters
    ----------
    output_jsonl:
        Path to the completed Batch API output JSONL file.
    input_jsonl:
        Path to the matching batch input JSONL file.  Used to reconstruct
        article provenance (title, link, date, politician).  If ``None``
        and *provenance* is not supplied, provenance fields will be empty.
    provenance:
        Optional pre-built ``custom_id → provenance`` mapping (as returned
        by :func:`_build_provenance_index`).  If supplied, *input_jsonl* is
        ignored for provenance.  Useful in tests.

    Returns
    -------
    TriageBatchIngestionResult
        All results, with positives, negatives, failures, and parse errors
        classified and accessible as properties.

    Raises
    ------
    FileNotFoundError
        If *output_jsonl* does not exist.
    """
    out_path = Path(output_jsonl)
    if not out_path.exists():
        raise FileNotFoundError(f"Triage batch output not found: {out_path}")

    # Build provenance index from input file (if not supplied directly).
    if provenance is None and input_jsonl is not None:
        provenance = _build_provenance_index(Path(input_jsonl))
    if provenance is None:
        provenance = {}

    results: list[TriageResult] = []

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
            doc_id = _doc_id_from_custom_id(custom_id)
            prov = provenance.get(custom_id, {})

            # Resolve article metadata (provenance takes priority).
            title: Optional[str] = prov.get("title")
            link: Optional[str] = prov.get("link")
            date: Optional[str] = prov.get("date")
            matched_politician: Optional[str] = prov.get("matched_politician")

            # Check for a provider-level request failure.
            error_field: Optional[dict[str, Any]] = entry.get("error")
            if error_field:
                logger.warning(
                    "Batch request failed for %r (custom_id=%r): %s",
                    doc_id,
                    custom_id,
                    error_field,
                )
                results.append(
                    TriageResult(
                        doc_id=doc_id,
                        title=title,
                        link=link,
                        date=date,
                        matched_politician=matched_politician,
                        request_id=custom_id,
                        decision=None,
                        raw_response=None,
                        parse_error=str(error_field),
                        failed=True,
                    )
                )
                continue

            # Extract raw content from the response.
            response: dict[str, Any] = entry.get("response", {})
            status_code: int = response.get("status_code", 0)
            body: dict[str, Any] = response.get("body", {})

            if status_code != 200:
                logger.warning(
                    "Non-200 status %d for %r; treating as failure.", status_code, doc_id
                )
                results.append(
                    TriageResult(
                        doc_id=doc_id,
                        title=title,
                        link=link,
                        date=date,
                        matched_politician=matched_politician,
                        request_id=custom_id,
                        decision=None,
                        raw_response=None,
                        parse_error=f"HTTP status {status_code}",
                        failed=True,
                    )
                )
                continue

            choices: list[dict[str, Any]] = body.get("choices", [])
            raw_content: str = ""
            if choices:
                raw_content = choices[0].get("message", {}).get("content", "") or ""

            decision, parse_error = _parse_triage_decision(raw_content, doc_id)

            if parse_error:
                logger.warning("Parse error for %r: %s", doc_id, parse_error)

            results.append(
                TriageResult(
                    doc_id=doc_id,
                    title=title,
                    link=link,
                    date=date,
                    matched_politician=matched_politician,
                    request_id=custom_id,
                    decision=decision,
                    raw_response=raw_content,
                    parse_error=parse_error,
                    failed=False,
                )
            )

    ingestion_result = TriageBatchIngestionResult(results=results)
    logger.info(
        "Triage ingestion complete: %s", ingestion_result.summary()
    )
    return ingestion_result
