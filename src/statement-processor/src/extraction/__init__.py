"""
extraction
==========
LLM-based stance extractor for the statement-processor pipeline.

Public API re-exports for convenient imports:

    from extraction.extractor import extract_articles, extract_single_article
    from extraction.models import ArticleInput, ExtractionResult
    from extraction.chunking import chunk_article
    from extraction.prompt_loader import load_prompt
    from extraction.debug_logger import DebugLogger
    from extraction.client import LLMClient
"""

from __future__ import annotations

from .client import LLMClient
from .chunking import chunk_article
from .debug_logger import DebugLogger
from .extractor import extract_articles, extract_single_article
from .models import (
    ArticleInput,
    CandidateStanceEvent,
    ChunkInput,
    ExtractionConfig,
    ExtractionResult,
    RawExtractionOutput,
)
from .prompt_loader import load_prompt

__all__ = [
    "ArticleInput",
    "CandidateStanceEvent",
    "ChunkInput",
    "ExtractionConfig",
    "ExtractionResult",
    "LLMClient",
    "RawExtractionOutput",
    "chunk_article",
    "DebugLogger",
    "extract_articles",
    "extract_single_article",
    "load_prompt",
]
