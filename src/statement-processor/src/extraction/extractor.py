"""
extraction.extractor
====================
Main LLM-based stance extraction orchestration for the statement-processor
pipeline.

This module coordinates:
1. Loading the prompt contract.
2. Chunking long articles.
3. Calling the LLM for each chunk (with retry on failure).
4. Parsing the JSON response into :class:`~extraction.models.CandidateStanceEvent`
   objects.
5. Writing raw/intermediate outputs to the debug log.
6. Returning :class:`~extraction.models.ExtractionResult` objects that are
   ready for later validation.

**Important**: This module treats all model output as **untrusted**.
Parsed candidate events are **not** inserted into final validated tables.
They are returned as candidates for a later validation step.

Usage
-----
    from extraction.extractor import extract_articles, extract_single_article
    from extraction.models import ArticleInput, ExtractionConfig

    config = ExtractionConfig(model_name="gpt-4o-mini", max_retries=2)
    article = ArticleInput(
        doc_id="art-001",
        text="President Biden said …",
        title="Biden on Healthcare",
        date="2025-01-15",
    )

    result = extract_single_article(article, config=config)
    print(result.event_count)          # 0-to-many
    print(result.candidate_events)     # untrusted candidates

    # Batch extraction
    results = extract_articles([article], config=config)
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

from .chunking import chunk_article
from .client import LLMClient, LLMClientError, LLMTimeoutError
from .debug_logger import DebugLogger
from .models import (
    ArticleInput,
    CandidateStanceEvent,
    ChunkInput,
    ExtractionConfig,
    ExtractionResult,
    RawExtractionOutput,
)
from .prompt_loader import load_prompt

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JSON parsing helpers
# ---------------------------------------------------------------------------

_REQUIRED_FIELDS: frozenset[str] = frozenset(
    [
        "politician",
        "topic",
        "normalized_proposition",
        "stance_direction",
        "stance_mode",
        "evidence_role",
        "confidence",
    ]
)


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _parse_raw_response(
    raw: str,
    doc_id: str,
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """Try to parse *raw* as a JSON object conforming to the extraction schema.

    Parameters
    ----------
    raw:
        Raw text returned by the LLM.
    doc_id:
        Article identifier, used only for error messages.

    Returns
    -------
    tuple[Optional[dict], Optional[str]]
        ``(parsed_json, error_message)``.  Exactly one of the two will be
        ``None``: on success ``error_message`` is ``None``; on failure
        ``parsed_json`` is ``None``.
    """
    stripped = raw.strip()
    if not stripped:
        return None, "empty response"

    # The prompt instructs the model to start with `{` and end with `}`.
    # Strip any accidental markdown fencing that some models add.
    if stripped.startswith("```"):
        # Remove ```json ... ``` or ``` ... ``` wrappers.
        lines = stripped.splitlines()
        # Drop first line (```json or ```) and last line (```)
        inner_lines = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        stripped = "\n".join(inner_lines).strip()

    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as exc:
        return None, f"JSON parse error: {exc}"

    if not isinstance(data, dict):
        return None, f"expected a JSON object, got {type(data).__name__}"

    if "stance_events" not in data:
        return None, "missing required top-level key 'stance_events'"

    if not isinstance(data["stance_events"], list):
        return None, "'stance_events' is not a list"

    return data, None


def _build_candidate(
    event_dict: dict[str, Any],
    doc_id: str,
    chunk_index: int,
    chunk_total: int,
) -> tuple[Optional[CandidateStanceEvent], Optional[str]]:
    """Try to build a :class:`~extraction.models.CandidateStanceEvent` from
    a raw event dict.

    Missing required fields result in a ``None`` candidate and an error
    message (the whole event is skipped rather than silently corrupted).

    Parameters
    ----------
    event_dict:
        A single element of the ``stance_events`` list from the model response.
    doc_id:
        Source article identifier to attach as provenance.
    chunk_index:
        0-based chunk index.
    chunk_total:
        Total number of chunks for the article.

    Returns
    -------
    tuple[Optional[CandidateStanceEvent], Optional[str]]
        ``(candidate, error_message)``.
    """
    missing = [f for f in _REQUIRED_FIELDS if f not in event_dict]
    if missing:
        return None, f"stance event missing required fields: {missing}"

    # confidence must be a number
    confidence_raw = event_dict.get("confidence")
    try:
        confidence = float(confidence_raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None, f"'confidence' is not a number: {confidence_raw!r}"

    return (
        CandidateStanceEvent(
            doc_id=doc_id,
            politician=str(event_dict["politician"]),
            topic=str(event_dict["topic"]),
            normalized_proposition=str(event_dict["normalized_proposition"]),
            stance_direction=str(event_dict["stance_direction"]),
            stance_mode=str(event_dict["stance_mode"]),
            evidence_role=str(event_dict["evidence_role"]),
            confidence=confidence,
            subtopic=event_dict.get("subtopic"),
            speaker=event_dict.get("speaker"),
            target_entity=event_dict.get("target_entity"),
            event_date=event_dict.get("event_date"),
            event_date_precision=event_dict.get("event_date_precision"),
            quote_text=event_dict.get("quote_text"),
            quote_start_char=event_dict.get("quote_start_char"),
            quote_end_char=event_dict.get("quote_end_char"),
            paraphrase=event_dict.get("paraphrase"),
            notes=event_dict.get("notes"),
            chunk_index=chunk_index,
            chunk_total=chunk_total,
        ),
        None,
    )


# ---------------------------------------------------------------------------
# Per-chunk extraction
# ---------------------------------------------------------------------------


def _extract_chunk(
    chunk: ChunkInput,
    client: LLMClient,
    config: ExtractionConfig,
    debug_logger: DebugLogger,
) -> tuple[list[CandidateStanceEvent], bool]:
    """Run LLM extraction for a single *chunk* with retry logic.

    Parameters
    ----------
    chunk:
        The text chunk to process.
    client:
        The :class:`~extraction.client.LLMClient` to use for completions.
    config:
        Extraction configuration (model, retries, temperature).
    debug_logger:
        :class:`~extraction.debug_logger.DebugLogger` for debug output.

    Returns
    -------
    tuple[list[CandidateStanceEvent], bool]
        ``(candidates, success)``.  ``success`` is ``False`` if all
        attempts failed.
    """
    last_raw = RawExtractionOutput(
        doc_id=chunk.doc_id,
        chunk_index=chunk.chunk_index,
        chunk_total=chunk.chunk_total,
        model_name=config.model_name,
        raw_response="",
        parsed_json=None,
        parse_error="not attempted",
        extraction_timestamp=_now_iso(),
        title=chunk.title,
        date=chunk.date,
        link=chunk.link,
    )

    for attempt in range(1, config.max_retries + 1):
        ts = _now_iso()
        raw_text = ""
        parsed: Optional[dict[str, Any]] = None
        error: Optional[str] = None

        try:
            system_msg, user_msg = load_prompt(
                doc_id=chunk.doc_id,
                article_text=chunk.chunk_text,
            )
            raw_text = client.complete(
                system_message=system_msg,
                user_message=user_msg,
            )
        except LLMTimeoutError as exc:
            error = f"timeout on attempt {attempt}: {exc}"
            logger.warning(
                "Chunk %s/%s of %r timed out (attempt %d/%d): %s",
                chunk.chunk_index + 1,
                chunk.chunk_total,
                chunk.doc_id,
                attempt,
                config.max_retries,
                exc,
            )
        except LLMClientError as exc:
            error = f"LLM client error on attempt {attempt}: {exc}"
            logger.error(
                "Chunk %s/%s of %r failed (attempt %d/%d): %s",
                chunk.chunk_index + 1,
                chunk.chunk_total,
                chunk.doc_id,
                attempt,
                config.max_retries,
                exc,
            )
        else:
            parsed, error = _parse_raw_response(raw_text, chunk.doc_id)

        raw_output = RawExtractionOutput(
            doc_id=chunk.doc_id,
            chunk_index=chunk.chunk_index,
            chunk_total=chunk.chunk_total,
            model_name=config.model_name,
            raw_response=raw_text,
            parsed_json=parsed,
            parse_error=error,
            extraction_timestamp=ts,
            title=chunk.title,
            date=chunk.date,
            link=chunk.link,
            attempt_number=attempt,
        )
        debug_logger.log(raw_output)
        last_raw = raw_output

        if error is None and parsed is not None:
            # Successfully parsed – build candidate events.
            candidates: list[CandidateStanceEvent] = []
            for event_dict in parsed.get("stance_events", []):
                candidate, build_err = _build_candidate(
                    event_dict,
                    doc_id=chunk.doc_id,
                    chunk_index=chunk.chunk_index,
                    chunk_total=chunk.chunk_total,
                )
                if build_err:
                    logger.warning(
                        "Skipping malformed stance event in %r chunk %d: %s",
                        chunk.doc_id,
                        chunk.chunk_index,
                        build_err,
                    )
                elif candidate is not None:
                    candidates.append(candidate)
            return candidates, True

        # Transient / parse failure: back off slightly before retry.
        if attempt < config.max_retries:
            time.sleep(0.5 * attempt)

    # All attempts exhausted.
    logger.error(
        "All %d attempt(s) failed for chunk %d/%d of %r. Last error: %s",
        config.max_retries,
        chunk.chunk_index + 1,
        chunk.chunk_total,
        chunk.doc_id,
        last_raw.parse_error,
    )
    return [], False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_single_article(
    article: ArticleInput,
    config: Optional[ExtractionConfig] = None,
    client: Optional[LLMClient] = None,
    debug_logger: Optional[DebugLogger] = None,
) -> ExtractionResult:
    """Run LLM-based stance extraction on a single article.

    Parameters
    ----------
    article:
        The article to extract from.
    config:
        Extraction configuration.  Defaults to :class:`ExtractionConfig`
        with ``model_name="gpt-4o-mini"``.
    client:
        LLM client to use.  If ``None``, a new :class:`LLMClient` is
        created from *config*.  Inject a mock here in tests.
    debug_logger:
        Debug logger.  If ``None``, a new :class:`DebugLogger` is created
        using the path from *config*.

    Returns
    -------
    ExtractionResult
        Contains zero-to-many candidate stance events plus all raw outputs
        and provenance metadata.

    Notes
    -----
    Candidate events are **untrusted** – they must pass a later validation
    step before being persisted to final tables.
    """
    cfg = config or ExtractionConfig()
    llm_client = client or LLMClient(config=cfg)
    dbg = debug_logger or DebugLogger(
        log_path=cfg.debug_log_path,
        enabled=cfg.debug_log_path is not None,
    )

    chunks = chunk_article(article, max_chars=cfg.max_chunk_chars)
    all_candidates: list[CandidateStanceEvent] = []
    all_raw: list[RawExtractionOutput] = []
    failed_chunks = 0

    for chunk in chunks:
        candidates, success = _extract_chunk(chunk, llm_client, cfg, dbg)
        if not success:
            failed_chunks += 1
        all_candidates.extend(candidates)

    # Collect raw outputs from the debug logger (already written) – we
    # reconstruct the count from failed_chunks since raw outputs are logged
    # inside _extract_chunk.
    return ExtractionResult(
        doc_id=article.doc_id,
        title=article.title,
        date=article.date,
        link=article.link,
        candidate_events=all_candidates,
        raw_outputs=all_raw,  # populated via debug_logger; kept empty here
        total_chunks=len(chunks),
        failed_chunks=failed_chunks,
    )


def extract_articles(
    articles: list[ArticleInput],
    config: Optional[ExtractionConfig] = None,
    client: Optional[LLMClient] = None,
    debug_logger: Optional[DebugLogger] = None,
) -> list[ExtractionResult]:
    """Run LLM-based stance extraction on a batch of articles.

    Articles are processed sequentially (one at a time).  The same LLM
    client and debug logger are reused across all articles to avoid
    re-initialisation overhead.

    Parameters
    ----------
    articles:
        Ordered list of articles to extract from.
    config:
        Extraction configuration shared across all articles.
    client:
        LLM client to use.  If ``None``, one is created from *config*.
    debug_logger:
        Debug logger shared across all articles.

    Returns
    -------
    list[ExtractionResult]
        One result per article, in the same order as the input.
    """
    cfg = config or ExtractionConfig()
    llm_client = client or LLMClient(config=cfg)
    dbg = debug_logger or DebugLogger(
        log_path=cfg.debug_log_path,
        enabled=cfg.debug_log_path is not None,
    )

    results: list[ExtractionResult] = []
    for i, article in enumerate(articles):
        logger.info(
            "Extracting article %d/%d: %r",
            i + 1,
            len(articles),
            article.doc_id,
        )
        result = extract_single_article(
            article,
            config=cfg,
            client=llm_client,
            debug_logger=dbg,
        )
        results.append(result)
        logger.info(
            "  → %d candidate event(s), %d chunk(s) failed",
            result.event_count,
            result.failed_chunks,
        )

    return results


# ---------------------------------------------------------------------------
# SQLite-backed convenience loader
# ---------------------------------------------------------------------------


def load_articles_from_db(
    doc_ids: list[str],
    db_path: Optional[str] = None,
) -> list[ArticleInput]:
    """Load :class:`ArticleInput` records from the local SQLite database.

    This is a convenience function for the CLI and integration tests.  It
    reads article rows from ``news_articles`` by ``doc_id`` and converts
    them to :class:`~extraction.models.ArticleInput` objects.

    Parameters
    ----------
    doc_ids:
        List of ``doc_id`` values to load.
    db_path:
        Path to the SQLite database file.  Defaults to the project default
        (``data/political_dossier.db``).

    Returns
    -------
    list[ArticleInput]
        Articles in the same order as *doc_ids*.  Missing ``doc_id`` values
        are silently skipped with a warning.
    """
    import sys
    from pathlib import Path as _Path

    # Ensure the db package is importable.
    _src_dir = str(_Path(__file__).parent.parent)
    if _src_dir not in sys.path:
        sys.path.insert(0, _src_dir)

    from db.sqlite_utils import get_connection, get_default_db_path

    resolved = _Path(db_path).resolve() if db_path else get_default_db_path()
    conn = get_connection(resolved)
    articles: list[ArticleInput] = []
    try:
        for doc_id in doc_ids:
            row = conn.execute(
                "SELECT doc_id, title, text, date, link FROM news_articles "
                "WHERE doc_id = ?",
                (doc_id,),
            ).fetchone()
            if row is None:
                logger.warning("doc_id %r not found in database; skipping.", doc_id)
                continue
            articles.append(
                ArticleInput(
                    doc_id=row["doc_id"],
                    text=row["text"] or "",
                    title=row["title"],
                    date=row["date"],
                    link=row["link"],
                )
            )
    finally:
        conn.close()

    return articles
