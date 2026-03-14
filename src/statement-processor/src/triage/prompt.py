"""
triage.prompt
=============
Triage prompt constants and loader for the first-pass LLM classifier.

The triage prompt is intentionally narrow: it asks only the minimum
questions needed to decide whether an article is worth sending to the
full extraction stage.  It uses a cheaper/faster model and a smaller
context window than full extraction.

The prompt is embedded here as a module-level constant rather than an
external file so that the triage stage has no filesystem dependency for its
core logic.  The stance extraction prompt continues to live in an external
markdown file because it is a formal contract.

Usage
-----
    from triage.prompt import TRIAGE_SYSTEM, render_triage_user_prompt

    system_msg = TRIAGE_SYSTEM
    user_msg = render_triage_user_prompt(
        doc_id="art-001",
        title="Biden signs climate bill",
        article_text="President Biden on Wednesday signed …",
    )
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# System instruction
# ---------------------------------------------------------------------------

TRIAGE_SYSTEM: str = (
    "You are a political-news triage classifier. "
    "Your job is to read one news article and decide whether it is worth "
    "sending to a full political-stance extractor. "
    "Answer the five questions below with true or false. "
    "Output ONLY a strict JSON object – no prose, no markdown, no commentary "
    "outside the JSON object."
)

# ---------------------------------------------------------------------------
# User prompt template
# ---------------------------------------------------------------------------

_TRIAGE_USER_TEMPLATE: str = """\
Classify the following news article.

ARTICLE DOC_ID: {doc_id}
ARTICLE TITLE: {title}

ARTICLE TEXT (may be truncated):
{article_text}

---

Answer the five questions below about the article.  For each question return
true or false.  Then set "advance" to true if the article is likely to yield
at least one meaningful political-stance event, otherwise false.

Output ONLY the following JSON object (no extra text):

{{
  "has_stance_statement": <true|false>,
  "has_policy_position": <true|false>,
  "has_politician_action": <true|false>,
  "has_contradiction_signal": <true|false>,
  "advance": <true|false>,
  "rationale": "<one sentence explaining your decision, max 150 chars>"
}}

QUESTION DEFINITIONS
  has_stance_statement    : The article contains a direct or reported statement
                            from a politician expressing a view or position.
  has_policy_position     : The article records a specific policy stance
                            (support for, opposition to, or ambiguity about a
                            policy or bill).
  has_politician_action   : The article records a politician taking a concrete
                            action (e.g. signed a bill, issued an order, cast a
                            vote, made an appointment).
  has_contradiction_signal: The article mentions a change, reversal,
                            inconsistency, or contradiction in a politician's
                            position relative to a prior position.
  advance                 : Set to true when the article is likely to yield at
                            least one useful stance event for tracking purposes.
                            Set to false for purely horse-race, poll, or
                            celebrity news with no policy content.

Return ONLY the JSON object.  Begin your response with `{{` and end with `}}`.\
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render_triage_user_prompt(
    doc_id: str,
    title: str,
    article_text: str,
) -> str:
    """Render the triage user prompt with article-specific values.

    Parameters
    ----------
    doc_id:
        Unique article identifier.
    title:
        Article headline.
    article_text:
        Article body text (or truncated excerpt).

    Returns
    -------
    str
        The rendered user prompt string, ready to be sent to the model.
    """
    return _TRIAGE_USER_TEMPLATE.format(
        doc_id=doc_id,
        title=title,
        article_text=article_text,
    )
