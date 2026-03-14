"""
extraction.batch_requests
=========================
Convert triage-positive articles into OpenAI Batch API JSONL request files
for full stance extraction.

This module is the Batch-API counterpart to the synchronous
:func:`~extraction.extractor.extract_single_article` function.  Instead of
calling the model immediately, it produces a JSONL file that can be submitted
to the OpenAI Batch API for offline processing.

Each line of the output file is an OpenAI Batch API request::

    {
      "custom_id": "extraction-<doc_id>-chunk<idx>of<total>",
      "method": "POST",
      "url": "/v1/chat/completions",
      "body": {
        "model": "gpt-4o-mini",
        "temperature": 0.0,
        "messages": [
          {"role": "system", "content": "<extraction system prompt>"},
          {"role": "user",   "content": "<rendered article prompt>"}
        ]
      }
    }

The ``custom_id`` encodes the article ``doc_id`` and chunk index so that the
ingestion stage can reconstruct provenance without needing the original JSONL.

Long articles are chunked using the existing
:func:`~extraction.chunking.chunk_article` logic so that no single request
exceeds the context window.

Usage
-----
    from extraction.batch_requests import (
        build_extraction_batch_requests,
        write_extraction_batch_jsonl,
    )
    from extraction.models import ArticleInput, ExtractionConfig
    from pathlib import Path

    articles = [ArticleInput(doc_id="art-001", text="…")]
    config = ExtractionConfig(model_name="gpt-4o-mini")

    requests = build_extraction_batch_requests(articles, config)
    paths = write_extraction_batch_jsonl(
        requests,
        output_dir=Path("data/batch_artifacts/extraction/run-001"),
    )
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from .chunking import chunk_article
from .models import ArticleInput, ExtractionConfig
from .prompt_loader import load_prompt

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CUSTOM_ID_PREFIX: str = "extraction-"
_BATCH_API_URL: str = "/v1/chat/completions"
_BATCH_API_METHOD: str = "POST"


# ---------------------------------------------------------------------------
# Request building
# ---------------------------------------------------------------------------


def _make_extraction_request_id(doc_id: str, chunk_index: int, chunk_total: int) -> str:
    """Return a deterministic Batch API ``custom_id`` for one extraction chunk.

    Format: ``extraction-<doc_id>-chunk<idx>of<total>``

    Parameters
    ----------
    doc_id:
        Unique article identifier.
    chunk_index:
        0-based chunk index.
    chunk_total:
        Total number of chunks for this article.

    Returns
    -------
    str
        Deterministic request ID.
    """
    return f"{_CUSTOM_ID_PREFIX}{doc_id}-chunk{chunk_index}of{chunk_total}"


def build_extraction_requests_for_article(
    article: ArticleInput,
    config: ExtractionConfig,
    prompt_path: Optional[Path | str] = None,
) -> list[dict[str, Any]]:
    """Build Batch API request dicts for one article (one per chunk).

    Parameters
    ----------
    article:
        The article to process.
    config:
        Extraction configuration (model, chunk size, temperature).
    prompt_path:
        Optional override path to the prompt markdown file.

    Returns
    -------
    list[dict[str, Any]]
        One request dict per chunk.  Single-chunk articles produce a
        one-element list.
    """
    chunks = chunk_article(article, max_chars=config.max_chunk_chars)
    requests: list[dict[str, Any]] = []

    for chunk in chunks:
        system_msg, user_msg = load_prompt(
            doc_id=chunk.doc_id,
            article_text=chunk.chunk_text,
            prompt_path=prompt_path,
        )
        custom_id = _make_extraction_request_id(
            chunk.doc_id, chunk.chunk_index, chunk.chunk_total
        )
        requests.append(
            {
                "custom_id": custom_id,
                "method": _BATCH_API_METHOD,
                "url": _BATCH_API_URL,
                "body": {
                    "model": config.model_name,
                    "temperature": config.temperature,
                    "messages": [
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": user_msg},
                    ],
                },
            }
        )

    return requests


def build_extraction_batch_requests(
    articles: list[ArticleInput],
    config: ExtractionConfig | None = None,
    prompt_path: Optional[Path | str] = None,
) -> list[dict[str, Any]]:
    """Convert a list of articles into Batch API extraction request dicts.

    Long articles are split into chunks by the existing chunking logic.
    Each chunk becomes one Batch API request.

    Parameters
    ----------
    articles:
        Triage-positive articles to prepare for full extraction.
    config:
        Extraction configuration.  Defaults to :class:`ExtractionConfig`
        with default values.
    prompt_path:
        Optional override for the prompt template path.

    Returns
    -------
    list[dict[str, Any]]
        One request dict per article chunk, in article order.
    """
    cfg = config or ExtractionConfig()
    all_requests: list[dict[str, Any]] = []
    for article in articles:
        all_requests.extend(
            build_extraction_requests_for_article(article, cfg, prompt_path=prompt_path)
        )
    return all_requests


# ---------------------------------------------------------------------------
# JSONL writing
# ---------------------------------------------------------------------------


def write_extraction_batch_jsonl(
    requests: list[dict[str, Any]],
    output_dir: Path | str,
    batch_size: int | None = None,
) -> list[Path]:
    """Write extraction batch requests to JSONL file(s) in *output_dir*.

    If the number of requests exceeds *batch_size*, the output is split
    across multiple numbered files.  A single file is always named
    ``batch_input.jsonl``.

    Parameters
    ----------
    requests:
        List of Batch API request dicts.
    output_dir:
        Directory where the JSONL file(s) will be written.  Created if it
        does not exist.
    batch_size:
        Maximum number of requests per file.  ``None`` writes all to one
        file.

    Returns
    -------
    list[Path]
        Absolute paths to the written JSONL files, one per chunk.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    if not requests:
        return []

    chunks: list[list[dict[str, Any]]]
    if batch_size is None or len(requests) <= batch_size:
        chunks = [requests]
    else:
        chunks = [
            requests[i : i + batch_size]
            for i in range(0, len(requests), batch_size)
        ]

    written: list[Path] = []
    for idx, chunk in enumerate(chunks):
        filename = "batch_input.jsonl" if len(chunks) == 1 else f"batch_input_{idx:03d}.jsonl"
        path = out / filename
        with path.open("w", encoding="utf-8") as fh:
            for req in chunk:
                fh.write(json.dumps(req, ensure_ascii=False) + "\n")
        written.append(path.resolve())

    return written
