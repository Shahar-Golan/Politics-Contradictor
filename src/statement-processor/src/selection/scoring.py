"""
selection.scoring
=================
Rule-based scoring logic for the article selection layer.

Each rule contributes a fixed integer weight to the overall article score.
The rules are deterministic, inspectable, and easy to extend.

Rule catalogue
--------------
+-----------------------------------+--------+-------------------------------------------+
| Rule name                         | Weight | Signal                                    |
+===================================+========+===========================================+
| politician_in_speakers            |  +3    | Politician name in speakers_mentioned     |
+-----------------------------------+--------+-------------------------------------------+
| reporting_verb_in_title           |  +2    | Title contains a reporting/action verb    |
+-----------------------------------+--------+-------------------------------------------+
| policy_topic_in_title             |  +2    | Title contains a policy topic keyword     |
+-----------------------------------+--------+-------------------------------------------+
| policy_topic_in_text              |  +1    | Text contains a policy topic keyword      |
+-----------------------------------+--------+-------------------------------------------+
| quote_marker_in_text              |  +2    | Text contains a direct-quote marker       |
+-----------------------------------+--------+-------------------------------------------+
| politician_in_title               |  +1    | Politician alias appears in title         |
+-----------------------------------+--------+-------------------------------------------+
| text_length_ok                    |  +1    | Text meets minimum length threshold       |
+-----------------------------------+--------+-------------------------------------------+
| low_priority_signal_in_title      |  -2    | Title contains a low-priority signal      |
+-----------------------------------+--------+-------------------------------------------+
| low_priority_signal_in_text       |  -1    | Text contains a low-priority signal       |
+-----------------------------------+--------+-------------------------------------------+
| text_too_short                    |  -2    | Text is below minimum length threshold    |
+-----------------------------------+--------+-------------------------------------------+
"""

from __future__ import annotations

import json
import re
from typing import Any

from .keywords import (
    LOW_PRIORITY_SIGNALS,
    MIN_TEXT_LENGTH,
    POLICY_TOPICS,
    POLITICIAN_ALIASES,
    QUOTE_MARKERS,
    REPORTING_VERBS,
)
from .models import ScoredArticle, SelectionConfig

# ---------------------------------------------------------------------------
# Rule weights
# ---------------------------------------------------------------------------

_RULE_WEIGHTS: dict[str, int] = {
    "politician_in_speakers": 3,
    "reporting_verb_in_title": 2,
    "policy_topic_in_title": 2,
    "policy_topic_in_text": 1,
    "quote_marker_in_text": 2,
    "politician_in_title": 1,
    "text_length_ok": 1,
    "low_priority_signal_in_title": -2,
    "low_priority_signal_in_text": -1,
    "text_too_short": -2,
}


def _parse_speakers(raw: Any) -> list[str]:
    """Return a list of lower-cased speaker names from a raw SQLite value.

    Parameters
    ----------
    raw:
        Value from the ``speakers_mentioned`` column.  May be a JSON array
        string, a comma-separated string, or ``None``.
    """
    if raw is None or str(raw).strip() == "":
        return []
    raw_str = str(raw).strip()
    try:
        parsed = json.loads(raw_str)
        if isinstance(parsed, list):
            return [str(s).lower().strip() for s in parsed if str(s).strip()]
    except (json.JSONDecodeError, ValueError):
        pass
    return [s.lower().strip() for s in raw_str.split(",") if s.strip()]


def _contains_any(text: str, terms: frozenset[str]) -> bool:
    """Return ``True`` if *text* (lower-cased) contains any term from *terms*.

    Uses word-boundary-aware substring matching for purely alphabetic
    single-word terms, and plain substring matching for everything else
    (multi-word phrases, terms containing punctuation such as ``"``, etc.).

    Parameters
    ----------
    text:
        The text to search (should already be lower-cased).
    terms:
        A frozenset of lower-cased terms to look for.
    """
    for term in terms:
        if " " in term:
            # Multi-word phrase: simple substring match.
            if term in text:
                return True
        elif re.match(r"^[a-z'\-]+$", term):
            # Purely alphabetic (with optional hyphens/apostrophes): use
            # word boundaries to avoid partial matches, e.g. "poll" should
            # not match "pollster" when we only want the standalone word.
            if re.search(r"\b" + re.escape(term) + r"\b", text):
                return True
        else:
            # Non-alphabetic term (e.g. quotation characters): plain ``in``.
            if term in text:
                return True
    return False


