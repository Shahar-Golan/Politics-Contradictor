"""
test_bulk_pipeline
==================
Fixture-based and mock-based tests for the bulk Option-A pipeline.

Coverage:
- triage.models: TriageResult.is_positive, TriageBatchIngestionResult properties
- triage.prompt: TRIAGE_SYSTEM non-empty, render_triage_user_prompt renders correctly
- triage.batch_requests: build_triage_batch_requests preserves provenance and format
- triage.batch_requests: write_triage_batch_jsonl writes JSONL with correct structure
- triage.batch_requests: chunked output when batch_size is exceeded
- triage.batch_ingest: ingest_triage_batch_output classifies positives/negatives
- triage.batch_ingest: malformed triage responses are handled as parse errors
- triage.batch_ingest: failed batch requests are classified as failed
- extraction.batch_requests: build_extraction_batch_requests preserves provenance
- extraction.batch_requests: multi-chunk articles produce multiple requests
- extraction.batch_requests: write_extraction_batch_jsonl writes JSONL correctly
- extraction.batch_ingest: ingest_extraction_batch_output stores raw candidate outputs
- extraction.batch_ingest: malformed extraction responses are handled as parse errors
- extraction.batch_ingest: failed extraction requests are classified correctly
- pipeline.artifacts: resolve_run_dir creates directory and returns Path
- pipeline.artifacts: write_jsonl_artifact writes valid JSONL
- pipeline.artifacts: write_summary writes valid JSON
- Only triage-positive articles are included in extraction batch preparation
- Rerunning batch ingestion on same input is idempotent
"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# ── Add src/ to sys.path ──────────────────────────────────────────────────
_SRC_DIR = Path(__file__).parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from extraction.batch_ingest import ExtractionBatchIngestionResult, ingest_extraction_batch_output
from extraction.batch_requests import (
    build_extraction_batch_requests,
    build_extraction_requests_for_article,
    write_extraction_batch_jsonl,
)
from extraction.models import ArticleInput, ExtractionConfig
from pipeline.artifacts import resolve_run_dir, write_artifact, write_jsonl_artifact, write_summary
from triage.batch_ingest import ingest_triage_batch_output
from triage.batch_requests import (
    build_triage_batch_requests,
    build_triage_request,
    write_triage_batch_jsonl,
)
from triage.models import (
    TriageArticle,
    TriageBatchIngestionResult,
    TriageConfig,
    TriageDecision,
    TriageResult,
)
from triage.prompt import TRIAGE_SYSTEM, render_triage_user_prompt

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_triage_article(
    doc_id: str = "art-001",
    title: str = "Biden signs climate bill",
    text: str = "President Biden signed the Climate Act on Wednesday. The bill includes $500 billion in clean energy investment.",
    date: str = "2024-03-01",
    link: str = "https://example.com/article",
    matched_politician: str = "Biden",
) -> TriageArticle:
    return TriageArticle(
        doc_id=doc_id,
        title=title,
        text=text,
        date=date,
        link=link,
        matched_politician=matched_politician,
    )


def _make_article_input(
    doc_id: str = "art-001",
    text: str = "President Biden said 'We will fix healthcare.' " * 5,
    title: str = "Biden on Healthcare",
    date: str = "2025-01-15",
    link: str = "https://example.com/article",
) -> ArticleInput:
    return ArticleInput(doc_id=doc_id, text=text, title=title, date=date, link=link)


def _make_triage_result(
    doc_id: str = "art-001",
    advance: bool = True,
    failed: bool = False,
    parse_error: str | None = None,
) -> TriageResult:
    decision = (
        TriageDecision(
            has_stance_statement=advance,
            has_policy_position=advance,
            has_politician_action=False,
            has_contradiction_signal=False,
            advance=advance,
            rationale="Test rationale",
        )
        if not failed and parse_error is None
        else None
    )
    return TriageResult(
        doc_id=doc_id,
        title=f"Title {doc_id}",
        link=None,
        date=None,
        matched_politician="Biden",
        request_id=f"triage-{doc_id}",
        decision=decision,
        raw_response="{}" if not failed else None,
        parse_error=parse_error,
        failed=failed,
    )


def _make_triage_batch_output_line(
    custom_id: str,
    advance: bool = True,
    failed: bool = False,
    status_code: int = 200,
) -> str:
    """Build a Batch API output line as JSON string."""
    if failed:
        return json.dumps(
            {
                "id": f"batch-{custom_id}",
                "custom_id": custom_id,
                "response": None,
                "error": {"code": "server_error", "message": "Internal error"},
            }
        )
    content = json.dumps(
        {
            "has_stance_statement": advance,
            "has_policy_position": advance,
            "has_politician_action": False,
            "has_contradiction_signal": False,
            "advance": advance,
            "rationale": "Test rationale.",
        }
    )
    return json.dumps(
        {
            "id": f"batch-{custom_id}",
            "custom_id": custom_id,
            "response": {
                "status_code": status_code,
                "body": {
                    "choices": [{"message": {"content": content}}]
                },
            },
            "error": None,
        }
    )


def _make_extraction_batch_output_line(
    doc_id: str,
    chunk_index: int = 0,
    chunk_total: int = 1,
    events: list[dict[str, Any]] | None = None,
    failed: bool = False,
) -> str:
    """Build an extraction Batch API output line as JSON string."""
    custom_id = f"extraction-{doc_id}-chunk{chunk_index}of{chunk_total}"
    if failed:
        return json.dumps(
            {
                "id": f"batch-{custom_id}",
                "custom_id": custom_id,
                "response": None,
                "error": {"code": "server_error", "message": "Internal error"},
            }
        )
    stance_events = events if events is not None else [
        {
            "politician": "Joe Biden",
            "topic": "climate",
            "normalized_proposition": "Biden supports clean energy investment.",
            "stance_direction": "support",
            "stance_mode": "action",
            "evidence_role": "inferred_from_action",
            "confidence": 0.9,
        }
    ]
    content = json.dumps({"doc_id": doc_id, "stance_events": stance_events})
    return json.dumps(
        {
            "id": f"batch-{custom_id}",
            "custom_id": custom_id,
            "response": {
                "status_code": 200,
                "body": {
                    "model": "gpt-4o-mini",
                    "choices": [{"message": {"content": content}}],
                },
            },
            "error": None,
        }
    )


# ===========================================================================
# triage.prompt
# ===========================================================================


class TestTriagePrompt:
    def test_system_prompt_non_empty(self) -> None:
        assert TRIAGE_SYSTEM
        assert "triage" in TRIAGE_SYSTEM.lower() or "classifier" in TRIAGE_SYSTEM.lower()

    def test_render_user_prompt_contains_doc_id(self) -> None:
        rendered = render_triage_user_prompt(
            doc_id="art-001",
            title="Test Title",
            article_text="Some text.",
        )
        assert "art-001" in rendered

    def test_render_user_prompt_contains_title(self) -> None:
        rendered = render_triage_user_prompt(
            doc_id="art-001",
            title="Biden signs climate bill",
            article_text="Some text.",
        )
        assert "Biden signs climate bill" in rendered

    def test_render_user_prompt_contains_required_question_keys(self) -> None:
        rendered = render_triage_user_prompt("a", "b", "c")
        for key in [
            "has_stance_statement",
            "has_policy_position",
            "has_politician_action",
            "has_contradiction_signal",
            "advance",
        ]:
            assert key in rendered


# ===========================================================================
# triage.models
# ===========================================================================


class TestTriageModels:
    def test_triage_result_is_positive_when_advance_true(self) -> None:
        result = _make_triage_result(advance=True)
        assert result.is_positive is True

    def test_triage_result_not_positive_when_advance_false(self) -> None:
        result = _make_triage_result(advance=False)
        assert result.is_positive is False

    def test_triage_result_not_positive_when_failed(self) -> None:
        result = _make_triage_result(failed=True)
        assert result.is_positive is False

    def test_triage_result_not_positive_when_parse_error(self) -> None:
        result = _make_triage_result(parse_error="some parse error")
        assert result.is_positive is False

    def test_batch_ingestion_result_positives(self) -> None:
        r1 = _make_triage_result("art-001", advance=True)
        r2 = _make_triage_result("art-002", advance=False)
        r3 = _make_triage_result("art-003", failed=True)
        result = TriageBatchIngestionResult(results=[r1, r2, r3])
        assert len(result.positives) == 1
        assert result.positives[0].doc_id == "art-001"

    def test_batch_ingestion_result_negatives(self) -> None:
        r1 = _make_triage_result("art-001", advance=True)
        r2 = _make_triage_result("art-002", advance=False)
        result = TriageBatchIngestionResult(results=[r1, r2])
        assert len(result.negatives) == 1
        assert result.negatives[0].doc_id == "art-002"

    def test_batch_ingestion_result_failed(self) -> None:
        r1 = _make_triage_result("art-001", advance=True)
        r2 = _make_triage_result("art-002", failed=True)
        result = TriageBatchIngestionResult(results=[r1, r2])
        assert len(result.failed) == 1
        assert result.failed[0].doc_id == "art-002"

    def test_batch_ingestion_result_parse_errors(self) -> None:
        r1 = _make_triage_result("art-001", advance=True)
        r2 = _make_triage_result("art-002", parse_error="json error")
        result = TriageBatchIngestionResult(results=[r1, r2])
        assert len(result.parse_errors) == 1
        assert result.parse_errors[0].doc_id == "art-002"

    def test_batch_ingestion_result_retry_candidates(self) -> None:
        r1 = _make_triage_result("art-001", advance=True)
        r2 = _make_triage_result("art-002", failed=True)
        r3 = _make_triage_result("art-003", parse_error="err")
        result = TriageBatchIngestionResult(results=[r1, r2, r3])
        assert len(result.retry_candidates) == 2

    def test_summary_keys(self) -> None:
        result = TriageBatchIngestionResult(results=[_make_triage_result()])
        s = result.summary()
        for key in ["total", "positives", "negatives", "failed", "parse_errors"]:
            assert key in s


# ===========================================================================
# triage.batch_requests
# ===========================================================================


class TestTriageBatchRequests:
    def test_build_triage_request_preserves_doc_id(self) -> None:
        article = _make_triage_article(doc_id="my-article-123")
        req = build_triage_request(article, TriageConfig())
        assert req["custom_id"] == "triage-my-article-123"

    def test_build_triage_request_structure(self) -> None:
        req = build_triage_request(_make_triage_article(), TriageConfig())
        assert req["method"] == "POST"
        assert req["url"] == "/v1/chat/completions"
        assert "body" in req
        body = req["body"]
        assert "model" in body
        assert "messages" in body
        messages = body["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_build_triage_request_text_truncation(self) -> None:
        long_text = "X" * 10_000
        article = _make_triage_article(text=long_text)
        config = TriageConfig(max_article_chars=500)
        req = build_triage_request(article, config)
        user_content = req["body"]["messages"][1]["content"]
        # The user content should contain truncation marker.
        assert "truncated" in user_content

    def test_build_triage_batch_requests_count(self) -> None:
        articles = [_make_triage_article(doc_id=f"art-{i:03d}") for i in range(5)]
        reqs = build_triage_batch_requests(articles)
        assert len(reqs) == 5

    def test_build_triage_batch_requests_provenance(self) -> None:
        articles = [_make_triage_article(doc_id="test-doc")]
        reqs = build_triage_batch_requests(articles)
        assert reqs[0]["custom_id"] == "triage-test-doc"

    def test_write_triage_batch_jsonl_single_file(self, tmp_path: Path) -> None:
        articles = [_make_triage_article(doc_id=f"art-{i}") for i in range(3)]
        reqs = build_triage_batch_requests(articles)
        paths = write_triage_batch_jsonl(reqs, output_dir=tmp_path)
        assert len(paths) == 1
        assert paths[0].name == "batch_input.jsonl"

    def test_write_triage_batch_jsonl_content_is_valid_jsonl(self, tmp_path: Path) -> None:
        articles = [_make_triage_article(doc_id=f"art-{i}") for i in range(3)]
        reqs = build_triage_batch_requests(articles)
        paths = write_triage_batch_jsonl(reqs, output_dir=tmp_path)
        lines = paths[0].read_text().splitlines()
        assert len(lines) == 3
        for line in lines:
            parsed = json.loads(line)
            assert "custom_id" in parsed

    def test_write_triage_batch_jsonl_chunked_output(self, tmp_path: Path) -> None:
        articles = [_make_triage_article(doc_id=f"art-{i:04d}") for i in range(25)]
        reqs = build_triage_batch_requests(articles)
        paths = write_triage_batch_jsonl(reqs, output_dir=tmp_path, batch_size=10)
        assert len(paths) == 3  # 25 / 10 → 3 files

    def test_write_triage_batch_jsonl_empty_input(self, tmp_path: Path) -> None:
        paths = write_triage_batch_jsonl([], output_dir=tmp_path)
        assert paths == []


# ===========================================================================
# triage.batch_ingest
# ===========================================================================


class TestTriageBatchIngest:
    def _write_output_file(self, lines: list[str], tmp_path: Path) -> Path:
        p = tmp_path / "batch_output.jsonl"
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return p

    def test_ingest_positive_result(self, tmp_path: Path) -> None:
        line = _make_triage_batch_output_line("triage-art-001", advance=True)
        output = self._write_output_file([line], tmp_path)
        result = ingest_triage_batch_output(output_jsonl=output)
        assert len(result.results) == 1
        assert result.results[0].is_positive is True
        assert result.results[0].doc_id == "art-001"

    def test_ingest_negative_result(self, tmp_path: Path) -> None:
        line = _make_triage_batch_output_line("triage-art-002", advance=False)
        output = self._write_output_file([line], tmp_path)
        result = ingest_triage_batch_output(output_jsonl=output)
        assert len(result.negatives) == 1
        assert result.negatives[0].doc_id == "art-002"

    def test_ingest_failed_request(self, tmp_path: Path) -> None:
        line = _make_triage_batch_output_line("triage-art-003", failed=True)
        output = self._write_output_file([line], tmp_path)
        result = ingest_triage_batch_output(output_jsonl=output)
        assert len(result.failed) == 1
        assert result.failed[0].failed is True

    def test_ingest_malformed_response(self, tmp_path: Path) -> None:
        malformed_content = "this is not JSON"
        line = json.dumps(
            {
                "id": "batch-x",
                "custom_id": "triage-art-004",
                "response": {
                    "status_code": 200,
                    "body": {
                        "choices": [{"message": {"content": malformed_content}}]
                    },
                },
                "error": None,
            }
        )
        output = self._write_output_file([line], tmp_path)
        result = ingest_triage_batch_output(output_jsonl=output)
        assert len(result.parse_errors) == 1

    def test_ingest_missing_required_keys(self, tmp_path: Path) -> None:
        incomplete = json.dumps({"advance": True})  # missing other required keys
        line = json.dumps(
            {
                "id": "batch-y",
                "custom_id": "triage-art-005",
                "response": {
                    "status_code": 200,
                    "body": {
                        "choices": [{"message": {"content": incomplete}}]
                    },
                },
                "error": None,
            }
        )
        output = self._write_output_file([line], tmp_path)
        result = ingest_triage_batch_output(output_jsonl=output)
        assert len(result.parse_errors) == 1

    def test_ingest_mixed_results(self, tmp_path: Path) -> None:
        lines = [
            _make_triage_batch_output_line("triage-art-001", advance=True),
            _make_triage_batch_output_line("triage-art-002", advance=False),
            _make_triage_batch_output_line("triage-art-003", failed=True),
        ]
        output = self._write_output_file(lines, tmp_path)
        result = ingest_triage_batch_output(output_jsonl=output)
        assert len(result.positives) == 1
        assert len(result.negatives) == 1
        assert len(result.failed) == 1

    def test_ingest_raises_on_missing_output_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            ingest_triage_batch_output(output_jsonl=tmp_path / "nonexistent.jsonl")

    def test_ingest_non_200_status_treated_as_failure(self, tmp_path: Path) -> None:
        line = _make_triage_batch_output_line("triage-art-006", status_code=500)
        output = self._write_output_file([line], tmp_path)
        result = ingest_triage_batch_output(output_jsonl=output)
        assert len(result.failed) == 1

    def test_ingest_idempotent_on_same_file(self, tmp_path: Path) -> None:
        """Re-running ingestion on the same file should produce the same results."""
        lines = [
            _make_triage_batch_output_line("triage-art-001", advance=True),
            _make_triage_batch_output_line("triage-art-002", advance=False),
        ]
        output = self._write_output_file(lines, tmp_path)
        result1 = ingest_triage_batch_output(output_jsonl=output)
        result2 = ingest_triage_batch_output(output_jsonl=output)
        assert len(result1.results) == len(result2.results)
        assert len(result1.positives) == len(result2.positives)

    def test_ingest_with_provenance(self, tmp_path: Path) -> None:
        """Provenance supplied via the provenance parameter is applied to results."""
        line = _make_triage_batch_output_line("triage-art-001", advance=True)
        output = self._write_output_file([line], tmp_path)
        provenance = {
            "triage-art-001": {
                "doc_id": "art-001",
                "title": "Test Title",
                "link": "https://example.com",
                "date": "2024-01-01",
                "matched_politician": "Biden",
            }
        }
        result = ingest_triage_batch_output(output_jsonl=output, provenance=provenance)
        assert result.results[0].title == "Test Title"
        assert result.results[0].matched_politician == "Biden"


# ===========================================================================
# extraction.batch_requests
# ===========================================================================


class TestExtractionBatchRequests:
    def test_build_requests_single_chunk(self) -> None:
        article = _make_article_input(text="Short text for testing. " * 5)
        reqs = build_extraction_requests_for_article(article, ExtractionConfig())
        assert len(reqs) == 1
        assert reqs[0]["custom_id"] == "extraction-art-001-chunk0of1"

    def test_build_requests_multi_chunk(self) -> None:
        # Force chunking: text > max_chunk_chars
        article = _make_article_input(text=("Word " * 300) + "\n\n" + ("Word " * 300))
        config = ExtractionConfig(max_chunk_chars=500)
        reqs = build_extraction_requests_for_article(article, config)
        assert len(reqs) > 1
        # All custom_ids should reference the same doc_id.
        for req in reqs:
            assert req["custom_id"].startswith("extraction-art-001-")

    def test_build_requests_preserves_doc_id_in_prompt(self) -> None:
        article = _make_article_input(doc_id="unique-doc-456")
        reqs = build_extraction_requests_for_article(article, ExtractionConfig())
        user_content = reqs[0]["body"]["messages"][1]["content"]
        assert "unique-doc-456" in user_content

    def test_build_extraction_batch_requests_count(self) -> None:
        articles = [_make_article_input(doc_id=f"art-{i}") for i in range(4)]
        reqs = build_extraction_batch_requests(articles)
        # Each short article → 1 chunk; total = 4
        assert len(reqs) == 4

    def test_only_positives_in_extraction_batch(self) -> None:
        """Simulate that only triage-positive articles are used."""
        positive_ids = {"art-001", "art-003"}
        all_articles = [_make_article_input(doc_id=f"art-{i:03d}") for i in range(5)]
        positive_articles = [a for a in all_articles if a.doc_id in positive_ids]
        reqs = build_extraction_batch_requests(positive_articles)
        doc_ids_in_reqs = {
            req["custom_id"].split("-chunk")[0].removeprefix("extraction-")
            for req in reqs
        }
        assert doc_ids_in_reqs == positive_ids

    def test_write_extraction_batch_jsonl_single_file(self, tmp_path: Path) -> None:
        articles = [_make_article_input(doc_id=f"art-{i}") for i in range(3)]
        reqs = build_extraction_batch_requests(articles)
        paths = write_extraction_batch_jsonl(reqs, output_dir=tmp_path)
        assert len(paths) == 1
        assert paths[0].name == "batch_input.jsonl"

    def test_write_extraction_batch_jsonl_content_valid_jsonl(self, tmp_path: Path) -> None:
        articles = [_make_article_input(doc_id=f"art-{i}") for i in range(2)]
        reqs = build_extraction_batch_requests(articles)
        paths = write_extraction_batch_jsonl(reqs, output_dir=tmp_path)
        lines = paths[0].read_text().splitlines()
        assert len(lines) == 2
        for line in lines:
            parsed = json.loads(line)
            assert "custom_id" in parsed
            assert parsed["custom_id"].startswith("extraction-")

    def test_write_extraction_batch_jsonl_empty(self, tmp_path: Path) -> None:
        paths = write_extraction_batch_jsonl([], output_dir=tmp_path)
        assert paths == []


# ===========================================================================
# extraction.batch_ingest
# ===========================================================================


class TestExtractionBatchIngest:
    def _write_output_file(self, lines: list[str], tmp_path: Path) -> Path:
        p = tmp_path / "batch_output.jsonl"
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return p

    def test_ingest_valid_extraction_output(self, tmp_path: Path) -> None:
        line = _make_extraction_batch_output_line("art-001")
        output = self._write_output_file([line], tmp_path)
        result = ingest_extraction_batch_output(output_jsonl=output)
        assert len(result.raw_outputs) == 1
        assert len(result.candidate_events) == 1
        assert result.candidate_events[0].doc_id == "art-001"

    def test_ingest_preserves_provenance(self, tmp_path: Path) -> None:
        line = _make_extraction_batch_output_line("art-007")
        output = self._write_output_file([line], tmp_path)
        result = ingest_extraction_batch_output(output_jsonl=output)
        assert result.candidate_events[0].doc_id == "art-007"

    def test_ingest_failed_request_no_candidates(self, tmp_path: Path) -> None:
        line = _make_extraction_batch_output_line("art-002", failed=True)
        output = self._write_output_file([line], tmp_path)
        result = ingest_extraction_batch_output(output_jsonl=output)
        assert len(result.failed_requests) == 1
        assert len(result.candidate_events) == 0

    def test_ingest_malformed_response(self, tmp_path: Path) -> None:
        custom_id = "extraction-art-003-chunk0of1"
        malformed_line = json.dumps(
            {
                "id": "batch-x",
                "custom_id": custom_id,
                "response": {
                    "status_code": 200,
                    "body": {
                        "choices": [{"message": {"content": "not json at all"}}]
                    },
                },
                "error": None,
            }
        )
        output = self._write_output_file([malformed_line], tmp_path)
        result = ingest_extraction_batch_output(output_jsonl=output)
        assert len(result.parse_error_ids) == 1
        assert len(result.raw_outputs) == 1
        assert result.raw_outputs[0].parse_error is not None

    def test_ingest_zero_events_response(self, tmp_path: Path) -> None:
        line = _make_extraction_batch_output_line("art-004", events=[])
        output = self._write_output_file([line], tmp_path)
        result = ingest_extraction_batch_output(output_jsonl=output)
        assert len(result.candidate_events) == 0
        assert len(result.raw_outputs) == 1
        assert result.raw_outputs[0].parse_error is None

    def test_ingest_multi_chunk_article(self, tmp_path: Path) -> None:
        lines = [
            _make_extraction_batch_output_line("art-005", chunk_index=0, chunk_total=2),
            _make_extraction_batch_output_line("art-005", chunk_index=1, chunk_total=2),
        ]
        output = self._write_output_file(lines, tmp_path)
        result = ingest_extraction_batch_output(output_jsonl=output)
        assert len(result.raw_outputs) == 2
        assert len(result.candidate_events) == 2  # one event per chunk

    def test_ingest_raises_on_missing_output_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            ingest_extraction_batch_output(output_jsonl=tmp_path / "nonexistent.jsonl")

    def test_ingest_idempotent_on_same_file(self, tmp_path: Path) -> None:
        line = _make_extraction_batch_output_line("art-006")
        output = self._write_output_file([line], tmp_path)
        result1 = ingest_extraction_batch_output(output_jsonl=output)
        result2 = ingest_extraction_batch_output(output_jsonl=output)
        assert len(result1.candidate_events) == len(result2.candidate_events)
        assert len(result1.raw_outputs) == len(result2.raw_outputs)

    def test_ingest_summary_keys(self, tmp_path: Path) -> None:
        line = _make_extraction_batch_output_line("art-008")
        output = self._write_output_file([line], tmp_path)
        result = ingest_extraction_batch_output(output_jsonl=output)
        s = result.summary()
        for key in ["total_responses", "candidate_events", "failed_requests", "parse_errors"]:
            assert key in s

    def test_candidate_events_are_marked_untrusted(self, tmp_path: Path) -> None:
        """Candidate events should be in ExtractionBatchIngestionResult,
        not in a final validated table."""
        line = _make_extraction_batch_output_line("art-009")
        output = self._write_output_file([line], tmp_path)
        result = ingest_extraction_batch_output(output_jsonl=output)
        # The result should be an ExtractionBatchIngestionResult (not a validated output)
        assert isinstance(result, ExtractionBatchIngestionResult)
        # Events are in candidate_events, not any validated store
        assert hasattr(result, "candidate_events")


# ===========================================================================
# pipeline.artifacts
# ===========================================================================


class TestPipelineArtifacts:
    def test_resolve_run_dir_creates_directory(self, tmp_path: Path) -> None:
        run_dir = resolve_run_dir(tmp_path / "artifacts", run_id="test-001")
        assert run_dir.exists()
        assert run_dir.is_dir()

    def test_resolve_run_dir_uses_run_id(self, tmp_path: Path) -> None:
        run_dir = resolve_run_dir(tmp_path, run_id="my-run-123")
        assert run_dir.name == "my-run-123"

    def test_resolve_run_dir_auto_generates_id(self, tmp_path: Path) -> None:
        run_dir = resolve_run_dir(tmp_path)
        assert run_dir.exists()
        assert "run-" in run_dir.name

    def test_write_artifact_creates_valid_json(self, tmp_path: Path) -> None:
        data = {"key": "value", "count": 42}
        path = write_artifact(data, tmp_path / "test.json")
        assert path.exists()
        loaded = json.loads(path.read_text())
        assert loaded == data

    def test_write_jsonl_artifact_creates_valid_jsonl(self, tmp_path: Path) -> None:
        records = [{"doc_id": f"art-{i}", "score": i} for i in range(5)]
        path = write_jsonl_artifact(records, tmp_path / "test.jsonl")
        assert path.exists()
        lines = path.read_text().splitlines()
        assert len(lines) == 5
        for line in lines:
            json.loads(line)  # should not raise

    def test_write_summary_is_readable_json(self, tmp_path: Path) -> None:
        summary = {"stage": "test", "total": 100, "passed": 80}
        path = write_summary(summary, tmp_path / "summary.json")
        loaded = json.loads(path.read_text())
        assert loaded["stage"] == "test"

    def test_write_jsonl_artifact_empty_list(self, tmp_path: Path) -> None:
        path = write_jsonl_artifact([], tmp_path / "empty.jsonl")
        assert path.exists()
        assert path.read_text() == ""

    def test_write_artifact_creates_parent_dirs(self, tmp_path: Path) -> None:
        nested = tmp_path / "a" / "b" / "c" / "data.json"
        write_artifact({"x": 1}, nested)
        assert nested.exists()

    def test_artifact_location_is_predictable(self, tmp_path: Path) -> None:
        """Artifacts should be written to the expected sub-paths."""
        run_dir = resolve_run_dir(tmp_path / "triage", run_id="run-001")
        write_jsonl_artifact([{"doc_id": "art-001"}], run_dir / "selected_articles.jsonl")
        write_summary({"total": 1}, run_dir / "summary.json")
        assert (run_dir / "selected_articles.jsonl").exists()
        assert (run_dir / "summary.json").exists()
