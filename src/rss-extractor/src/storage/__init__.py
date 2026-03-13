"""
storage
=======
The Storage package handles persistence of feed items, raw articles,
extracted records, and vector export preparation.

Responsibilities:
- Domain schema definitions
- SQL/database interaction helpers
- Document storage interface (filesystem or object store)
- Vector export formatting for downstream retrieval

This package does NOT contain parsing, extraction, or pipeline orchestration logic.
"""
