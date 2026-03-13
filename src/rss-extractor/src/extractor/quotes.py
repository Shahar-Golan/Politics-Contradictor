"""
extractor.quotes
================
Quote and statement candidate extraction from article text.

Identifies direct quotes (text in quotation marks attributed to a politician)
and indirect statements (sentences with speech verbs attributed to a politician)
within extracted article bodies.
"""

from __future__ import annotations

import logging
import re

from src.extractor.models import StatementCandidate
from src.utils.config import PoliticianConfig
from src.utils.hashing import content_hash

logger = logging.getLogger(__name__)

# Pattern for text enclosed in double quotation marks (including curly quotes).
# Matches 20–500 characters of quoted content.
_QUOTE_PATTERN = re.compile(r'["\u201c]([^"\u201d]{20,500})["\u201d]')

# Speech verbs that signal attributed statements.
_SPEECH_VERBS: frozenset[str] = frozenset({
    "said", "stated", "announced", "declared", "argued",
    "claimed", "told", "noted", "added", "confirmed",
    "insisted", "emphasized", "remarked",
})

_VERB_PATTERN = re.compile(
    r"\b(?:" + "|".join(_SPEECH_VERBS) + r")\b",
    re.IGNORECASE,
)

# Sentence-boundary pattern: split after terminal punctuation followed by whitespace.
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


def extract_statements(
    body: str,
    politician: PoliticianConfig,
    article_id: str = "",
) -> list[StatementCandidate]:
    """Extract quote and statement candidates from article body text.

    Looks for:

    1. Direct quotes — text inside ``"..."`` or ``\u201c...\u201d`` (curly quotes) that
       appears near a politician alias.
    2. Indirect statements — sentences that contain a speech verb (e.g. *said*,
       *announced*, *declared*) together with a politician alias.

    Args:
        body: Clean article body text.
        politician: Configuration for the politician to attribute statements to.
        article_id: Optional ID of the source ``ExtractedArticle``.

    Returns:
        A list of :class:`~extractor.models.StatementCandidate` records. May be empty.
    """
    aliases = [politician.name, *politician.aliases]
    candidates: list[StatementCandidate] = []
    candidates.extend(_find_direct_quotes(body, politician.id, article_id, aliases))
    candidates.extend(_find_indirect_statements(body, politician.id, article_id, aliases))
    return candidates


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _sentence_spans(body: str) -> list[tuple[int, int]]:
    """Return ``(start, end)`` character spans for each sentence in *body*.

    Sentences are delimited by terminal punctuation (``.``, ``!``, ``?``)
    followed by whitespace.

    Args:
        body: Plain text body.

    Returns:
        List of ``(start, end)`` tuples; ``end`` is exclusive.
    """
    boundaries = list(_SENTENCE_BOUNDARY.finditer(body))
    starts = [0] + [m.end() for m in boundaries]
    ends = [m.start() for m in boundaries] + [len(body)]
    return list(zip(starts, ends))


def _get_context(
    body: str,
    match_start: int,
    match_end: int,
    n: int = 2,
) -> str:
    """Extract up to *n* surrounding sentences as attribution context.

    Args:
        body: Full article body text.
        match_start: Start character offset of the matched span.
        match_end: End character offset of the matched span (exclusive).
        n: Number of sentences to include before and after the match sentence.

    Returns:
        Stripped context string covering the matched sentence plus its neighbours.
    """
    spans = _sentence_spans(body)
    if not spans:
        return body.strip()

    # Find the index of the sentence that contains the match start.
    sent_idx = 0
    for i, (s, e) in enumerate(spans):
        if s <= match_start < e:
            sent_idx = i
            break
    else:
        # Fallback: use the last sentence.
        sent_idx = len(spans) - 1

    ctx_start = max(0, sent_idx - n)
    ctx_end = min(len(spans), sent_idx + n + 1)
    char_start = spans[ctx_start][0]
    char_end = spans[ctx_end - 1][1]
    return body[char_start:char_end].strip()


def _find_direct_quotes(
    body: str,
    politician_id: str,
    article_id: str,
    aliases: list[str],
) -> list[StatementCandidate]:
    """Find direct quotes plausibly attributed to the politician.

    A quote is included if a politician alias appears within the surrounding
    two-sentence context of the quoted text.

    Args:
        body: Article body text.
        politician_id: ID of the politician.
        article_id: ID of the source article.
        aliases: Politician name variants to match for attribution.

    Returns:
        List of :class:`~extractor.models.StatementCandidate` records.
    """
    candidates: list[StatementCandidate] = []
    if not aliases:
        return candidates

    alias_pattern = re.compile(
        r"\b(" + "|".join(re.escape(a) for a in aliases) + r")\b",
        re.IGNORECASE,
    )

    for match in _QUOTE_PATTERN.finditer(body):
        quote_text = match.group(1).strip()
        start = match.start()
        end = match.end()

        context = _get_context(body, start, end)

        if alias_pattern.search(context):
            statement_id = content_hash(quote_text)
            candidates.append(
                StatementCandidate(
                    statement_id=statement_id,
                    article_id=article_id,
                    politician_id=politician_id,
                    text=quote_text,
                    is_direct_quote=True,
                    context=context,
                    char_offset=start,
                )
            )
            logger.debug(
                "Found direct quote at offset %d for politician %s.",
                start,
                politician_id,
            )

    return candidates


def _find_indirect_statements(
    body: str,
    politician_id: str,
    article_id: str,
    aliases: list[str],
) -> list[StatementCandidate]:
    """Find indirect statements attributed to the politician via speech verbs.

    A sentence is included if it contains both a politician alias and a speech
    verb (e.g. *said*, *announced*, *declared*), indicating that the politician
    made a statement.

    Args:
        body: Article body text.
        politician_id: ID of the politician.
        article_id: ID of the source article.
        aliases: Politician name variants to match for attribution.

    Returns:
        List of :class:`~extractor.models.StatementCandidate` records.
    """
    candidates: list[StatementCandidate] = []
    if not aliases:
        return candidates

    alias_pattern = re.compile(
        r"\b(" + "|".join(re.escape(a) for a in aliases) + r")\b",
        re.IGNORECASE,
    )

    spans = _sentence_spans(body)
    for i, (start, end) in enumerate(spans):
        sentence = body[start:end].strip()
        if not sentence:
            continue
        if not alias_pattern.search(sentence):
            continue
        if not _VERB_PATTERN.search(sentence):
            continue

        statement_id = content_hash(sentence)
        context = _get_context(body, start, end)
        candidates.append(
            StatementCandidate(
                statement_id=statement_id,
                article_id=article_id,
                politician_id=politician_id,
                text=sentence,
                is_direct_quote=False,
                context=context,
                char_offset=start,
            )
        )
        logger.debug(
            "Found indirect statement at offset %d for politician %s.",
            start,
            politician_id,
        )

    return candidates
