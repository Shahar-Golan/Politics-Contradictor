"""
extraction.debug_logger
=======================
Structured debug/intermediate logging for the stance extraction pipeline.

Every extraction request – successful or failed – is written to a JSONL
file so that extraction behaviour is fully inspectable after the fact.

Each line of the JSONL file is one :class:`~extraction.models.RawExtractionOutput`
serialised to a flat JSON object.

Usage
-----
    from extraction.debug_logger import DebugLogger
    from extraction.models import RawExtractionOutput

    logger = DebugLogger(log_path=Path("data/debug/extraction_debug.jsonl"))
    logger.log(raw_output)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from .models import RawExtractionOutput

_module_logger = logging.getLogger(__name__)

# Default debug log location relative to the statement-processor root.
_DEFAULT_LOG_PATH = (
    Path(__file__).parent.parent.parent / "data" / "debug" / "extraction_debug.jsonl"
)


class DebugLogger:
    """Writes :class:`~extraction.models.RawExtractionOutput` records to a
    JSONL file.

    Parameters
    ----------
    log_path:
        Path to the JSONL output file.  Parent directories are created
        automatically.  If ``None``, the default path
        ``data/debug/extraction_debug.jsonl`` is used.
    enabled:
        If ``False``, all ``log`` calls are silently ignored (useful in
        tests that do not want file I/O).
    """

    def __init__(
        self,
        log_path: Optional[Path | str] = None,
        enabled: bool = True,
    ) -> None:
        self._enabled = enabled
        if log_path is None:
            self._path = _DEFAULT_LOG_PATH.resolve()
        else:
            self._path = Path(log_path).resolve()

    @property
    def path(self) -> Path:
        """Resolved path to the debug log file."""
        return self._path

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def log(self, output: RawExtractionOutput) -> None:
        """Append *output* as a single JSON line to the log file.

        Parameters
        ----------
        output:
            The raw extraction output to record.
        """
        if not self._enabled:
            return

        record = _raw_output_to_dict(output)
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as exc:
            _module_logger.warning(
                "DebugLogger: failed to write to %s: %s", self._path, exc
            )


# ---------------------------------------------------------------------------
# Serialisation helper
# ---------------------------------------------------------------------------


def _raw_output_to_dict(output: RawExtractionOutput) -> dict[str, Any]:
    """Convert a :class:`~extraction.models.RawExtractionOutput` to a plain
    ``dict`` suitable for JSON serialisation.

    Parameters
    ----------
    output:
        The raw extraction output to convert.

    Returns
    -------
    dict[str, Any]
        A JSON-serialisable flat dictionary.
    """
    return {
        "doc_id": output.doc_id,
        "chunk_index": output.chunk_index,
        "chunk_total": output.chunk_total,
        "model_name": output.model_name,
        "raw_response": output.raw_response,
        "parsed_json": output.parsed_json,
        "parse_error": output.parse_error,
        "extraction_timestamp": output.extraction_timestamp,
        "title": output.title,
        "date": output.date,
        "link": output.link,
        "attempt_number": output.attempt_number,
    }
