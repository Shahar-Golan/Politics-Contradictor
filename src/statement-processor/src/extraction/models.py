"""
extraction.models
=================
Typed data models for the LLM-based stance extraction pipeline.

These dataclasses represent the inputs, intermediate outputs, and final
candidate results produced by the extractor.  All outputs are treated as
**untrusted candidates** until a later validation step approves them.

Design principles
-----------------
* Keep models lightweight (dataclasses, not Pydantic) to match the
  selection layer style.
* Preserve article-level and chunk-level provenance throughout the pipeline.
* Separate raw model output from parsed/typed candidates so that the raw
  response is always available for debugging.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArticleInput:
    """A single article to be processed by the extractor.

    Attributes
    ----------
    doc_id:
        Unique article identifier (matches ``news_articles.doc_id``).
    text:
        Full article body text.
    title:
        Article headline, or ``None`` if not available.
    date:
        Publication date (ISO-8601 string), or ``None`` if not available.
    link:
        Source URL, or ``None`` if not available.
    """

    doc_id: str
    text: str
    title: Optional[str] = None
    date: Optional[str] = None
    link: Optional[str] = None


@dataclass(frozen=True)
class ChunkInput:
    """A text chunk derived from an :class:`ArticleInput`.

    Used when an article is split into multiple segments to fit within
    model context limits.  Provenance fields allow outputs to be traced
    back to the original article.

    Attributes
    ----------
    doc_id:
        Original article identifier.
    chunk_index:
        0-based index of this chunk within the article (0 = first chunk).
    chunk_total:
        Total number of chunks for this article.
    chunk_text:
        The text content of this specific chunk.
    title:
        Original article headline, forwarded for context.
    date:
        Original article publication date.
    link:
        Original article source URL.
    """

    doc_id: str
    chunk_index: int
    chunk_total: int
    chunk_text: str
    title: Optional[str] = None
    date: Optional[str] = None
    link: Optional[str] = None


# ---------------------------------------------------------------------------
# Intermediate / debug models
# ---------------------------------------------------------------------------


@dataclass
class RawExtractionOutput:
    """Raw model response and request metadata for a single chunk.

    This object is always produced regardless of whether the response
    parsed successfully.  It is written to the debug log so that extraction
    behaviour can be inspected after the fact.

    Attributes
    ----------
    doc_id:
        Source article identifier.
    chunk_index:
        0-based chunk index (0 for un-chunked articles).
    chunk_total:
        Total number of chunks for the article.
    model_name:
        Name of the LLM model used (e.g. ``"gpt-4o-mini"``).
    raw_response:
        The raw text content returned by the model.  May be empty or
        malformed JSON.
    parsed_json:
        The parsed JSON object, if parsing succeeded; ``None`` otherwise.
    parse_error:
        Human-readable parse/pre-check failure reason, or ``None`` if
        parsing succeeded.
    extraction_timestamp:
        ISO-8601 timestamp when the extraction was performed.
    title:
        Article headline forwarded for debug context.
    date:
        Article publication date forwarded for debug context.
    link:
        Article source URL forwarded for debug context.
    attempt_number:
        Which attempt produced this output (1-based; > 1 means a retry).
    """

    doc_id: str
    chunk_index: int
    chunk_total: int
    model_name: str
    raw_response: str
    parsed_json: Optional[dict[str, Any]]
    parse_error: Optional[str]
    extraction_timestamp: str
    title: Optional[str] = None
    date: Optional[str] = None
    link: Optional[str] = None
    attempt_number: int = 1


# ---------------------------------------------------------------------------
# Candidate output models
# ---------------------------------------------------------------------------


@dataclass
class CandidateStanceEvent:
    """One parsed (but **unvalidated**) stance event candidate.

    Every field mirrors a ``StanceEvent`` field from the extraction schema.
    All values come directly from the model response and must be treated as
    untrusted until a later validator approves them.

    Attributes
    ----------
    doc_id:
        Source article identifier – preserved from the input.
    politician:
        Full name of the politician.
    topic:
        High-level policy area (one of the controlled vocabulary values).
    normalized_proposition:
        Declarative sentence summarising the stance.
    stance_direction:
        Direction of the stance (support / oppose / mixed / unclear).
    stance_mode:
        Form of expression (statement / action / promise / accusation /
        value_judgment).
    evidence_role:
        How evidence relates to the stance (direct_quote / reported_speech /
        inferred_from_action / headline_claim / summary_statement).
    confidence:
        Extractor confidence (0.0 – 1.0).
    subtopic:
        Optional finer-grained sub-category.
    speaker:
        Who delivered the statement (may differ from politician).
    target_entity:
        Entity the stance is directed at.
    event_date:
        ISO-8601 date when the stance was expressed.
    event_date_precision:
        Precision of ``event_date`` (day / month / year / approximate).
    quote_text:
        Verbatim text from the article.
    quote_start_char:
        0-based character offset of ``quote_text``.
    quote_end_char:
        Exclusive end offset of ``quote_text``.
    paraphrase:
        Brief paraphrase of the supporting evidence.
    notes:
        Extraction uncertainty notes.
    chunk_index:
        Chunk this event was extracted from (0 for un-chunked articles).
    chunk_total:
        Total number of chunks for the source article.
    """

    # Provenance
    doc_id: str

    # Required fields (from schema)
    politician: str
    topic: str
    normalized_proposition: str
    stance_direction: str
    stance_mode: str
    evidence_role: str
    confidence: float

    # Optional fields
    subtopic: Optional[str] = None
    speaker: Optional[str] = None
    target_entity: Optional[str] = None
    event_date: Optional[str] = None
    event_date_precision: Optional[str] = None
    quote_text: Optional[str] = None
    quote_start_char: Optional[int] = None
    quote_end_char: Optional[int] = None
    paraphrase: Optional[str] = None
    notes: Optional[str] = None

    # Chunk provenance
    chunk_index: int = 0
    chunk_total: int = 1


@dataclass
class ExtractionResult:
    """Aggregated output from processing a single article.

    Attributes
    ----------
    doc_id:
        Source article identifier.
    title:
        Article headline.
    date:
        Article publication date.
    link:
        Article source URL.
    candidate_events:
        Zero or more parsed candidate stance events.  These are untrusted
        until a later validator reviews them.
    raw_outputs:
        All raw model responses produced during extraction (one per chunk,
        including retries).  Always populated, even on failure.
    total_chunks:
        Number of chunks the article was split into.
    failed_chunks:
        Number of chunks where parsing failed on all attempts.
    """

    doc_id: str
    title: Optional[str]
    date: Optional[str]
    link: Optional[str]
    candidate_events: list[CandidateStanceEvent]
    raw_outputs: list[RawExtractionOutput]
    total_chunks: int
    failed_chunks: int

    @property
    def succeeded(self) -> bool:
        """``True`` if every chunk was parsed without error."""
        return self.failed_chunks == 0

    @property
    def event_count(self) -> int:
        """Number of candidate events extracted from this article."""
        return len(self.candidate_events)


# ---------------------------------------------------------------------------
# Extraction config
# ---------------------------------------------------------------------------


@dataclass
class ExtractionConfig:
    """Configuration for the extraction pipeline.

    Attributes
    ----------
    model_name:
        LLM model identifier (e.g. ``"gpt-4o-mini"``).
    max_chunk_chars:
        Maximum number of characters per chunk before the article text is
        split.  Defaults to 6 000 characters (roughly 1 500 tokens).
    max_retries:
        Maximum number of attempts per chunk on transient/parse failures.
        Defaults to 2 (i.e. one initial attempt + one retry).
    temperature:
        LLM sampling temperature.  0.0 is recommended for deterministic
        JSON extraction.
    debug_log_path:
        Path to write the JSONL debug log.  ``None`` disables file logging.
    """

    model_name: str = "gpt-5-nano"
    max_chunk_chars: int = 6_000
    max_retries: int = 2
    temperature: float = 1
    debug_log_path: Optional[str] = None
