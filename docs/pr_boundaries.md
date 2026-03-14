# PR Boundaries — Politics-Contradictor

## Overview

Keep pull requests narrow and focused. One logical change per PR makes code
easier to review, safer to merge, and simpler to revert if something goes wrong.

This document describes the expected scope boundaries for each major pipeline
component. Use it when deciding what to include in — or exclude from — a PR.

---

## General rules

- **One logical component per PR.** Do not combine a schema change with an
  unrelated refactor, or mix an agent change with a new CLI flag.
- **Update docs in the same PR as behaviour changes.** If you change a schema,
  update `docs/data_model.md`. If you change the extraction contract, update
  `src/statement-processor/docs/stance_extraction_contract.md`. Documentation
  PRs are not second-class.
- **Update tests in the same PR as code changes.** A PR that changes behaviour
  without updating tests is incomplete.
- **Keep CLI wrappers thin.** CLI scripts in `scripts/` should delegate to
  library functions in `src/`. Business logic belongs in `src/`, not in scripts.
- **Avoid cross-layer changes.** Do not move business logic into graph files
  or API route handlers. See `docs/architecture.md` for layer boundaries.

---

## PR boundaries by component

### 1. Schema / migrations

**Scope:** changes to `src/statement-processor/src/db/schema.sql` or the
Supabase schema.

**Include in the same PR:**
- The schema change itself
- Updated `docs/data_model.md`
- Updated `src/statement-processor/docs/stance_extraction_contract.md`
  (if the change affects extraction output)
- Updated tests for the new structure
- Updated fixtures if the contract changed

**Do not mix with:**
- Unrelated code refactors
- New agent logic
- Frontend changes

---

### 2. Prompt / contract changes

**Scope:** changes to `src/statement-processor/prompts/stance_extraction_prompt.md`,
`src/statement-processor/schemas/stance_extraction.schema.json`, or
`src/statement-processor/src/contracts/vocab.json`.

**Include in the same PR:**
- The prompt or schema change
- Updated `src/statement-processor/docs/stance_extraction_contract.md`
- Updated test fixtures under `tests/fixtures/`
- Updated `test_contract.py` if validation logic changes

**Do not mix with:**
- Schema/migration changes
- Selection logic changes
- Unrelated refactors

---

### 3. Article selection

**Scope:** changes to `src/statement-processor/src/selection/` (keywords,
scoring rules, models, article selector).

**Include in the same PR:**
- The selection logic change
- Updated `test_article_selection.py`
- Updated `src/statement-processor/README.md` (scoring table, usage examples)
  if the behaviour changes visibly

**Do not mix with:**
- Schema changes
- Extraction logic
- Prompt changes

---

### 4. Extraction logic (PLANNED)

**Scope:** the LLM-backed stance extractor (future implementation in
`src/agents/stance_extractor.py` or equivalent).

**Include in the same PR:**
- The extractor agent implementation
- Tests (mocked LLM calls — no live API calls in tests)
- Updated `docs/architecture.md` if a new agent is added
- Updated `docs/data_model.md` if extraction output populates new fields

**Do not mix with:**
- Prompt/contract changes (make those in a separate PR first)
- Schema changes
- Validation/normalisation

---

### 5. Validation / normalisation

**Scope:** code that validates extractor output against the JSON schema and
normalises fields before database insertion.

**Include in the same PR:**
- The validator or normaliser logic
- Tests for the validator
- Updated contract docs if validation rules change

**Do not mix with:**
- Extraction logic
- Persistence / deduplication logic

---

### 6. Persistence / deduplication

**Scope:** code that writes `stance_records` and `stance_relations` to the
local SQLite or Supabase database.

**Include in the same PR:**
- The persistence layer implementation
- Tests (using a fixture/in-memory database — no live Supabase calls in tests)
- Updated `docs/data_model.md` if new insert patterns are introduced

**Do not mix with:**
- Validation logic
- Query layer logic

---

### 7. Relation generation (PLANNED)

**Scope:** code that computes pairwise relations between `stance_records`
and writes them to `stance_relations`.

**Include in the same PR:**
- The relation generation logic
- Tests
- Updated `docs/data_model.md` if `stance_relations` schema evolves

**Do not mix with:**
- Contradiction detection (separate logical step)
- Dossier generation

---

### 8. Dossier query layer (PLANNED)

**Scope:** functions that query `stance_records` and `stance_relations` to
produce per-figure summaries or contradiction reports.

**Include in the same PR:**
- Query functions with typed signatures
- Tests against fixture data

**Do not mix with:**
- Dossier rendering / report generation
- Persistence layer

---

### 9. Dossier / report generation (PLANNED)

**Scope:** code that formats query results into human-readable output (text,
JSON, or HTML reports).

**Include in the same PR:**
- The generation logic
- Tests with fixture inputs
- Updated `docs/operations.md` if a new CLI entrypoint is added

**Do not mix with:**
- Dossier query layer
- LangGraph integration

---

### 10. LangGraph integration (PLANNED)

**Scope:** wiring new agents (stance extractor, contradiction finder, page
builder) into the LangGraph background pipeline graph
(`src/graphs/background_graph.py`).

**Include in the same PR:**
- The graph wiring change (nodes and edges only — no business logic in graph files)
- Updated `docs/architecture.md`

**Do not mix with:**
- Agent implementation (make that in a separate PR first)
- API changes

---

### 11. Flask API changes

**Scope:** new or modified endpoints in `api/index.py`.

**Include in the same PR:**
- The endpoint change
- Tests in `test/test_endpoints.py` or a parallel file
- Updated `docs/operations.md`

**Do not mix with:**
- Agent or tool logic (those changes belong in `src/agents/` or `src/agent_tools/`)
- Frontend changes

---

### 12. Frontend changes

**Scope:** React components, styles, or Vite configuration in `frontend/`.

**Include in the same PR:**
- The frontend change
- Any updated `docs/operations.md` if user-visible behaviour changes

**Do not mix with:**
- Backend / API changes (unless tightly coupled and small)

---

### 13. RSS / ingestion changes

**Scope:** changes to `src/rss-extractor/` (feed scraping, CSV export,
Supabase push).

**Include in the same PR:**
- The ingestion change
- Updated config files under `src/rss-extractor/config/` if politicians or
  feeds change
- Updated `docs/operations.md`

**Do not mix with:**
- Statement-processor changes
- LangGraph pipeline changes

---

### 14. Docs / config-only changes

**Scope:** documentation, configuration examples, `.env.example`, or
`environment.yml` updates with no code behaviour changes.

These PRs are low-risk and can be reviewed quickly. Still keep them focused —
one documentation area per PR where possible.

**Examples:**
- Updating `docs/architecture.md` to reflect a newly implemented phase
- Adding a new section to `docs/development.md`
- Updating `.env.example` with a new variable
- Fixing typos or broken links across multiple docs (acceptable to batch)

---

## When to deviate

Sometimes a change is genuinely coupled across components. For example, adding
a new required field to `stance_records` requires schema, contract, tests, and
docs to change together. That is acceptable — the goal is _logical_ cohesion,
not enforced minimalism.

When a PR crosses multiple components:

1. Say so explicitly in the PR summary.
2. Group commits logically (schema → contract → code → tests → docs).
3. Keep the total diff reviewable — if it grows too large, split out the
   least-coupled parts.
