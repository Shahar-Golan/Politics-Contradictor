"""
selection.article_selector
==========================
Main article selection layer for the statement-processor pipeline.

Reads candidate articles from the local SQLite ``news_articles`` table,
applies deterministic rule-based scoring, and returns a
:class:`~selection.models.SelectionResult` with the highest-scoring articles
first.

Usage example::

    from selection.article_selector import select_candidate_articles
    from selection.models import SelectionConfig

    config = SelectionConfig(politicians=["Trump"], min_score=2, max_results=50)
    result = select_candidate_articles(config=config, db_path="/tmp/political_dossier.db")

    for article in result.eligible_articles:
        print(article.doc_id, article.score, article.matched_rules)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Optional

from db.sqlite_utils import get_connection, get_default_db_path
from .keywords import POLITICIAN_ALIASES
from .models import SelectionConfig, SelectionResult, ScoredArticle
from .scoring import score_article_for_extraction

# ---------------------------------------------------------------------------
# SQL helpers
# ---------------------------------------------------------------------------

_BASE_QUERY = """
SELECT
    doc_id,
    title,
    text,
    date,
    speakers_mentioned
FROM news_articles
WHERE 1=1
"""


def _build_selection_query(
    aliases: frozenset[str],
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> tuple[str, list[Any]]:
    """Build a SQL query that pre-filters articles by politician aliases.

    The query uses a broad LIKE / JSON-text search to narrow the full table
    down to articles that mention at least one alias.  Fine-grained scoring
    is then applied in Python.

    Parameters
    ----------
    aliases:
        A frozenset of lower-cased politician alias strings.
    date_from:
        Optional ISO-8601 date lower bound (inclusive).
    date_to:
        Optional ISO-8601 date upper bound (inclusive).

    Returns
    -------
    tuple[str, list]
        ``(sql_string, parameters_list)`` ready for
        ``conn.execute(sql, params)``.
    """
    sql = _BASE_QUERY
    params: list[Any] = []

    # Build an OR clause: (lower(title) LIKE ? OR lower(text) LIKE ?
    #                       OR lower(speakers_mentioned) LIKE ?)
    # for each alias.
    alias_clauses: list[str] = []
    for alias in sorted(aliases):  # sort for determinism
        pattern = f"%{alias}%"
        alias_clauses.append(
            "(lower(title) LIKE ? OR lower(text) LIKE ? OR lower(speakers_mentioned) LIKE ?)"
        )
        params.extend([pattern, pattern, pattern])

    if alias_clauses:
        sql += " AND (" + " OR ".join(alias_clauses) + ")"

    if date_from:
        sql += " AND date >= ?"
        params.append(date_from)

    if date_to:
        sql += " AND date <= ?"
        params.append(date_to)

    # Deterministic ordering: newest first, then by doc_id for ties.
    sql += " ORDER BY date DESC, doc_id ASC"

    return sql, params


# ---------------------------------------------------------------------------
# Public selection function
# ---------------------------------------------------------------------------


def select_candidate_articles(
    config: Optional[SelectionConfig] = None,
    db_path: Optional[Path | str] = None,
) -> SelectionResult:
    """Select and score candidate articles from the local SQLite database.

    The function:
    1. Resolves the database path (defaults to the project default).
    2. For each politician in ``config.politicians``, runs a broad SQL
       pre-filter using politician aliases.
    3. Scores every candidate article using deterministic rule-based logic.
    4. De-duplicates across politicians (a single article that mentions
       multiple politicians is scored against the politician that yields the
       highest score).
    5. Sorts results by score descending, then by ``doc_id`` ascending for
       ties (ensuring determinism across runs).
    6. Applies ``max_results`` cap on the eligible subset if configured.

    Parameters
    ----------
    config:
        :class:`~selection.models.SelectionConfig` controlling which
        politicians to target, the minimum eligibility score, and optional
        date range / result caps.  If ``None``, a default config is used.
    db_path:
        Path to the SQLite database file.  Defaults to the project's
        ``data/political_dossier.db``.

    Returns
    -------
    SelectionResult
        Contains all scored articles (both eligible and ineligible),
        sorted by score descending, plus summary counts.

    Raises
    ------
    ValueError
        If an unknown politician name is passed in ``config.politicians``.
    FileNotFoundError
        If the database file does not exist.
    """
    if config is None:
        config = SelectionConfig()

    # Validate politician names up-front.
    unknown = [p for p in config.politicians if p not in POLITICIAN_ALIASES]
    if unknown:
        raise ValueError(
            f"Unknown politician(s): {unknown}. "
            f"Available: {sorted(POLITICIAN_ALIASES)}"
        )

    resolved_db = Path(db_path).resolve() if db_path else get_default_db_path()
    if not resolved_db.exists():
        raise FileNotFoundError(f"Database not found: {resolved_db}")

    # ------------------------------------------------------------------
    # Query and score articles for each politician.  Track the best score
    # per doc_id to handle articles mentioning multiple politicians.
    # ------------------------------------------------------------------

    # best_scored: doc_id -> ScoredArticle with the highest score seen so far
    best_scored: dict[str, ScoredArticle] = {}

    conn: sqlite3.Connection = get_connection(resolved_db)
    try:
        for politician in config.politicians:
            aliases = POLITICIAN_ALIASES[politician]
            sql, params = _build_selection_query(
                aliases,
                date_from=config.date_from,
                date_to=config.date_to,
            )
            rows = conn.execute(sql, params).fetchall()

            for row in rows:
                row_dict: dict[str, Any] = dict(row)
                scored = score_article_for_extraction(row_dict, politician, config)

                existing = best_scored.get(scored.doc_id)
                if existing is None or scored.score > existing.score:
                    best_scored[scored.doc_id] = scored
    finally:
        conn.close()

    # ------------------------------------------------------------------
    # Sort: highest score first, then doc_id ascending for determinism.
    # ------------------------------------------------------------------
    all_articles: list[ScoredArticle] = sorted(
        best_scored.values(),
        key=lambda a: (-a.score, a.doc_id),
    )

    total_candidates = len(all_articles)
    eligible = [a for a in all_articles if a.is_eligible]
    eligible_count = len(eligible)

    # Apply max_results cap to the eligible set; keep all ineligible for
    # inspection.
    if config.max_results is not None:
        eligible = eligible[: config.max_results]

    # Rebuild the combined list: capped eligible first, then ineligible.
    ineligible = [a for a in all_articles if not a.is_eligible]
    all_articles = eligible + ineligible

    return SelectionResult(
        articles=all_articles,
        config=config,
        total_candidates=total_candidates,
        eligible_count=eligible_count,
    )
