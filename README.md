# Politics-Contradictor

An autonomous political intelligence system that monitors public figures, cross-references their statements (tweets) with news coverage, detects contradictions, and surfaces insights through an interactive query interface.

> **Current status:** Phase 1 (interactive query graph + real-time UI) is complete. Phases 2–5 (topic extraction, contradiction detection, figure pages, deployment) are planned but not yet implemented. See `docs/architecture.md` for the full roadmap.

---

## What it does

- **Interactive queries** — ask natural language questions about politicians; the system routes your question to the right specialist agent (tweet agent, news agent, or both) and streams the answer back in real time.
- **Multi-agent pipeline** — built with LangGraph, routing through page lookup → router → tweet/news agents.
- **Dual data sources** — ~52K tweet embeddings and ~400 news article embeddings in Pinecone, with structured data in Supabase.

---

## Quick start

### Prerequisites

- [Miniconda](https://docs.conda.io/en/latest/miniconda.html) or Anaconda
- Node.js 18+
- API access to Pinecone, Supabase, and the LLM endpoint (see Environment variables)

### 1. Set up the Python environment

```bash
conda env create -f environment.yml
conda activate politician-tracker
```

`environment.yml` is the single source of truth for all Python dependencies.

### 2. Configure environment variables

Create a `.env` file in the project root (never commit this file):

```env
OPENAI_API_KEY=your_key
BASE_URL=https://api.llmod.ai/v1
GPT_MODEL=RPRTHPB-gpt-5-mini
PINECONE_API_KEY=your_key
SUPABASE_URL=your_url
SUPABASE_KEY=your_key
```

Copy `.env.example` for the full list of required and optional variables.

### 3. Install frontend dependencies

```bash
cd frontend
npm install
```

### 4. Run the application

**Backend** (Terminal 1):
```bash
conda activate politician-tracker
python api/index.py
```

**Frontend** (Terminal 2):
```bash
cd frontend
npm run dev
```

Open `http://localhost:5173` in your browser.

---

## Documentation

| Document | Contents |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | System design, module boundaries, LangGraph systems, implementation phases |
| [`docs/data_model.md`](docs/data_model.md) | Supabase tables, local SQLite schema, Pinecone indexes, data flow |
| [`docs/development.md`](docs/development.md) | Local setup, coding conventions, type hinting requirements, test instructions, model configuration |
| [`docs/operations.md`](docs/operations.md) | API endpoints, configuration files, data ingestion, statement-processor workflow, CLI scripts |
| [`docs/migrations.md`](docs/migrations.md) | Schema change guidance for local SQLite and Supabase |
| [`docs/pr_boundaries.md`](docs/pr_boundaries.md) | Expected PR scope by pipeline component |
| [`src/statement-processor/README.md`](src/statement-processor/README.md) | statement-processor local workflow: database setup, CSV import, article selection, tests |
| [`src/statement-processor/docs/stance_extraction_contract.md`](src/statement-processor/docs/stance_extraction_contract.md) | Extraction contract: what the extractor consumes and emits, field definitions, controlled vocabularies |

---

## Project structure

```
Politics-Contradictor/
├── .github/
│   ├── copilot-instructions.md     # Copilot agent guidelines
│   └── pull_request_template.md    # PR checklist
├── api/
│   └── index.py                    # Flask API (all endpoints + SSE streaming)
├── docs/                           # Project documentation
├── frontend/                       # React UI (Vite)
├── src/
│   ├── agents/                     # LangGraph agent node implementations
│   ├── agent_tools/                # Shared reusable tool functions
│   ├── graphs/                     # LangGraph StateGraph definitions
│   ├── rss-extractor/              # RSS ingestion module
│   └── statement-processor/        # Local-first extraction pipeline (offline, SQLite)
├── test/                           # Tests and utilities
├── .env.example                    # Environment variable reference
├── environment.yml                 # Conda environment (source of truth)
└── requirements.txt                # pip fallback
```

---

## Contributing

Before opening a PR, read:

- [`.github/copilot-instructions.md`](.github/copilot-instructions.md) — coding standards, type hinting requirements, layer boundaries, documentation expectations.
- [`.github/pull_request_template.md`](.github/pull_request_template.md) — the PR checklist every contributor should follow.

Key expectations:

- All new Python code must use **extensive type hints** (typed signatures, return types, typed domain models).
- Keep PRs narrow in scope — one logical change per PR.
- Update the relevant `docs/` files in the same PR as any behaviour, schema, or workflow change.
- All dependency changes go through `environment.yml`.

---

## Author

**Shahar Golan** — [GitHub](https://github.com/Shahar-Golan) 