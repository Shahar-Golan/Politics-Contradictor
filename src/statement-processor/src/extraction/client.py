"""
extraction.client
=================
LLM provider wrapper for the stance extraction pipeline.

This module isolates all provider-specific API code so that the rest of the
extractor never imports from ``openai`` directly.  Swapping providers only
requires changes here.

The client:
- reads the API key and model configuration from the environment / an
  :class:`~extraction.models.ExtractionConfig`,
- sends a structured chat completion request (system + user messages),
- returns the raw text content of the first response choice,
- raises typed exceptions on API and timeout failures.

Usage
-----
    from extraction.client import LLMClient
    from extraction.models import ExtractionConfig

    client = LLMClient(config=ExtractionConfig(model_name="gpt-4o-mini"))
    raw_text = client.complete(system_message="…", user_message="…")
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from .models import ExtractionConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class LLMClientError(Exception):
    """Raised when the LLM provider returns an unrecoverable error."""


class LLMTimeoutError(LLMClientError):
    """Raised when the LLM request times out."""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class LLMClient:
    """Thin wrapper around the OpenAI chat completions API.

    Parameters
    ----------
    config:
        :class:`~extraction.models.ExtractionConfig` containing model name
        and temperature settings.
    api_key:
        OpenAI API key.  If ``None``, the key is read from the
        ``OPENAI_API_KEY`` environment variable.

    Raises
    ------
    LLMClientError
        If the ``openai`` package is not installed.
    """

    def __init__(
        self,
        config: Optional[ExtractionConfig] = None,
        api_key: Optional[str] = None,
    ) -> None:
        try:
            import openai  # noqa: F401 - imported to verify availability
            from openai import OpenAI
        except ImportError as exc:
            raise LLMClientError(
                "The 'openai' package is required for LLM extraction. "
                "Install it with: pip install openai"
            ) from exc

        self._config = config or ExtractionConfig()
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._client = OpenAI(api_key=self._api_key)

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def complete(
        self,
        system_message: str,
        user_message: str,
    ) -> str:
        """Send a chat completion request and return the raw response text.

        Parameters
        ----------
        system_message:
            The system role message (extractor instruction).
        user_message:
            The user role message (rendered prompt with article text).

        Returns
        -------
        str
            The raw text content of the first response choice.  May be
            empty or malformed JSON – callers must handle both cases.

        Raises
        ------
        LLMTimeoutError
            If the request times out.
        LLMClientError
            On any other provider/API error.
        """
        try:
            import openai

            response = self._client.chat.completions.create(
                model=self._config.model_name,
                temperature=self._config.temperature,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message},
                ],
            )
        except openai.APITimeoutError as exc:
            raise LLMTimeoutError(
                f"OpenAI request timed out: {exc}"
            ) from exc
        except openai.APIError as exc:
            raise LLMClientError(
                f"OpenAI API error: {exc}"
            ) from exc

        choices = response.choices
        if not choices:
            return ""

        content = choices[0].message.content
        return content if content is not None else ""
