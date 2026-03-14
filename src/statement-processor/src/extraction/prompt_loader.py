"""
extraction.prompt_loader
========================
Loads the checked-in prompt contract from ``prompts/stance_extraction_prompt.md``
and renders it with article-specific context.

The prompt template lives at a fixed path relative to the
``statement-processor`` root so that the extractor always uses the
canonical contract and not ad hoc prompt strings.

Usage
-----
    from extraction.prompt_loader import load_prompt

    system_msg, user_msg = load_prompt(doc_id="art-001", article_text="…")
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

# The prompts/ directory is two levels above this file:
#   src/extraction/prompt_loader.py  →  ../../prompts/
_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"
_PROMPT_FILE = _PROMPTS_DIR / "stance_extraction_prompt.md"


def _get_prompt_path(prompt_path: Path | str | None = None) -> Path:
    """Return the resolved path to the prompt file.

    Parameters
    ----------
    prompt_path:
        Explicit override path.  If ``None``, the default checked-in path
        is used.
    """
    if prompt_path is not None:
        return Path(prompt_path).resolve()
    return _PROMPT_FILE.resolve()


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

# Regex: match the fenced code block containing the user prompt template.
# The template starts after ```  and ends before ```
_CODEBLOCK_RE = re.compile(r"```\s*\n(.*?)```", re.DOTALL)

# Heading that introduces the system instruction section
_SYSTEM_HEADING = "## System instruction"
# Heading that introduces the user prompt section
_USER_HEADING = "## User prompt template"


def _parse_prompt_file(raw: str) -> tuple[str, str]:
    """Extract system instruction and user prompt template from markdown.

    The prompt file follows this structure::

        ## System instruction

        <system text (plain text, not in a code block)>

        ## User prompt template

        ```
        <user prompt template>
        ```

    Parameters
    ----------
    raw:
        Full text of the prompt markdown file.

    Returns
    -------
    tuple[str, str]
        ``(system_instruction, user_template)`` both as plain strings.

    Raises
    ------
    ValueError
        If the expected headings or code block are not found.
    """
    # Split on the user-prompt heading to separate system from user sections.
    if _SYSTEM_HEADING not in raw:
        raise ValueError(
            f"Prompt file is missing the '{_SYSTEM_HEADING}' heading."
        )
    if _USER_HEADING not in raw:
        raise ValueError(
            f"Prompt file is missing the '{_USER_HEADING}' heading."
        )

    # System instruction: text between ## System instruction and ## User prompt template
    system_start = raw.index(_SYSTEM_HEADING) + len(_SYSTEM_HEADING)
    user_heading_start = raw.index(_USER_HEADING)
    system_raw = raw[system_start:user_heading_start].strip()

    # User template: the first fenced code block after ## User prompt template
    user_section = raw[user_heading_start + len(_USER_HEADING) :]
    code_match = _CODEBLOCK_RE.search(user_section)
    if not code_match:
        raise ValueError(
            "Prompt file is missing the fenced code block for the user "
            "prompt template."
        )
    user_template = code_match.group(1).rstrip()

    return system_raw, user_template


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_prompt(
    doc_id: str,
    article_text: str,
    prompt_path: Path | str | None = None,
) -> tuple[str, str]:
    """Load the prompt contract and render it with article-specific values.

    Parameters
    ----------
    doc_id:
        Unique identifier of the article.  Replaces the ``{{doc_id}}``
        placeholder in the user prompt template.
    article_text:
        Full text of the article (or a chunk thereof).  Replaces the
        ``{{article_text}}`` placeholder.
    prompt_path:
        Optional override path to the prompt markdown file.  Defaults to
        the checked-in ``prompts/stance_extraction_prompt.md``.

    Returns
    -------
    tuple[str, str]
        ``(system_message, user_message)`` ready to be passed to the LLM.

    Raises
    ------
    FileNotFoundError
        If the prompt file does not exist at the resolved path.
    ValueError
        If the prompt file is malformed (missing required sections).
    """
    path = _get_prompt_path(prompt_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Prompt file not found: {path}\n"
            "Expected at: prompts/stance_extraction_prompt.md"
        )

    raw = path.read_text(encoding="utf-8")
    system_instruction, user_template = _parse_prompt_file(raw)

    # Render placeholders
    user_message = user_template.replace("{{doc_id}}", doc_id).replace(
        "{{article_text}}", article_text
    )

    return system_instruction, user_message
