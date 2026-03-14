# Copilot Instructions — Politics-Contradictor

## Project context

Politics-Contradictor is an autonomous political intelligence system that monitors public figures, cross-references their statements with news coverage, detects contradictions, and surfaces insights through an interactive query interface.

The system has two major runtime modes:
- **System A** — a scheduled background pipeline (ingestion → topic extraction → contradiction detection → page building)
- **System B** — an on-demand interactive query graph that routes user questions to specialist agents (tweet agent, news agent, or both)

The backend is a Flask API. The frontend is React (Vite). Agent logic is built with LangGraph. Data lives in Supabase (PostgreSQL) and Pinecone (vector search).

---

## Architecture and module boundaries

Keep code in the layer it belongs to:

| Folder | Purpose |
|---|---|
| `src/graphs/` | LangGraph `StateGraph` definitions — wire agents together, no business logic |
| `src/agents/` | Agent node implementations — each file is one agent, calls tools and LLM |
| `src/agent_tools/` | Shared, reusable tool functions (Pinecone search, web scraping, URL extraction) |
| `src/rss-extractor/` | RSS ingestion module — scrapes feeds, exports to CSV and Supabase |
| `src/statement-processor/` | Local-first extraction pipeline — local SQLite schema, CSV ingestion, article selection, stance extraction contract; runs offline before Supabase integration |
| `api/` | Flask application — HTTP handlers and SSE streaming only, no business logic |
| `frontend/` | React UI — display and interaction only |
| `test/` | All tests — unit tests, integration scripts, utilities |

**Do not mix layers.** Business logic belongs in `src/agents/` and `src/agent_tools/`, not in `api/index.py`. LangGraph wiring belongs in `src/graphs/`, not in agent files.

---

## Environment management

The project uses **conda** with `environment.yml` as the single source of truth for dependencies and Python version.

- **Always update `environment.yml`** when adding or removing a dependency.
- Do not introduce `requirements.txt`-only changes for new dependencies — keep both files consistent if `requirements.txt` is also present.
- Do not pin versions unless there is a known incompatibility.
- The Python version is **3.13**. Do not raise or lower it without discussion.

To recreate the environment:
```bash
conda env create -f environment.yml
conda activate politician-tracker
```

---

## Type hinting requirements

All new and modified Python code **must** use extensive type hints. This is not optional.

Specific requirements:
- Every public function and method must have fully typed signatures — parameters and return type.
- Use `->` return type annotations on all functions, including those returning `None`.
- Use typed domain models (`dataclass`, `TypedDict`, or Pydantic models) for structured data passed between components.
- Prefer modern Python typing syntax: `list[str]` over `List[str]`, `dict[str, Any]` over `Dict[str, Any]`, `X | Y` over `Optional[X]` or `Union[X, Y]` (Python 3.10+).
- Never expose untyped public APIs.
- Private helpers should also be typed where practical.
- Use `Any` sparingly and only when the type genuinely cannot be constrained.

Example of the expected style:
```python
def search_tweets(query: str, top_k: int = 7) -> list[dict[str, Any]]:
    ...
```

---

## Testing expectations

- New agent behaviour must be covered by tests in `test/`.
- Tests must not rely on live external services (Pinecone, Supabase, OpenAI). Mock or patch them.
- Follow the existing `unittest` style used in `test/test_endpoints.py`.
- Tests for API endpoints go in `test/test_endpoints.py` or a dedicated parallel file.
- Tests for agent logic go in dedicated files, e.g. `test/test_router.py`.

---

## Documentation requirements

Documentation is not optional. When you change behaviour, workflow, architecture, configuration, data models, or developer setup, you **must** update the relevant docs in the same PR:

- Architecture changes → `docs/architecture.md`
- Data model changes (Supabase schema, Pinecone metadata) → `docs/data_model.md`
- Setup or environment changes → `docs/development.md` and `README.md`
- Operational workflow changes → `docs/operations.md`
- PR template and Copilot instructions → `.github/`

---

## Configuration expectations

- All secrets and runtime config go in `.env`. Never hardcode API keys.
- The `.env` file is never committed. `.env.example` is preferred for documenting required keys.
- Configuration constants used across multiple files should be centralised — not duplicated.
- YAML config files in `src/rss-extractor/config/` control politicians, feeds, and topics — update them when those lists change.

---

## Maintainability and separation of concerns

- Each agent file (`src/agents/`) should do one thing: call tools, call the LLM, return a result.
- Graph files (`src/graphs/`) should only wire nodes and edges — no LLM calls directly.
- Tool files (`src/agent_tools/`) should be stateless, reusable functions.
- Flask route handlers in `api/index.py` should be thin: validate input, call graph/agent, return response.
- Keep PR scope narrow. One logical change per PR.
- Prefer explicit over implicit. Avoid magic.

---

## Implementation phases (current state)

- **Phase 1** (System B — interactive query + UI): **COMPLETE**
- **Phase 1.5** (statement-processor — local SQLite foundation, article selection, extraction contract): **COMPLETE**
- **Phase 2** (Topic Extraction): NOT STARTED
- **Phase 3** (Contradiction Detection): NOT STARTED
- **Phase 4** (Figure Pages + full System A): NOT STARTED
- **Phase 5** (Deployment and automation): NOT STARTED

When implementing a new phase, follow the data model in `docs/data_model.md` and update `docs/architecture.md` as you go.

---

## PR boundaries

Keep PRs narrow and focused. See `docs/pr_boundaries.md` for the expected scope
of each pipeline component. Key rules:

- One logical component per PR.
- Update docs in the same PR as behaviour changes.
- Update tests in the same PR as code changes.
- Do not mix schema changes with unrelated refactors.
- Keep CLI scripts thin — business logic belongs in `src/`, not in `scripts/`.
