"""
contracts.vocab
===============
Controlled vocabularies for the stance extraction contract (v1).

These values are the single source of truth for all enumerated fields in the
``StanceEvent`` JSON schema (``schemas/stance_extraction.schema.json``).

Downstream code (extractors, validators, tests) should import from here
rather than hard-coding string literals.

Usage
-----
    from contracts.vocab import TOPIC_VALUES, STANCE_DIRECTION_VALUES

    assert event["topic"] in TOPIC_VALUES
    assert event["stance_direction"] in STANCE_DIRECTION_VALUES
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# topic
# ---------------------------------------------------------------------------
# High-level political issue areas supported in the first version.
# Use "other" when none of the specific values fit.

TOPIC_VALUES: frozenset[str] = frozenset(
    [
        "immigration",
        "trade",
        "foreign_policy",
        "abortion",
        "healthcare",
        "economy",
        "taxation",
        "crime",
        "climate",
        "energy",
        "elections",
        "democracy",
        "other",
    ]
)

# ---------------------------------------------------------------------------
# stance_direction
# ---------------------------------------------------------------------------
# The direction of a politician's stance toward a proposition.
#
#   support        – the politician endorses or promotes the proposition.
#   oppose         – the politician rejects or argues against the proposition.
#   mixed          – the politician expresses both support and opposition
#                    within the same event (use sparingly; prefer two events).
#   unclear        – evidence is too ambiguous to assign a direction.

STANCE_DIRECTION_VALUES: frozenset[str] = frozenset(
    [
        "support",
        "oppose",
        "mixed",
        "unclear",
    ]
)

# ---------------------------------------------------------------------------
# stance_mode
# ---------------------------------------------------------------------------
# The mode or form through which the stance is expressed.
#
#   statement      – a verbal declaration or public comment.
#   action         – a concrete act (signing a bill, issuing an order, etc.).
#   promise        – a forward-looking commitment or pledge.
#   accusation     – one actor accuses another of something; populate
#                    target_entity accordingly.
#   value_judgment – an expression of values or moral framing without a
#                    specific policy claim.

STANCE_MODE_VALUES: frozenset[str] = frozenset(
    [
        "statement",
        "action",
        "promise",
        "accusation",
        "value_judgment",
    ]
)

# ---------------------------------------------------------------------------
# evidence_role
# ---------------------------------------------------------------------------
# How the supporting evidence relates to the stance event.
#
#   direct_quote         – politician's exact words in quotation marks.
#   reported_speech      – article paraphrases what the politician said
#                          (e.g. "he said that …") without full quotes.
#   inferred_from_action – stance inferred from an action rather than words
#                          (e.g. vetoed a bill → opposes that policy).
#   headline_claim       – evidence comes only from the article headline;
#                          body may not fully corroborate it.
#   summary_statement    – general characterisation by the article author
#                          without direct attribution.

EVIDENCE_ROLE_VALUES: frozenset[str] = frozenset(
    [
        "direct_quote",
        "reported_speech",
        "inferred_from_action",
        "headline_claim",
        "summary_statement",
    ]
)

# ---------------------------------------------------------------------------
# event_date_precision
# ---------------------------------------------------------------------------
# How precise the event_date value is.
#
#   day         – date is known to the specific calendar day (YYYY-MM-DD).
#   month       – only the month is known (YYYY-MM).
#   year        – only the year is known (YYYY).
#   approximate – date is estimated (use with a note explaining the basis).

EVENT_DATE_PRECISION_VALUES: frozenset[str] = frozenset(
    [
        "day",
        "month",
        "year",
        "approximate",
    ]
)

# ---------------------------------------------------------------------------
# Aggregate mapping (useful for generic validators)
# ---------------------------------------------------------------------------

ALL_VOCABULARIES: dict[str, frozenset[str]] = {
    "topic": TOPIC_VALUES,
    "stance_direction": STANCE_DIRECTION_VALUES,
    "stance_mode": STANCE_MODE_VALUES,
    "evidence_role": EVIDENCE_ROLE_VALUES,
    "event_date_precision": EVENT_DATE_PRECISION_VALUES,
}
