"""
pipeline.bulk_option_a
======================
Main orchestration module for the bulk Option-A processing pipeline.

This module provides individually runnable stage functions so that the
pipeline can be executed step by step rather than only as one monolithic
command.  Each stage function:

- accepts a :class:`BulkPipelineConfig` and a run directory,
- writes inspectable artifacts to the run directory,
- returns structured typed output,
- is independently resumable.

Pipeline stages
---------------
1. :func:`run_select`            – deterministic pre-filter (no LLM)
2. :func:`run_prepare_triage`    – generate triage Batch API JSONL
3. :func:`run_ingest_triage`     – ingest completed triage batch output
4. :func:`run_prepare_extraction` – generate extraction Batch API JSONL
5. :func:`run_ingest_extraction`  – ingest completed extraction batch output

Usage
-----
    from pipeline.bulk_option_a import BulkPipelineConfig, run_select
    from pipeline.artifacts import resolve_run_dir
    from pathlib import Path

    config = BulkPipelineConfig(
        politicians=["Trump", "Biden"],
        min_score=1,
    )
    triage_run_dir = resolve_run_dir("data/batch_artifacts/triage", run_id="run-001")
    selected = run_select(config, triage_run_dir)
    print(f"Selected {len(selected)} articles")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from extraction.batch_ingest import ExtractionBatchIngestionResult, ingest_extraction_batch_output
from extraction.batch_requests import build_extraction_batch_requests, write_extraction_batch_jsonl
from extraction.models import ArticleInput, ExtractionConfig
from selection.article_selector import select_candidate_articles
from selection.models import ScoredArticle, SelectionConfig
from triage.batch_ingest import ingest_triage_batch_output
from triage.batch_requests import build_triage_batch_requests, write_triage_batch_jsonl
from triage.models import TriageArticle, TriageBatchIngestionResult, TriageConfig

from .artifacts import resolve_run_dir, write_artifact, write_jsonl_artifact, write_summary

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pipeline config
# ---------------------------------------------------------------------------


@dataclass
class BulkPipelineConfig:
    """Configuration for the bulk Option-A pipeline.

    Attributes
    ----------
    politicians:
        Canonical politician names to target.  Must be keys in
        :data:`~selection.keywords.POLITICIAN_ALIASES`.
    min_score:
        Minimum selection score for an article to pass deterministic filtering.
    max_results:
        Optional cap on the number of selected articles.
    date_from:
        Optional ISO-8601 date lower bound for article selection.
    date_to:
        Optional ISO-8601 date upper bound for article selection.
    triage_config:
        Configuration for the triage stage.
    extraction_config:
        Configuration for the full extraction stage.
    db_path:
        Path to the local SQLite database.  ``None`` uses the project
        default (``data/political_dossier.db``).
    artifacts_base_dir:
        Root directory for all pipeline artifacts.
    """

    politicians: list[str] = field(default_factory=lambda: ["Trump", "Biden"])
    min_score: int = 1
    max_results: Optional[int] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    triage_config: TriageConfig = field(default_factory=TriageConfig)
    extraction_config: ExtractionConfig = field(default_factory=ExtractionConfig)
    db_path: Optional[str] = None
    artifacts_base_dir: str = "data/batch_artifacts"


# ---------------------------------------------------------------------------
# Stage 1 – deterministic pre-filter
# ---------------------------------------------------------------------------


def run_select(
    config: BulkPipelineConfig,
    run_dir: Path,
) -> list[ScoredArticle]:
    """Run the deterministic pre-filter and write selected article artifacts.

    This stage runs entirely locally with no LLM calls.

    Parameters
    ----------
    config:
        Pipeline configuration.
    run_dir:
        Directory where the ``selected_articles.jsonl`` and
        ``summary.json`` artifacts are written.

    Returns
    -------
    list[ScoredArticle]
        Eligible scored articles, sorted by score descending.
    """
    selection_config = SelectionConfig(
        politicians=config.politicians,
        min_score=config.min_score,
        max_results=config.max_results,
        date_from=config.date_from,
        date_to=config.date_to,
    )

    logger.info(
        "Running deterministic selection for politicians=%s min_score=%d",
        config.politicians,
        config.min_score,
    )
    result = select_candidate_articles(config=selection_config, db_path=config.db_path)
    eligible = result.eligible_articles

    logger.info(
        "Selection: %d total candidates, %d eligible",
        result.total_candidates,
        result.eligible_count,
    )

    # Write artifacts.
    articles_jsonl = run_dir / "selected_articles.jsonl"
    write_jsonl_artifact(
        [
            {
                "doc_id": a.doc_id,
                "title": a.title,
                "matched_politician": a.matched_politician,
                "score": a.score,
                "matched_rules": list(a.matched_rules),
                "is_eligible": a.is_eligible,
            }
            for a in eligible
        ],
        articles_jsonl,
    )
    write_summary(
        {
            "stage": "select",
            "total_candidates": result.total_candidates,
            "eligible_count": result.eligible_count,
            "politicians": config.politicians,
            "min_score": config.min_score,
        },
        run_dir / "summary.json",
    )
    logger.info("Selection artifacts written to %s", run_dir)
    return eligible


# ---------------------------------------------------------------------------
# Stage 2 – triage batch preparation
# ---------------------------------------------------------------------------


def run_prepare_triage(
    selected_articles: list[ScoredArticle],
    config: BulkPipelineConfig,
    run_dir: Path,
    db_path: Optional[str] = None,
) -> list[Path]:
    """Load full article text and generate the triage Batch API JSONL.

    This stage reads the article text from the local SQLite database for
    each selected article and builds the triage batch input file.

    Parameters
    ----------
    selected_articles:
        Eligible articles from :func:`run_select`.
    config:
        Pipeline configuration.
    run_dir:
        Directory where ``batch_input.jsonl`` is written.
    db_path:
        Path to the SQLite database.  Falls back to ``config.db_path`` and
        then the project default.

    Returns
    -------
    list[Path]
        Paths to the written batch input JSONL file(s).
    """
    resolved_db = db_path or config.db_path

    # Load article text from the database.
    triage_articles = _load_triage_articles(selected_articles, resolved_db)

    logger.info(
        "Preparing triage batch for %d articles (model=%s)",
        len(triage_articles),
        config.triage_config.model_name,
    )

    requests = build_triage_batch_requests(triage_articles, config.triage_config)
    paths = write_triage_batch_jsonl(
        requests,
        output_dir=run_dir,
        batch_size=config.triage_config.batch_size,
    )

    write_summary(
        {
            "stage": "prepare_triage",
            "article_count": len(triage_articles),
            "request_count": len(requests),
            "batch_files": [str(p) for p in paths],
            "model": config.triage_config.model_name,
        },
        run_dir / "prepare_summary.json",
    )
    logger.info("Triage batch input written to %s (%d files)", run_dir, len(paths))
    return paths


def _load_triage_articles(
    selected_articles: list[ScoredArticle],
    db_path: Optional[str],
) -> list[TriageArticle]:
    """Load article text from SQLite and build :class:`TriageArticle` objects.

    Parameters
    ----------
    selected_articles:
        Scored articles with doc_id and politician.
    db_path:
        Path to the SQLite database.

    Returns
    -------
    list[TriageArticle]
        Articles ready for the triage stage.
    """
    from db.sqlite_utils import get_connection, get_default_db_path

    resolved = Path(db_path).resolve() if db_path else get_default_db_path()
    conn = get_connection(resolved)

    # Build a lookup for matched_politician.
    politician_by_doc_id = {a.doc_id: a.matched_politician for a in selected_articles}
    doc_ids = [a.doc_id for a in selected_articles]

    articles: list[TriageArticle] = []
    try:
        for doc_id in doc_ids:
            row = conn.execute(
                "SELECT doc_id, title, text, date, link FROM news_articles WHERE doc_id = ?",
                (doc_id,),
            ).fetchone()
            if row is None:
                logger.warning("doc_id %r not found in database; skipping.", doc_id)
                continue
            articles.append(
                TriageArticle(
                    doc_id=row["doc_id"],
                    title=row["title"] or "",
                    text=row["text"] or "",
                    date=row["date"],
                    link=row["link"],
                    matched_politician=politician_by_doc_id.get(doc_id),
                )
            )
    finally:
        conn.close()

    return articles


# ---------------------------------------------------------------------------
# Stage 3 – triage batch ingestion
# ---------------------------------------------------------------------------


def run_ingest_triage(
    run_dir: Path,
    output_jsonl_name: str = "batch_output.jsonl",
) -> TriageBatchIngestionResult:
    """Ingest the completed triage batch output and write result artifacts.

    The user must place the completed Batch API output file in *run_dir*
    before calling this function.

    Parameters
    ----------
    run_dir:
        Directory containing both ``batch_input.jsonl`` and the completed
        ``batch_output.jsonl`` (or the name given by *output_jsonl_name*).
    output_jsonl_name:
        Name of the completed output file.  Defaults to
        ``"batch_output.jsonl"``.

    Returns
    -------
    TriageBatchIngestionResult
        Classified triage results.
    """
    output_path = run_dir / output_jsonl_name
    input_path = run_dir / "batch_input.jsonl"

    logger.info("Ingesting triage batch output from %s", output_path)
    ingestion = ingest_triage_batch_output(
        output_jsonl=output_path,
        input_jsonl=input_path if input_path.exists() else None,
    )

    # Write per-class artifact files.
    write_jsonl_artifact(
        [
            {
                "doc_id": r.doc_id,
                "title": r.title,
                "link": r.link,
                "date": r.date,
                "matched_politician": r.matched_politician,
                "request_id": r.request_id,
                "advance": r.decision.advance if r.decision else None,
                "rationale": r.decision.rationale if r.decision else None,
                "has_stance_statement": r.decision.has_stance_statement if r.decision else None,
                "has_policy_position": r.decision.has_policy_position if r.decision else None,
                "has_politician_action": r.decision.has_politician_action if r.decision else None,
                "has_contradiction_signal": r.decision.has_contradiction_signal if r.decision else None,
            }
            for r in ingestion.results
        ],
        run_dir / "triage_results.jsonl",
    )
    write_jsonl_artifact(
        [{"doc_id": r.doc_id, "request_id": r.request_id} for r in ingestion.positives],
        run_dir / "positives.jsonl",
    )
    write_jsonl_artifact(
        [{"doc_id": r.doc_id, "request_id": r.request_id} for r in ingestion.negatives],
        run_dir / "negatives.jsonl",
    )
    write_jsonl_artifact(
        [
            {
                "doc_id": r.doc_id,
                "request_id": r.request_id,
                "parse_error": r.parse_error,
                "failed": r.failed,
            }
            for r in ingestion.retry_candidates
        ],
        run_dir / "retry_candidates.jsonl",
    )
    write_summary(ingestion.summary(), run_dir / "summary.json")
    logger.info("Triage ingestion complete: %s", ingestion.summary())
    return ingestion


# ---------------------------------------------------------------------------
# Stage 4 – extraction batch preparation
# ---------------------------------------------------------------------------


def run_prepare_extraction(
    triage_result: TriageBatchIngestionResult,
    config: BulkPipelineConfig,
    run_dir: Path,
    db_path: Optional[str] = None,
) -> list[Path]:
    """Load triage-positive articles and generate the extraction Batch API JSONL.

    Only articles flagged as positive by triage are sent to the extraction
    stage.

    Parameters
    ----------
    triage_result:
        The result of :func:`run_ingest_triage`.
    config:
        Pipeline configuration.
    run_dir:
        Directory where ``batch_input.jsonl`` is written.
    db_path:
        Path to the SQLite database.

    Returns
    -------
    list[Path]
        Paths to the written batch input JSONL file(s).
    """
    positives = triage_result.positives
    logger.info(
        "Preparing extraction batch for %d triage-positive articles (model=%s)",
        len(positives),
        config.extraction_config.model_name,
    )

    if not positives:
        logger.warning("No triage-positive articles; extraction batch will be empty.")
        write_summary(
            {
                "stage": "prepare_extraction",
                "article_count": 0,
                "request_count": 0,
                "batch_files": [],
            },
            run_dir / "prepare_summary.json",
        )
        return []

    # Load full article text.
    resolved_db = db_path or config.db_path
    doc_ids = [r.doc_id for r in positives]
    articles = _load_extraction_articles(doc_ids, resolved_db)

    # Write the article list for inspection.
    write_jsonl_artifact(
        [
            {
                "doc_id": a.doc_id,
                "title": a.title,
                "date": a.date,
                "link": a.link,
            }
            for a in articles
        ],
        run_dir / "articles_for_extraction.jsonl",
    )

    requests = build_extraction_batch_requests(articles, config.extraction_config)
    paths = write_extraction_batch_jsonl(
        requests,
        output_dir=run_dir,
        batch_size=config.triage_config.batch_size,
    )

    write_summary(
        {
            "stage": "prepare_extraction",
            "article_count": len(articles),
            "request_count": len(requests),
            "batch_files": [str(p) for p in paths],
            "model": config.extraction_config.model_name,
        },
        run_dir / "prepare_summary.json",
    )
    logger.info("Extraction batch input written to %s (%d files)", run_dir, len(paths))
    return paths


def _load_extraction_articles(
    doc_ids: list[str],
    db_path: Optional[str],
) -> list[ArticleInput]:
    """Load article text from SQLite for extraction.

    Parameters
    ----------
    doc_ids:
        List of doc_id values to load.
    db_path:
        Path to the SQLite database.

    Returns
    -------
    list[ArticleInput]
        Articles ready for batch extraction request building.
    """
    from db.sqlite_utils import get_connection, get_default_db_path

    resolved = Path(db_path).resolve() if db_path else get_default_db_path()
    conn = get_connection(resolved)

    articles: list[ArticleInput] = []
    try:
        for doc_id in doc_ids:
            row = conn.execute(
                "SELECT doc_id, title, text, date, link FROM news_articles WHERE doc_id = ?",
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


# ---------------------------------------------------------------------------
# Stage 5 – extraction batch ingestion
# ---------------------------------------------------------------------------


def run_ingest_extraction(
    run_dir: Path,
    output_jsonl_name: str = "batch_output.jsonl",
    model_name: str = "unknown",
) -> ExtractionBatchIngestionResult:
    """Ingest the completed extraction batch output and write result artifacts.

    The user must place the completed Batch API output file in *run_dir*
    before calling this function.

    All parsed events are stored as **raw candidate outputs** – they are not
    validated or persisted.

    Parameters
    ----------
    run_dir:
        Directory containing both ``batch_input.jsonl`` and the completed
        ``batch_output.jsonl`` (or the name given by *output_jsonl_name*).
    output_jsonl_name:
        Name of the completed output file.  Defaults to
        ``"batch_output.jsonl"``.
    model_name:
        Model name to record in raw outputs.

    Returns
    -------
    ExtractionBatchIngestionResult
        Raw outputs, candidate events, failures, and parse errors.
    """
    output_path = run_dir / output_jsonl_name
    input_path = run_dir / "batch_input.jsonl"

    logger.info("Ingesting extraction batch output from %s", output_path)
    result = ingest_extraction_batch_output(
        output_jsonl=output_path,
        input_jsonl=input_path if input_path.exists() else None,
        model_name=model_name,
    )

    # Write raw outputs artifact.
    write_jsonl_artifact(
        [
            {
                "doc_id": r.doc_id,
                "chunk_index": r.chunk_index,
                "chunk_total": r.chunk_total,
                "model_name": r.model_name,
                "parse_error": r.parse_error,
                "has_parsed_json": r.parsed_json is not None,
                "extraction_timestamp": r.extraction_timestamp,
            }
            for r in result.raw_outputs
        ],
        run_dir / "raw_outputs.jsonl",
    )

    # Write candidate events (untrusted).
    write_jsonl_artifact(
        [
            {
                "doc_id": e.doc_id,
                "politician": e.politician,
                "topic": e.topic,
                "normalized_proposition": e.normalized_proposition,
                "stance_direction": e.stance_direction,
                "stance_mode": e.stance_mode,
                "evidence_role": e.evidence_role,
                "confidence": e.confidence,
                "chunk_index": e.chunk_index,
                "chunk_total": e.chunk_total,
            }
            for e in result.candidate_events
        ],
        run_dir / "candidate_events.jsonl",
    )

    # Write failures.
    write_jsonl_artifact(
        [{"custom_id": cid} for cid in result.failed_requests],
        run_dir / "failures.jsonl",
    )
    write_jsonl_artifact(
        [{"doc_id": did} for did in result.parse_error_ids],
        run_dir / "parse_errors.jsonl",
    )

    write_summary(result.summary(), run_dir / "summary.json")
    logger.info("Extraction ingestion complete: %s", result.summary())
    return result
