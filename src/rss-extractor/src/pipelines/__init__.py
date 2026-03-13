"""
pipelines
=========
The Pipelines package orchestrates end-to-end Scout + Extractor flows.

Responsibilities:
- Combining Scout and Extractor components into coherent jobs
- Defining clear stage boundaries (fetch → parse → dedup → extract → store)
- Providing entry points for scheduled or on-demand runs

Pipeline modules should stay thin: delegate to Scout/Extractor/Storage components
and keep orchestration logic explicit and easy to follow.
"""
