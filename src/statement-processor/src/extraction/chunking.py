"""
extraction.chunking
===================
Article chunking utilities for the stance extraction pipeline.

Some articles are longer than a single LLM context window can handle
comfortably.  This module provides a simple character-count-based chunking
strategy that:

- returns the article as a single chunk when it is short enough,
- splits long articles on paragraph or sentence boundaries where possible,
- preserves article identity and chunk provenance across all chunks.

Usage
-----
    from extraction.chunking import chunk_article
    from extraction.models import ArticleInput

    chunks = chunk_article(article, max_chars=6_000)
    # → list[ChunkInput]
"""

from __future__ import annotations

import re
from typing import Optional

from .models import ArticleInput, ChunkInput

# ---------------------------------------------------------------------------
# Sentence / paragraph boundary patterns
# ---------------------------------------------------------------------------

# Prefer splitting on double-newlines (paragraph boundaries) first.
_PARAGRAPH_SEP = re.compile(r"\n\n+")

# Fallback: split on sentence-ending punctuation followed by whitespace.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _split_on_paragraphs(text: str) -> list[str]:
    """Split *text* into paragraph-sized segments."""
    return [p.strip() for p in _PARAGRAPH_SEP.split(text) if p.strip()]


def _split_on_sentences(text: str) -> list[str]:
    """Split *text* into sentence-sized segments."""
    return [s.strip() for s in _SENTENCE_END.split(text) if s.strip()]


def _pack_segments(segments: list[str], max_chars: int) -> list[str]:
    """Pack *segments* into chunks that do not exceed *max_chars*.

    Segments are joined with double newlines.  A single segment that
    exceeds *max_chars* is included as its own chunk (hard truncation is
    avoided so the LLM sees the complete segment even if it is long).

    Parameters
    ----------
    segments:
        Ordered list of text segments to pack.
    max_chars:
        Target maximum character count per chunk.

    Returns
    -------
    list[str]
        Ordered list of chunk text strings.
    """
    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    for seg in segments:
        seg_len = len(seg)
        # +2 accounts for the "\n\n" separator we add when joining.
        if current_parts and (current_len + 2 + seg_len) > max_chars:
            chunks.append("\n\n".join(current_parts))
            current_parts = [seg]
            current_len = seg_len
        else:
            current_parts.append(seg)
            current_len += (2 if current_parts else 0) + seg_len

    if current_parts:
        chunks.append("\n\n".join(current_parts))

    return chunks


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def chunk_article(
    article: ArticleInput,
    max_chars: int = 6_000,
) -> list[ChunkInput]:
    """Split *article* into one or more :class:`~extraction.models.ChunkInput`
    objects.

    Chunking strategy (in order of preference):

    1. If the article text fits within *max_chars*, return a single chunk.
    2. Split on paragraph boundaries (double newlines) and pack segments.
    3. If any resulting paragraph-chunk still exceeds *max_chars*, fall back
       to sentence-level splitting for that paragraph.

    Every returned chunk carries full article provenance (``doc_id``,
    ``title``, ``date``, ``link``) and chunk-position metadata
    (``chunk_index``, ``chunk_total``).

    Parameters
    ----------
    article:
        The source article to chunk.
    max_chars:
        Maximum character count per chunk.  Defaults to 6 000 characters
        (roughly 1 500 tokens, well within most model limits).

    Returns
    -------
    list[ChunkInput]
        Ordered list of chunk inputs.  Always contains at least one chunk.
    """
    text = article.text or ""

    # Fast path: article fits in one chunk.
    if len(text) <= max_chars:
        return [
            ChunkInput(
                doc_id=article.doc_id,
                chunk_index=0,
                chunk_total=1,
                chunk_text=text,
                title=article.title,
                date=article.date,
                link=article.link,
            )
        ]

    # Split on paragraphs first.
    paragraphs = _split_on_paragraphs(text) or [text]
    raw_chunks = _pack_segments(paragraphs, max_chars)

    # For any chunk that still exceeds max_chars, do a finer sentence split.
    final_texts: list[str] = []
    for chunk_text in raw_chunks:
        if len(chunk_text) > max_chars:
            sentences = _split_on_sentences(chunk_text) or [chunk_text]
            final_texts.extend(_pack_segments(sentences, max_chars))
        else:
            final_texts.append(chunk_text)

    # Build ChunkInput objects with correct provenance.
    chunk_total = len(final_texts)
    return [
        ChunkInput(
            doc_id=article.doc_id,
            chunk_index=idx,
            chunk_total=chunk_total,
            chunk_text=chunk_text,
            title=article.title,
            date=article.date,
            link=article.link,
        )
        for idx, chunk_text in enumerate(final_texts)
    ]