def score_article_for_extraction(
    article_row: dict[str, Any],
    politician: str,
    config: SelectionConfig | None = None,
) -> ScoredArticle:
    """Score a single article row for extraction eligibility.

    The score is derived entirely from deterministic rule matching.  No
    external API or LLM is used.

    Parameters
    ----------
    article_row:
        A dict (or ``sqlite3.Row``-compatible mapping) with the following
        keys from ``news_articles``:

        - ``doc_id`` (str)
        - ``title`` (str | None)
        - ``text`` (str | None)
        - ``speakers_mentioned`` (str | None) — stored as JSON array string

    politician:
        The canonical politician name to score against.  Must be a key in
        :data:`~selection.keywords.POLITICIAN_ALIASES`.

    config:
        Optional :class:`~selection.models.SelectionConfig`.  If omitted, a
        default config is used.

    Returns
    -------
    ScoredArticle
        Scored result including ``score``, ``matched_rules``, and
        ``is_eligible``.

    Raises
    ------
    KeyError
        If *politician* is not a recognised alias key.
    """
    if config is None:
        config = SelectionConfig()

    aliases = POLITICIAN_ALIASES.get(politician)
    if aliases is None:
        raise KeyError(
            f"Unknown politician {politician!r}. "
            f"Available politicians: {sorted(POLITICIAN_ALIASES)}"
        )

    doc_id: str = str(article_row.get("doc_id") or "")
    title: str = str(article_row.get("title") or "").strip()
    text: str = str(article_row.get("text") or "").strip()
    speakers_raw: Any = article_row.get("speakers_mentioned")

    title_lower = title.lower()
    text_lower = text.lower()

    speakers = _parse_speakers(speakers_raw)
    matched_rules: list[str] = []
    score: int = 0

    # ------------------------------------------------------------------
    # Rule: politician_in_speakers
    # ------------------------------------------------------------------
    if any(_contains_any(s, aliases) for s in speakers):
        matched_rules.append("politician_in_speakers")
        score += _RULE_WEIGHTS["politician_in_speakers"]

    # ------------------------------------------------------------------
    # Rule: politician_in_title
    # ------------------------------------------------------------------
    if _contains_any(title_lower, aliases):
        matched_rules.append("politician_in_title")
        score += _RULE_WEIGHTS["politician_in_title"]

    # ------------------------------------------------------------------
    # Rule: reporting_verb_in_title
    # ------------------------------------------------------------------
    if _contains_any(title_lower, REPORTING_VERBS):
        matched_rules.append("reporting_verb_in_title")
        score += _RULE_WEIGHTS["reporting_verb_in_title"]

    # ------------------------------------------------------------------
    # Rule: policy_topic_in_title
    # ------------------------------------------------------------------
    if _contains_any(title_lower, POLICY_TOPICS):
        matched_rules.append("policy_topic_in_title")
        score += _RULE_WEIGHTS["policy_topic_in_title"]

    # ------------------------------------------------------------------
    # Rule: policy_topic_in_text
    # ------------------------------------------------------------------
    if text_lower and _contains_any(text_lower, POLICY_TOPICS):
        matched_rules.append("policy_topic_in_text")
        score += _RULE_WEIGHTS["policy_topic_in_text"]

    # ------------------------------------------------------------------
    # Rule: quote_marker_in_text
    # ------------------------------------------------------------------
    if text and _contains_any(text_lower, QUOTE_MARKERS):
        matched_rules.append("quote_marker_in_text")
        score += _RULE_WEIGHTS["quote_marker_in_text"]

    # ------------------------------------------------------------------
    # Rule: text_length_ok / text_too_short
    # ------------------------------------------------------------------
    min_len = config.min_text_length
    text_len = len(text)
    if text_len >= min_len:
        matched_rules.append("text_length_ok")
        score += _RULE_WEIGHTS["text_length_ok"]
    elif text_len > 0:
        # Only penalise if there is some text but it is too short.
        matched_rules.append("text_too_short")
        score += _RULE_WEIGHTS["text_too_short"]

    # ------------------------------------------------------------------
    # Rule: low_priority_signal_in_title
    # ------------------------------------------------------------------
    if title_lower and _contains_any(title_lower, LOW_PRIORITY_SIGNALS):
        matched_rules.append("low_priority_signal_in_title")
        score += _RULE_WEIGHTS["low_priority_signal_in_title"]

    # ------------------------------------------------------------------
    # Rule: low_priority_signal_in_text
    # ------------------------------------------------------------------
    if text_lower and _contains_any(text_lower, LOW_PRIORITY_SIGNALS):
        matched_rules.append("low_priority_signal_in_text")
        score += _RULE_WEIGHTS["low_priority_signal_in_text"]

    is_eligible = score >= config.min_score

    return ScoredArticle(
        doc_id=doc_id,
        title=title or None,
        matched_politician=politician,
        score=score,
        matched_rules=tuple(matched_rules),
        is_eligible=is_eligible,
    )
