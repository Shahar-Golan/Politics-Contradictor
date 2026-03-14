"""
triage.models
=============
Typed data models for the first-pass LLM triage classifier.

The triage stage sits between the deterministic pre-filter (selection) and
the expensive full stance extractor.  Its job is to decide whether an article
is worth sending to the full extractor.

Design principles
-----------------
* Mirror the style of :mod:`extraction.models` – lightweight dataclasses, not
  Pydantic – so that all layers feel consistent.
* Preserve article provenance (``doc_id``, title, link, date) throughout.
* Keep the triage decision simple: five boolean questions + a single
  ``advance`` recommendation that drives the next stage.
* Store the raw model response alongside the parsed decision so that
  failures are always auditable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TriageArticle:
    """A single article to be classified by the triage stage.

    Attributes
    ----------
    doc_id:
        Unique article identifier (matches ``news_articles.doc_id``).
    title:
        Article headline.
    text:
        Full article body text (or a representative excerpt for very long
        articles).
    date:
        Publication date (ISO-8601 string), or ``None`` if unavailable.
    link:
        Source URL, or ``None`` if unavailable.
    matched_politician:
        The canonical politician name that caused this article to be
        selected by the deterministic filter.
    """

    doc_id: str
    title: str
    text: str
    date: Optional[str] = None
    link: Optional[str] = None
    matched_politician: Optional[str] = None


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


@dataclass
class TriageDecision:
    """Structured output from the triage LLM for one article.

    Each boolean field corresponds to a question in the triage prompt.
    All values come directly from the model response and must be treated as
    untrusted until the ingestion layer validates them.

    Attributes
    ----------
    has_stance_statement:
        The article contains a stance-bearing statement from a politician.
    has_policy_position:
        The article records a specific policy position.
    has_politician_action:
        The article records a politician action relevant to stance tracking
        (e.g. signed a bill, issued an executive order).
    has_contradiction_signal:
        The article mentions a change, reversal, inconsistency, or
        contradiction in a politician's position.
    advance:
        Whether the article should advance to full stance extraction.
        The model is expected to set this to ``True`` when at least one
        of the other fields is ``True`` and the article is likely to yield
        useful stance events.
    rationale:
        Optional short explanation from the model for its decision.
    """

    has_stance_statement: bool
    has_policy_position: bool
    has_politician_action: bool
    has_contradiction_signal: bool
    advance: bool
    rationale: Optional[str] = None


@dataclass
class TriageResult:
    """Outcome for a single article after triage batch ingestion.

    Attributes
    ----------
    doc_id:
        Source article identifier.
    title:
        Article headline (for logging/debugging).
    link:
        Article source URL.
    date:
        Article publication date.
    matched_politician:
        Politician that triggered selection.
    request_id:
        The ``custom_id`` used in the Batch API request.
    decision:
        Parsed :class:`TriageDecision` if parsing succeeded; ``None``
        otherwise.
    raw_response:
        Raw text returned by the model.  Always populated when a response
        was received, even if parsing failed.
    parse_error:
        Human-readable error message if parsing failed; ``None`` otherwise.
    failed:
        ``True`` when the Batch API request itself failed (HTTP error or
        provider error), distinct from a parse failure.
    """

    doc_id: str
    title: Optional[str]
    link: Optional[str]
    date: Optional[str]
    matched_politician: Optional[str]
    request_id: str
    decision: Optional[TriageDecision]
    raw_response: Optional[str]
    parse_error: Optional[str]
    failed: bool = False

    @property
    def is_positive(self) -> bool:
        """``True`` when the triage decision recommends advancing the article."""
        return self.decision is not None and self.decision.advance and not self.failed


# ---------------------------------------------------------------------------
# Batch ingestion aggregate
# ---------------------------------------------------------------------------


@dataclass
class TriageBatchIngestionResult:
    """Aggregated result of ingesting one completed triage batch output file.

    Attributes
    ----------
    results:
        One :class:`TriageResult` per request in the batch.
    positives:
        Subset of *results* where ``is_positive`` is ``True``.
    negatives:
        Subset of *results* where the decision was received but ``advance``
        is ``False``.
    failed:
        Subset of *results* where the Batch API request failed.
    parse_errors:
        Subset of *results* where the response was received but the JSON
        output could not be parsed.
    retry_candidates:
        Combined list of failed + parse_error results that are candidates
        for re-submission.
    """

    results: list[TriageResult] = field(default_factory=list)

    @property
    def positives(self) -> list[TriageResult]:
        """Articles that advance to full extraction."""
        return [r for r in self.results if r.is_positive]

    @property
    def negatives(self) -> list[TriageResult]:
        """Articles classified as not worth advancing."""
        return [
            r
            for r in self.results
            if not r.failed and r.parse_error is None and not r.is_positive
        ]

    @property
    def failed(self) -> list[TriageResult]:
        """Articles whose Batch API request failed."""
        return [r for r in self.results if r.failed]

    @property
    def parse_errors(self) -> list[TriageResult]:
        """Articles where the response was received but could not be parsed."""
        return [r for r in self.results if not r.failed and r.parse_error is not None]

    @property
    def retry_candidates(self) -> list[TriageResult]:
        """Articles that should be re-submitted (failed + parse errors)."""
        return self.failed + self.parse_errors

    def summary(self) -> dict[str, Any]:
        """Return a summary dict suitable for JSON serialisation."""
        return {
            "total": len(self.results),
            "positives": len(self.positives),
            "negatives": len(self.negatives),
            "failed": len(self.failed),
            "parse_errors": len(self.parse_errors),
            "retry_candidates": len(self.retry_candidates),
        }


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class TriageConfig:
    """Configuration for the triage batch stage.

    Attributes
    ----------
    model_name:
        LLM model to use for triage.  Should be cheaper/faster than the
        full extraction model.  Defaults to ``"gpt-4o-mini"``.
    max_article_chars:
        Maximum number of characters of article text to include in the
        triage prompt.  Long articles are truncated for cost efficiency.
        Defaults to 2 000 characters.
    temperature:
        LLM sampling temperature.  0.0 for deterministic JSON output.
    batch_size:
        Maximum number of requests per Batch API file.  The OpenAI Batch
        API accepts up to 50 000 requests per file; setting a lower value
        allows chunking large candidate sets into multiple files.
        Defaults to 10 000.
    """

    model_name: str = "gpt-4o-mini"
    max_article_chars: int = 2_000
    temperature: float = 0.0
    batch_size: int = 10_000
