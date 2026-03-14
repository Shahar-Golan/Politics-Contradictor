"""
test_extractor_fixtures
=======================
Fixture-based and mock-based tests for the LLM-based stance extractor.

All tests use mocks or fixture data – no real LLM API calls are made.

Coverage:
- extractor invocation over fixture/sample articles
- zero-event output case
- multi-event output case
- malformed JSON handling
- retry / failure logging behaviour
- provenance preservation (doc_id, title, link, date)
- chunking behaviour for long input
- prompt loading
- debug logger output
- ArticleInput → ExtractionResult data flow
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ── Add src/ to sys.path ──────────────────────────────────────────────────
_SRC_DIR = Path(__file__).parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from extraction.chunking import chunk_article
from extraction.client import LLMClient, LLMClientError, LLMTimeoutError
from extraction.debug_logger import DebugLogger, _raw_output_to_dict
from extraction.extractor import (
    _build_candidate,
    _parse_raw_response,
    extract_articles,
    extract_single_article,
)
from extraction.models import (
    ArticleInput,
    CandidateStanceEvent,
    ExtractionConfig,
    ExtractionResult,
    RawExtractionOutput,
)
from extraction.prompt_loader import load_prompt

# ---------------------------------------------------------------------------
# Fixture paths
# ---------------------------------------------------------------------------

_FIXTURES_DIR = Path(__file__).parent / "fixtures"
_VALID_DIR = _FIXTURES_DIR / "valid"
_INVALID_DIR = _FIXTURES_DIR / "invalid"


def _load_fixture(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------


def _make_article(
    doc_id: str = "test-001",
    text: str = "President Biden said 'We will fix healthcare.' The bill was introduced today. " * 5,
    title: str = "Biden on Healthcare",
    date: str = "2025-01-15",
    link: str = "https://example.com/article",
) -> ArticleInput:
    return ArticleInput(
        doc_id=doc_id, text=text, title=title, date=date, link=link
    )


def _make_config(
    max_retries: int = 1,
    max_chunk_chars: int = 6_000,
    debug_log_path: str | None = None,
) -> ExtractionConfig:
    return ExtractionConfig(
        model_name="gpt-4o-mini",
        max_retries=max_retries,
        max_chunk_chars=max_chunk_chars,
        debug_log_path=debug_log_path,
    )


def _make_mock_client(response: str) -> MagicMock:
    """Return a mock LLMClient whose complete() always returns *response*."""
    mock = MagicMock(spec=LLMClient)
    mock.complete.return_value = response
    return mock


def _make_mock_debug_logger() -> DebugLogger:
    """Return a DebugLogger with file I/O disabled."""
    return DebugLogger(enabled=False)


# ---------------------------------------------------------------------------
# Tests: prompt_loader
# ---------------------------------------------------------------------------


class TestPromptLoader:
    def test_load_prompt_returns_two_strings(self) -> None:
        system_msg, user_msg = load_prompt(
            doc_id="art-001",
            article_text="Some article text.",
        )
        assert isinstance(system_msg, str)
        assert isinstance(user_msg, str)
        assert len(system_msg) > 0
        assert len(user_msg) > 0

    def test_doc_id_is_substituted(self) -> None:
        _, user_msg = load_prompt(
            doc_id="unique-doc-42",
            article_text="Article body.",
        )
        assert "unique-doc-42" in user_msg

    def test_article_text_is_substituted(self) -> None:
        marker = "UNIQUE_MARKER_XYZ_123"
        _, user_msg = load_prompt(
            doc_id="art-001",
            article_text=marker,
        )
        assert marker in user_msg

    def test_placeholder_not_left_in_output(self) -> None:
        _, user_msg = load_prompt(
            doc_id="art-001",
            article_text="Some text.",
        )
        assert "{{doc_id}}" not in user_msg
        assert "{{article_text}}" not in user_msg

    def test_missing_prompt_file_raises_file_not_found(
        self, tmp_path: Path
    ) -> None:
        with pytest.raises(FileNotFoundError):
            load_prompt(
                doc_id="art-001",
                article_text="text",
                prompt_path=tmp_path / "does_not_exist.md",
            )


# ---------------------------------------------------------------------------
# Tests: chunking
# ---------------------------------------------------------------------------


class TestChunkArticle:
    def test_short_article_is_single_chunk(self) -> None:
        article = _make_article(text="Short text.")
        chunks = chunk_article(article, max_chars=6_000)
        assert len(chunks) == 1
        assert chunks[0].chunk_index == 0
        assert chunks[0].chunk_total == 1
        assert chunks[0].chunk_text == "Short text."

    def test_chunk_preserves_doc_id(self) -> None:
        article = _make_article(doc_id="prov-001", text="Short.")
        chunks = chunk_article(article, max_chars=6_000)
        for chunk in chunks:
            assert chunk.doc_id == "prov-001"

    def test_chunk_preserves_title(self) -> None:
        article = _make_article(title="My Title", text="Short.")
        chunks = chunk_article(article, max_chars=6_000)
        for chunk in chunks:
            assert chunk.title == "My Title"

    def test_chunk_preserves_date_and_link(self) -> None:
        article = _make_article(
            date="2025-03-01",
            link="https://example.com/a",
            text="Short.",
        )
        chunks = chunk_article(article, max_chars=6_000)
        for chunk in chunks:
            assert chunk.date == "2025-03-01"
            assert chunk.link == "https://example.com/a"

    def test_long_article_is_split_into_multiple_chunks(self) -> None:
        # Build a text that definitely exceeds 200 chars by repeating a paragraph.
        text = "Paragraph text here.\n\n" * 20  # ~440 chars
        article = _make_article(text=text)
        chunks = chunk_article(article, max_chars=100)
        assert len(chunks) > 1

    def test_chunk_indices_are_sequential(self) -> None:
        text = "Word " * 500  # ~2500 chars
        article = _make_article(text=text)
        chunks = chunk_article(article, max_chars=200)
        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_chunk_total_is_consistent(self) -> None:
        text = "Word " * 500
        article = _make_article(text=text)
        chunks = chunk_article(article, max_chars=200)
        totals = {c.chunk_total for c in chunks}
        assert totals == {len(chunks)}

    def test_empty_text_yields_single_chunk(self) -> None:
        article = ArticleInput(doc_id="empty-001", text="")
        chunks = chunk_article(article, max_chars=6_000)
        assert len(chunks) == 1
        assert chunks[0].chunk_text == ""


# ---------------------------------------------------------------------------
# Tests: JSON parsing helpers
# ---------------------------------------------------------------------------


class TestParseRawResponse:
    def test_valid_zero_events(self) -> None:
        raw = json.dumps({"doc_id": "art-001", "stance_events": []})
        parsed, err = _parse_raw_response(raw, "art-001")
        assert err is None
        assert parsed is not None
        assert parsed["stance_events"] == []

    def test_valid_multi_event(self) -> None:
        raw = _load_fixture(_VALID_DIR / "multiple_events.json")
        parsed, err = _parse_raw_response(raw, "article-multi-event-001")
        assert err is None
        assert parsed is not None
        assert len(parsed["stance_events"]) == 2

    def test_empty_response_returns_error(self) -> None:
        parsed, err = _parse_raw_response("", "art-001")
        assert parsed is None
        assert err is not None
        assert "empty" in err

    def test_malformed_json_returns_error(self) -> None:
        parsed, err = _parse_raw_response("{not valid json", "art-001")
        assert parsed is None
        assert err is not None
        assert "parse error" in err.lower() or "json" in err.lower()

    def test_plain_text_returns_error(self) -> None:
        raw = _load_fixture(_INVALID_DIR / "text_outside_json.txt")
        parsed, err = _parse_raw_response(raw, "art-001")
        assert parsed is None
        assert err is not None

    def test_missing_stance_events_key_returns_error(self) -> None:
        raw = json.dumps({"doc_id": "art-001"})
        parsed, err = _parse_raw_response(raw, "art-001")
        assert parsed is None
        assert err is not None
        assert "stance_events" in err

    def test_markdown_fence_stripped(self) -> None:
        inner = json.dumps({"doc_id": "art-001", "stance_events": []})
        raw = f"```json\n{inner}\n```"
        parsed, err = _parse_raw_response(raw, "art-001")
        assert err is None
        assert parsed is not None


# ---------------------------------------------------------------------------
# Tests: _build_candidate
# ---------------------------------------------------------------------------


class TestBuildCandidate:
    def _valid_event(self) -> dict:
        return {
            "politician": "Joe Biden",
            "topic": "healthcare",
            "normalized_proposition": "Biden supports expanding Medicare.",
            "stance_direction": "support",
            "stance_mode": "statement",
            "evidence_role": "direct_quote",
            "confidence": 0.9,
        }

    def test_valid_event_builds_candidate(self) -> None:
        cand, err = _build_candidate(
            self._valid_event(), doc_id="art-001", chunk_index=0, chunk_total=1
        )
        assert err is None
        assert cand is not None
        assert isinstance(cand, CandidateStanceEvent)

    def test_doc_id_preserved(self) -> None:
        cand, _ = _build_candidate(
            self._valid_event(), doc_id="prov-doc-42", chunk_index=0, chunk_total=1
        )
        assert cand is not None
        assert cand.doc_id == "prov-doc-42"

    def test_missing_required_field_returns_error(self) -> None:
        event = self._valid_event()
        del event["politician"]
        cand, err = _build_candidate(
            event, doc_id="art-001", chunk_index=0, chunk_total=1
        )
        assert cand is None
        assert err is not None
        assert "politician" in err

    def test_invalid_confidence_returns_error(self) -> None:
        event = self._valid_event()
        event["confidence"] = "not-a-number"
        cand, err = _build_candidate(
            event, doc_id="art-001", chunk_index=0, chunk_total=1
        )
        assert cand is None
        assert err is not None
        assert "confidence" in err

    def test_chunk_provenance_attached(self) -> None:
        cand, _ = _build_candidate(
            self._valid_event(), doc_id="art-001", chunk_index=2, chunk_total=5
        )
        assert cand is not None
        assert cand.chunk_index == 2
        assert cand.chunk_total == 5

    def test_optional_fields_default_to_none(self) -> None:
        cand, _ = _build_candidate(
            self._valid_event(), doc_id="art-001", chunk_index=0, chunk_total=1
        )
        assert cand is not None
        assert cand.subtopic is None
        assert cand.quote_text is None
        assert cand.notes is None


# ---------------------------------------------------------------------------
# Tests: extract_single_article (mocked LLM)
# ---------------------------------------------------------------------------


class TestExtractSingleArticle:
    def test_returns_extraction_result(self) -> None:
        raw = json.dumps({"doc_id": "art-001", "stance_events": []})
        result = extract_single_article(
            _make_article(),
            config=_make_config(),
            client=_make_mock_client(raw),
            debug_logger=_make_mock_debug_logger(),
        )
        assert isinstance(result, ExtractionResult)

    def test_zero_events_result(self) -> None:
        raw = json.dumps({"doc_id": "art-001", "stance_events": []})
        result = extract_single_article(
            _make_article(),
            config=_make_config(),
            client=_make_mock_client(raw),
            debug_logger=_make_mock_debug_logger(),
        )
        assert result.event_count == 0
        assert result.candidate_events == []
        assert result.succeeded

    def test_multi_event_result(self) -> None:
        raw = _load_fixture(_VALID_DIR / "multiple_events.json")
        article = _make_article(doc_id="article-multi-event-001")
        result = extract_single_article(
            article,
            config=_make_config(),
            client=_make_mock_client(raw),
            debug_logger=_make_mock_debug_logger(),
        )
        assert result.event_count == 2
        assert result.succeeded

    def test_provenance_preserved(self) -> None:
        raw = json.dumps({"doc_id": "prov-001", "stance_events": []})
        article = ArticleInput(
            doc_id="prov-001",
            text="Text.",
            title="My Title",
            date="2025-06-01",
            link="https://example.com",
        )
        result = extract_single_article(
            article,
            config=_make_config(),
            client=_make_mock_client(raw),
            debug_logger=_make_mock_debug_logger(),
        )
        assert result.doc_id == "prov-001"
        assert result.title == "My Title"
        assert result.date == "2025-06-01"
        assert result.link == "https://example.com"

    def test_candidate_event_doc_id_matches_article(self) -> None:
        raw = _load_fixture(_VALID_DIR / "single_direct_quote.json")
        article = _make_article(doc_id="article-direct-quote-001")
        result = extract_single_article(
            article,
            config=_make_config(),
            client=_make_mock_client(raw),
            debug_logger=_make_mock_debug_logger(),
        )
        assert result.event_count >= 1
        for event in result.candidate_events:
            assert event.doc_id == "article-direct-quote-001"

    def test_malformed_json_marks_chunk_failed(self) -> None:
        result = extract_single_article(
            _make_article(),
            config=_make_config(max_retries=1),
            client=_make_mock_client("{not json"),
            debug_logger=_make_mock_debug_logger(),
        )
        assert not result.succeeded
        assert result.failed_chunks == 1
        assert result.event_count == 0

    def test_empty_response_marks_chunk_failed(self) -> None:
        result = extract_single_article(
            _make_article(),
            config=_make_config(max_retries=1),
            client=_make_mock_client(""),
            debug_logger=_make_mock_debug_logger(),
        )
        assert not result.succeeded
        assert result.failed_chunks >= 1

    def test_llm_timeout_marks_chunk_failed(self) -> None:
        mock_client = MagicMock(spec=LLMClient)
        mock_client.complete.side_effect = LLMTimeoutError("timed out")
        result = extract_single_article(
            _make_article(),
            config=_make_config(max_retries=1),
            client=mock_client,
            debug_logger=_make_mock_debug_logger(),
        )
        assert not result.succeeded
        assert result.failed_chunks >= 1

    def test_llm_api_error_marks_chunk_failed(self) -> None:
        mock_client = MagicMock(spec=LLMClient)
        mock_client.complete.side_effect = LLMClientError("API error")
        result = extract_single_article(
            _make_article(),
            config=_make_config(max_retries=1),
            client=mock_client,
            debug_logger=_make_mock_debug_logger(),
        )
        assert not result.succeeded

    def test_retry_succeeds_on_second_attempt(self) -> None:
        """First call returns malformed JSON; second returns valid JSON."""
        raw_valid = json.dumps({"doc_id": "art-001", "stance_events": []})
        mock_client = MagicMock(spec=LLMClient)
        mock_client.complete.side_effect = ["{bad json}", raw_valid]
        result = extract_single_article(
            _make_article(),
            config=_make_config(max_retries=2),
            client=mock_client,
            debug_logger=_make_mock_debug_logger(),
        )
        assert result.succeeded

    def test_chunked_article_all_chunks_processed(self) -> None:
        """A long article is split and each chunk is extracted."""
        # Build text with paragraph breaks so the chunker can split it.
        # Each paragraph is ~120 chars; 12 paragraphs ≈ 1 440 chars total.
        # With max_chunk_chars=300 this should produce at least 4 chunks.
        para = "President Biden announced a new healthcare policy today. " * 2
        text = ("\n\n" + para.strip()) * 12
        article = _make_article(text=text)
        raw = json.dumps({"doc_id": article.doc_id, "stance_events": []})
        mock_client = MagicMock(spec=LLMClient)
        mock_client.complete.return_value = raw

        result = extract_single_article(
            article,
            config=_make_config(max_chunk_chars=300),
            client=mock_client,
            debug_logger=_make_mock_debug_logger(),
        )
        assert result.total_chunks >= 2
        assert mock_client.complete.call_count == result.total_chunks


# ---------------------------------------------------------------------------
# Tests: extract_articles (batch)
# ---------------------------------------------------------------------------


class TestExtractArticles:
    def test_returns_one_result_per_article(self) -> None:
        articles = [_make_article(doc_id=f"art-{i:03d}") for i in range(3)]
        raw = json.dumps({"doc_id": "placeholder", "stance_events": []})
        mock_client = _make_mock_client(raw)

        results = extract_articles(
            articles,
            config=_make_config(),
            client=mock_client,
            debug_logger=_make_mock_debug_logger(),
        )
        assert len(results) == 3

    def test_doc_ids_match_inputs(self) -> None:
        articles = [_make_article(doc_id=f"art-{i:03d}") for i in range(3)]
        raw = json.dumps({"doc_id": "placeholder", "stance_events": []})
        results = extract_articles(
            articles,
            config=_make_config(),
            client=_make_mock_client(raw),
            debug_logger=_make_mock_debug_logger(),
        )
        result_ids = [r.doc_id for r in results]
        assert result_ids == ["art-000", "art-001", "art-002"]

    def test_empty_batch_returns_empty_list(self) -> None:
        results = extract_articles(
            [],
            config=_make_config(),
            client=_make_mock_client(""),
            debug_logger=_make_mock_debug_logger(),
        )
        assert results == []


# ---------------------------------------------------------------------------
# Tests: DebugLogger
# ---------------------------------------------------------------------------


class TestDebugLogger:
    def _make_raw_output(self, doc_id: str = "art-001") -> RawExtractionOutput:
        return RawExtractionOutput(
            doc_id=doc_id,
            chunk_index=0,
            chunk_total=1,
            model_name="gpt-4o-mini",
            raw_response='{"doc_id": "art-001", "stance_events": []}',
            parsed_json={"doc_id": "art-001", "stance_events": []},
            parse_error=None,
            extraction_timestamp="2025-01-15T12:00:00+00:00",
            title="Test Article",
            date="2025-01-15",
            link="https://example.com",
            attempt_number=1,
        )

    def test_log_writes_jsonl_file(self, tmp_path: Path) -> None:
        log_path = tmp_path / "debug" / "test.jsonl"
        logger = DebugLogger(log_path=log_path, enabled=True)
        logger.log(self._make_raw_output())

        assert log_path.exists()
        lines = log_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["doc_id"] == "art-001"
        assert record["model_name"] == "gpt-4o-mini"

    def test_multiple_logs_append_lines(self, tmp_path: Path) -> None:
        log_path = tmp_path / "test.jsonl"
        logger = DebugLogger(log_path=log_path, enabled=True)
        logger.log(self._make_raw_output("art-001"))
        logger.log(self._make_raw_output("art-002"))

        lines = log_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["doc_id"] == "art-001"
        assert json.loads(lines[1])["doc_id"] == "art-002"

    def test_disabled_logger_writes_nothing(self, tmp_path: Path) -> None:
        log_path = tmp_path / "should_not_exist.jsonl"
        logger = DebugLogger(log_path=log_path, enabled=False)
        logger.log(self._make_raw_output())
        assert not log_path.exists()

    def test_log_contains_all_required_keys(self, tmp_path: Path) -> None:
        log_path = tmp_path / "test.jsonl"
        logger = DebugLogger(log_path=log_path, enabled=True)
        logger.log(self._make_raw_output())

        record = json.loads(log_path.read_text(encoding="utf-8").strip())
        for key in (
            "doc_id",
            "chunk_index",
            "chunk_total",
            "model_name",
            "raw_response",
            "parsed_json",
            "parse_error",
            "extraction_timestamp",
            "title",
            "date",
            "link",
            "attempt_number",
        ):
            assert key in record, f"key {key!r} missing from debug record"

    def test_parse_error_is_logged(self, tmp_path: Path) -> None:
        log_path = tmp_path / "test.jsonl"
        logger = DebugLogger(log_path=log_path, enabled=True)
        raw = RawExtractionOutput(
            doc_id="bad-001",
            chunk_index=0,
            chunk_total=1,
            model_name="gpt-4o-mini",
            raw_response="{bad json}",
            parsed_json=None,
            parse_error="JSON parse error: …",
            extraction_timestamp="2025-01-15T12:00:00+00:00",
        )
        logger.log(raw)

        record = json.loads(log_path.read_text(encoding="utf-8").strip())
        assert record["parsed_json"] is None
        assert record["parse_error"] is not None
        assert "JSON" in record["parse_error"]


# ---------------------------------------------------------------------------
# Tests: ExtractionResult helpers
# ---------------------------------------------------------------------------


class TestExtractionResult:
    def _make_result(
        self, *, event_count: int = 0, failed_chunks: int = 0, total_chunks: int = 1
    ) -> ExtractionResult:
        events = [
            CandidateStanceEvent(
                doc_id="art-001",
                politician="Biden",
                topic="healthcare",
                normalized_proposition="Biden supports Medicare expansion.",
                stance_direction="support",
                stance_mode="statement",
                evidence_role="direct_quote",
                confidence=0.9,
            )
            for _ in range(event_count)
        ]
        return ExtractionResult(
            doc_id="art-001",
            title="Title",
            date="2025-01-01",
            link=None,
            candidate_events=events,
            raw_outputs=[],
            total_chunks=total_chunks,
            failed_chunks=failed_chunks,
        )

    def test_succeeded_true_when_no_failed_chunks(self) -> None:
        assert self._make_result(failed_chunks=0).succeeded

    def test_succeeded_false_when_chunks_failed(self) -> None:
        assert not self._make_result(failed_chunks=1).succeeded

    def test_event_count_property(self) -> None:
        assert self._make_result(event_count=3).event_count == 3

    def test_zero_events_valid(self) -> None:
        result = self._make_result(event_count=0)
        assert result.event_count == 0
        assert result.candidate_events == []
