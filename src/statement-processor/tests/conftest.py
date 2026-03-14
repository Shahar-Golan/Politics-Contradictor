"""
conftest.py
===========
Pytest configuration for the statement-processor tests.

Adds ``statement-processor/src/`` to ``sys.path`` so that the ``db``
package can be imported without installing the project in editable mode.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC_DIR = Path(__file__).parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))
