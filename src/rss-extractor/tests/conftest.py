"""
conftest.py
===========
Pytest configuration for the merge-ready package tests.

Adds ``merge_ready/src/`` to ``sys.path`` so that packages can be imported
without installing the project in editable mode.
"""

import sys
from pathlib import Path

_SRC_DIR = Path(__file__).parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))
