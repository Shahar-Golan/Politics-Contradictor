"""
pipelines.ingest_article
========================
Article ingestion pipeline: extracts content from a fetched raw article,
scores politician relevance, extracts statement candidates, tags topics,
and writes all outputs to the database and document store.

This pipeline takes a pre-fetched ``RawArticle`` as input.  HTML fetching
is handled upstream (e.g. by the Scout fetcher or a backfill job).
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from src.extractor.article_extractor import extract_article
from src.extractor.models import ExtractedArticle, PoliticianMention, StatementCandidate
from src.extractor.quotes import extract_statements
from src.extractor.relevance import PoliticianConfig as RelevancePoliticianConfig
from src.extractor.relevance import find_mentions
from src.extractor.topics import tag_article
from src.scout.models import RawArticle
from src.storage.document_store import save_extracted_text, save_raw_html
from src.storage.sql import (
    get_feed_item,
    get_feed_source_name,
    insert_extracted_article,
    insert_politician_mention,
    insert_raw_article,
    insert_statement_candidate,
)
from src.utils.config import AppSettings, PoliticianConfig

logger = logging.getLogger(__name__)


@dataclass
class ArticleIngestResult:
    """Result of a single article ingestion run.

    Attributes:
        article_id: ID of the processed article.
        raw_article: The input raw article record.
        extracted_article: Extraction result, or ``None`` if extraction failed.
        mentions: Relevance scores for each tracked politician above threshold.
        statements: Statement / quote candidates attributed to politicians.
        topics: Topic IDs matched in the article.
        mentions_count: Number of politician mention records written.
        statements_count: Number of statement candidate records written.
        skipped_reason: Human-readable reason when processing was skipped.
        success: ``False`` if a write error occurred during persistence.
    """

    article_id: str
    raw_article: RawArticle
    extracted_article: ExtractedArticle | None = None
    mentions: list[PoliticianMention] = field(default_factory=list)
    statements: list[StatementCandidate] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    mentions_count: int = 0
    statements_count: int = 0
    skipped_reason: str | None = None
    success: bool = True


def ingest_article(
    raw: RawArticle,
    conn: sqlite3.Connection,
    politicians: list[PoliticianConfig],
    topics: dict[str, list[str]],
    settings: AppSettings,
) -> ArticleIngestResult:
    """Run the full article ingestion pipeline for a pre-fetched raw article.

    Steps:

    1. Save raw HTML to the document store.
    2. Persist ``RawArticle`` metadata to the database.
    3. Extract clean text and metadata from the HTML.
    4. If extraction yields no body, log and return a skipped result.
    5. Save the extracted body to the document store.
    6. Persist the ``ExtractedArticle`` record.
    7. Score politician relevance; persist each ``PoliticianMention``.
    8. For politicians above the relevance threshold, extract statement
       candidates and persist each ``StatementCandidate``.
    9. Tag article topics.
    10. Return an ``ArticleIngestResult`` with counts and status.

    Args:
        raw: Pre-fetched ``RawArticle`` containing HTML and fetch metadata.
        conn: Open SQLite connection used for all persistence writes.
        politicians: Politician configurations to score relevance against.
        topics: Topic taxonomy mapping (topic ID → keyword list).
        settings: Application settings (extraction backend, data dir, etc.).

    Returns:
        An ``ArticleIngestResult`` describing the outcome of the run.
    """
    data_dir = Path(settings.storage.data_dir)
    article_id = raw.article_id

    # ------------------------------------------------------------------
    # 1. Save raw HTML to document store (even on empty body — we keep
    #    the artefact for debugging).
    # ------------------------------------------------------------------
    html_path = save_raw_html(article_id, raw.html, data_dir)

    # ------------------------------------------------------------------
    # 2. Persist raw article metadata.
    # ------------------------------------------------------------------
    try:
        insert_raw_article(conn, raw, str(html_path))
    except Exception:
        logger.exception("Failed to persist raw article %s.", article_id)
        return ArticleIngestResult(
            article_id=article_id,
            raw_article=raw,
            skipped_reason="Database write failed for raw_articles",
            success=False,
        )

    # ------------------------------------------------------------------
    # 3. Extract article.
    # ------------------------------------------------------------------
    if not raw.html:
        logger.warning("Skipping extraction for %s: empty HTML.", article_id)
        return ArticleIngestResult(
            article_id=article_id,
            raw_article=raw,
            skipped_reason=raw.error_message or "Empty HTML",
        )

    extracted = extract_article(raw, settings)

    # ------------------------------------------------------------------
    # 3b. Metadata fallbacks from feed data.
    #     When HTML extraction fails to find the publication date or site
    #     name, fall back to values from the RSS feed / feeds.yaml.
    # ------------------------------------------------------------------
    feed_item = get_feed_item(conn, raw.feed_item_id)
    if feed_item is not None:
        if not extracted.metadata.published_at and feed_item.published_at:
            extracted.metadata.published_at = feed_item.published_at
            logger.debug(
                "Fallback published_at from feed item for %s.", article_id
            )
        if not extracted.metadata.site_name:
            feed_source_name = get_feed_source_name(conn, feed_item.feed_id)
            if feed_source_name:
                extracted.metadata.site_name = feed_source_name
                logger.debug(
                    "Fallback site_name from feed source for %s.", article_id
                )

    if not extracted.body:
        logger.warning("Extraction yielded no content for %s.", article_id)
        return ArticleIngestResult(
            article_id=article_id,
            raw_article=raw,
            extracted_article=extracted,
            skipped_reason="Extraction returned no content",
        )

    # ------------------------------------------------------------------
    # 4. Save extracted body to document store.
    # ------------------------------------------------------------------
    body_path = save_extracted_text(article_id, extracted.body, data_dir)

    # ------------------------------------------------------------------
    # 5. Persist extracted article record.
    # ------------------------------------------------------------------
    try:
        insert_extracted_article(conn, extracted, str(body_path))
    except Exception:
        logger.exception("Failed to persist extracted article %s.", article_id)
        return ArticleIngestResult(
            article_id=article_id,
            raw_article=raw,
            extracted_article=extracted,
            skipped_reason="Database write failed for extracted_articles",
            success=False,
        )

    # ------------------------------------------------------------------
    # 6. Score relevance and persist politician mentions.
    # ------------------------------------------------------------------
    min_score = settings.relevance.min_score
    # find_mentions expects extractor.relevance.PoliticianConfig (id/name/aliases only).
    # utils.config.PoliticianConfig is a superset; project the relevant fields.
    relevance_politicians = [
        RelevancePoliticianConfig(id=p.id, name=p.name, aliases=p.aliases)
        for p in politicians
    ]
    mentions = find_mentions(
        article_id=article_id,
        body=extracted.body,
        title=extracted.metadata.title,
        politicians=relevance_politicians,
        min_score=0.0,
    )

    persisted_mentions: list[PoliticianMention] = []
    for mention in mentions:
        try:
            insert_politician_mention(conn, mention)
            persisted_mentions.append(mention)
        except Exception:
            logger.exception(
                "Failed to persist politician mention for %s in %s.",
                mention.politician_id,
                article_id,
            )

    # ------------------------------------------------------------------
    # 7. Extract and persist statement candidates for relevant politicians.
    # ------------------------------------------------------------------
    all_statements: list[StatementCandidate] = []
    for mention in persisted_mentions:
        if mention.relevance_score < min_score:
            continue
        # Find the matching politician config for this mention.
        pol_cfg = next(
            (p for p in politicians if p.id == mention.politician_id), None
        )
        if pol_cfg is None:
            continue
        # extract_statements accepts utils.config.PoliticianConfig directly.
        candidates = extract_statements(
            body=extracted.body,
            politician=pol_cfg,
            article_id=article_id,
        )
        for candidate in candidates:
            try:
                insert_statement_candidate(conn, candidate)
                all_statements.append(candidate)
            except Exception:
                logger.exception(
                    "Failed to persist statement candidate %s.",
                    candidate.statement_id,
                )

    # ------------------------------------------------------------------
    # 8. Tag topics.
    # ------------------------------------------------------------------
    matched_topics = tag_article(
        text=f"{extracted.metadata.title} {extracted.body}",
        topics=topics,
    )

    logger.info(
        "Ingested article %s: %d words, %d mention(s), %d statement(s), %d topic(s).",
        article_id,
        extracted.word_count,
        len(persisted_mentions),
        len(all_statements),
        len(matched_topics),
    )

    return ArticleIngestResult(
        article_id=article_id,
        raw_article=raw,
        extracted_article=extracted,
        mentions=persisted_mentions,
        statements=all_statements,
        topics=matched_topics,
        mentions_count=len(persisted_mentions),
        statements_count=len(all_statements),
    )
