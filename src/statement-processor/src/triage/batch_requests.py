"""
triage.batch_requests
=====================
Convert triage candidate articles into OpenAI Batch API JSONL request files.

The OpenAI Batch API accepts a JSONL file where each line is a separate chat
completion request.  This module converts :class:`~triage.models.TriageArticle`
objects into that format and writes the resulting file locally for inspection
before submission.

Each request line has the following structure::

    {
      "custom_id": "triage-<doc_id>",
      "method": "POST",
      "url": "/v1/chat/completions",
      "body": {
        "model": "gpt-4o-mini",
        "temperature": 0.0,
        "messages": [
          {"role": "system", "content": "<triage system prompt>"},
          {"role": "user",   "content": "<rendered user prompt>"}
        ]
      }
    }

The ``custom_id`` is deterministic: ``"triage-{doc_id}"``.  The ingestion
stage uses this ID to map responses back to the originating article.

Usage
-----
    from triage.batch_requests import build_triage_batch_requests, write_triage_batch_jsonl
    from triage.models import TriageArticle, TriageConfig

    articles = [TriageArticle(doc_id="art-001", title="…", text="…")]
    config = TriageConfig(model_name="gpt-4o-mini")

    requests = build_triage_batch_requests(articles, config)
    paths = write_triage_batch_jsonl(requests, output_dir=Path("data/batch_artifacts/triage/run-001"))
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import TriageArticle, TriageConfig
from .prompt import TRIAGE_SYSTEM, render_triage_user_prompt

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CUSTOM_ID_PREFIX: str = "triage-"
_BATCH_API_URL: str = "/v1/chat/completions"
_BATCH_API_METHOD: str = "POST"

# ---------------------------------------------------------------------------
# Request building
# ---------------------------------------------------------------------------


def _make_request_id(doc_id: str) -> str:
    """Return the deterministic Batch API ``custom_id`` for *doc_id*.

    The ID format is ``triage-<doc_id>``.  If *doc_id* itself contains
    characters that are not safe in JSON string values they are preserved
    as-is because the Batch API ``custom_id`` accepts arbitrary strings.

    Parameters
    ----------
    doc_id:
        Unique article identifier.

    Returns
    -------
    str
        Deterministic request ID.
    """
    return f"{_CUSTOM_ID_PREFIX}{doc_id}"


def _truncate_text(text: str, max_chars: int) -> str:
    """Truncate *text* to at most *max_chars* characters.

    If truncation occurs a marker is appended so that the model knows the
    article was cut short.

    Parameters
    ----------
    text:
        The full article text.
    max_chars:
        Maximum number of characters to retain.

    Returns
    -------
    str
        Truncated (or original) text.
    """
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n[… article truncated for triage …]"


def build_triage_request(
    article: TriageArticle,
    config: TriageConfig,
) -> dict[str, Any]:
    """Build a single Batch API request dict for *article*.

    Parameters
    ----------
    article:
        The article to classify.
    config:
        Triage configuration (model, max chars, temperature).

    Returns
    -------
    dict[str, Any]
        A JSONL-serialisable request dict ready for the Batch API.
    """
    truncated_text = _truncate_text(article.text, config.max_article_chars)
    user_prompt = render_triage_user_prompt(
        doc_id=article.doc_id,
        title=article.title or "",
        article_text=truncated_text,
    )
    return {
        "custom_id": _make_request_id(article.doc_id),
        "method": _BATCH_API_METHOD,
        "url": _BATCH_API_URL,
        "body": {
            "model": config.model_name,
            "temperature": config.temperature,
            "messages": [
                {"role": "system", "content": TRIAGE_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
        },
    }


def build_triage_batch_requests(
    articles: list[TriageArticle],
    config: TriageConfig | None = None,
) -> list[dict[str, Any]]:
    """Convert a list of articles into Batch API request dicts.

    Parameters
    ----------
    articles:
        Articles to classify.
    config:
        Triage configuration.  Defaults to :class:`~triage.models.TriageConfig`
        with default values.

    Returns
    -------
    list[dict[str, Any]]
        One request dict per article, in the same order as *articles*.
    """
    cfg = config or TriageConfig()
    return [build_triage_request(article, cfg) for article in articles]


# ---------------------------------------------------------------------------
# JSONL writing
# ---------------------------------------------------------------------------


def write_triage_batch_jsonl(
    requests: list[dict[str, Any]],
    output_dir: Path | str,
    batch_size: int | None = None,
) -> list[Path]:
    """Write triage batch requests to JSONL file(s) in *output_dir*.

    If the number of requests exceeds *batch_size*, the output is split
    across multiple numbered files (``batch_input_000.jsonl``,
    ``batch_input_001.jsonl``, …).  A single file is always named
    ``batch_input.jsonl``.

    Parameters
    ----------
    requests:
        List of Batch API request dicts (from
        :func:`build_triage_batch_requests`).
    output_dir:
        Directory where the JSONL file(s) will be written.  Created if it
        does not exist.
    batch_size:
        Maximum number of requests per file.  ``None`` writes all requests
        to a single file.

    Returns
    -------
    list[Path]
        Absolute paths to the written JSONL files, one per chunk.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    if not requests:
        return []

    # Chunk the requests.
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
        if len(chunks) == 1:
            filename = "batch_input.jsonl"
        else:
            filename = f"batch_input_{idx:03d}.jsonl"
        path = out / filename
        with path.open("w", encoding="utf-8") as fh:
            for req in chunk:
                fh.write(json.dumps(req, ensure_ascii=False) + "\n")
        written.append(path.resolve())

    return written
