# Development Guide — Politics-Contradictor

## Prerequisites

- [Miniconda](https://docs.conda.io/en/latest/miniconda.html) or Anaconda
- Node.js 18+
- Access to the required external services (see Environment variables below)

---

## Local setup

### 1. Clone the repository

```bash
git clone https://github.com/Shahar-Golan/Politics-Contradictor.git
cd Politics-Contradictor
```

### 2. Create and activate the conda environment

`environment.yml` is the single source of truth for the Python environment.

```bash
conda env create -f environment.yml
conda activate politician-tracker
```

To update an existing environment after `environment.yml` changes:

```bash
conda env update -f environment.yml --prune
```

### 3. Configure environment variables

Create a `.env` file in the project root. Never commit this file.

```env
OPENAI_API_KEY=your_key
BASE_URL=https://api.llmod.ai/v1
GPT_MODEL=RPRTHPB-gpt-5-mini
PINECONE_API_KEY=your_key
SUPABASE_URL=your_url
SUPABASE_KEY=your_key
```

See `.env.example` in the repository root for the full list of required and optional variables, including statement-processor-specific settings.

### 4. Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

---

## Running the application

### Backend (Flask API)

```bash
conda activate politician-tracker
python api/index.py
```

The API will be available at `http://localhost:5000`.

### Frontend (React + Vite)

```bash
cd frontend
npm run dev
```

The frontend runs at `http://localhost:5173` and proxies API calls to `http://localhost:5000`.

### Running both together

Open two terminals:

**Terminal 1 — backend:**
```bash
conda activate politician-tracker
python api/index.py
```

**Terminal 2 — frontend:**
```bash
cd frontend
npm run dev
```

Then open `http://localhost:5173`.

---

## Running tests

```bash
conda activate politician-tracker
python -m pytest test/ -v
```

Tests must not rely on live external services. Mock or patch Pinecone, Supabase, and OpenAI calls. Follow the `unittest` + `mock` style used in `test/test_endpoints.py`.

### statement-processor tests

The statement-processor module has its own test suite:

```bash
cd src/statement-processor
pytest tests/ -v
```

Or from the repository root:

```bash
pytest src/statement-processor/tests/ -v
```

These tests run entirely offline — no API keys or external services required.

---

## statement-processor local workflow

The `src/statement-processor/` directory is a self-contained local pipeline.
It runs entirely offline using SQLite — no Supabase, Pinecone, or LLM access
required.

### 1. Initialise the local database

```bash
cd src/statement-processor
python scripts/init_local_db.py
```

This creates `data/political_dossier.db` with three tables: `news_articles`,
`stance_records`, and `stance_relations`.

### 2. Import news articles from CSV

Export `news_articles` from Supabase (or another source) and place the file at
`src/statement-processor/data/news_articles.csv`, then run:

```bash
python scripts/import_news_articles_csv.py
```

### 3. Run article selection

```bash
python scripts/select_candidate_articles.py --politicians Trump Biden
```

See `src/statement-processor/README.md` for the full range of options.

### 4. Run the tests

```bash
pytest tests/ -v
```

See `src/statement-processor/README.md` for full workflow details.

---

## Model configuration

The project uses an **OpenAI-compatible endpoint** provided by
[llmod.ai](https://llmod.ai) rather than the direct OpenAI API.

### Where models are configured

| Variable | Purpose | Default |
|---|---|---|
| `OPENAI_API_KEY` | API key for llmod.ai (not a direct OpenAI key) | Required |
| `BASE_URL` | LLM endpoint base URL | `https://api.llmod.ai/v1` |
| `GPT_MODEL` | Chat completion model name | `RPRTHPB-gpt-5-mini` |

All three variables must be set in `.env`. See `.env.example` for the full list.

### Which pipeline components use LLMs

| Component | Uses LLM? | Notes |
|---|---|---|
| System B router | ✅ Yes | Classifies user queries as `tweet` / `news` / `both` |
| System B tweet agent | ✅ Yes | Answers questions using Pinecone tweet search |
| System B news agent | ✅ Yes | Answers questions using Pinecone news search |
| Article selection | ❌ No | Deterministic rule-based scoring, no LLM |
| CSV ingestion | ❌ No | Pure data normalisation |
| DB schema bootstrap | ❌ No | Pure SQL |
| Stance extractor (planned) | ✅ Yes | Will call the LLM to extract stance events from articles |
| Contradiction finder (planned) | ✅ Yes | Will compare stances using the LLM |
| Page builder (planned) | ✅ Yes | Will synthesise per-figure summaries |

### Changing the model

1. Update `GPT_MODEL` in `.env` to the new model name.
2. If switching providers (not just model names), also update `BASE_URL` and
   `OPENAI_API_KEY`.
3. The model name uses a vendor-specific `RPRTHPB-` prefix on the llmod.ai
   endpoint — this prefix selects the underlying model on that platform.
4. Verify the change works by running the interactive query endpoint manually
   before opening a PR.

### Cost and latency notes

- All LLM calls currently go through llmod.ai, not direct OpenAI.
- Local development (article selection, DB bootstrap, CSV import) uses no LLM
  calls and incurs no cost.
- The stance extractor (planned) will process articles one at a time. Cost and
  latency per article will depend on article length and the chosen model.

---

## Adding a dependency

1. Add the package to `environment.yml` under `pip:`.
2. Update the environment:
   ```bash
   conda env update -f environment.yml --prune
   ```
3. If `requirements.txt` is also present in the project, keep it consistent with `environment.yml`.
4. Update `docs/development.md` and `README.md` if the setup process changes.

Do not add packages outside `environment.yml`.

---

## Coding conventions

### Type hints (required)

All new and modified Python code must use extensive type hints:

- Every public function must have fully typed parameters and a `->` return type.
- Use typed domain models (`dataclass`, `TypedDict`, or Pydantic) for structured data.
- Use modern Python 3.10+ syntax: `list[str]`, `dict[str, Any]`, `X | Y` (not `List`, `Dict`, `Optional`, `Union`).
- Never expose untyped public APIs.
- Use `Any` sparingly and only when the type genuinely cannot be constrained.

```python
# Good
def search_tweets(query: str, top_k: int = 7) -> list[dict[str, Any]]:
    ...

# Bad — no type hints
def search_tweets(query, top_k=7):
    ...
```

### Docstrings

Public functions and classes should have docstrings describing their purpose, parameters, and return values. Follow the style already present in the file you are editing.

### Layer separation

See `docs/architecture.md` for module responsibilities. Do not cross layers:
- No LLM calls in `api/index.py`.
- No business logic in graph files.
- No HTTP concerns in agent or tool files.

### Naming

- Python: `snake_case` for functions, variables, modules; `PascalCase` for classes.
- React: `PascalCase` for components; `camelCase` for functions and variables.

---

## Updating documentation

Whenever you change behaviour, workflow, architecture, configuration, data models, or developer setup, update the relevant docs in the same PR:

| What changed | File to update |
|---|---|
| Module structure or agent design | `docs/architecture.md` |
| Supabase schema or Pinecone metadata | `docs/data_model.md` |
| Setup, environment, or coding conventions | `docs/development.md` + `README.md` |
| Operational workflow or CLI entrypoints | `docs/operations.md` |
| Contribution or Copilot standards | `.github/copilot-instructions.md` |

Documentation PRs are not second-class. Keep docs synchronised with code.

---

## Project structure reference

```
Politics-Contradictor/
├── .github/
│   ├── copilot-instructions.md     # Copilot agent guidelines
│   └── pull_request_template.md    # PR checklist
├── api/
│   └── index.py                    # Flask API
├── docs/
│   ├── architecture.md
│   ├── data_model.md
│   ├── development.md              # This file
│   ├── migrations.md               # Schema change guidance
│   ├── operations.md
│   └── pr_boundaries.md            # PR scope guidance by component
├── frontend/                       # React (Vite)
├── src/
│   ├── agents/                     # LangGraph agent node implementations
│   ├── agent_tools/                # Shared reusable tool functions
│   ├── graphs/                     # LangGraph StateGraph definitions
│   ├── rss-extractor/              # RSS ingestion module
│   └── statement-processor/        # Local-first extraction pipeline (offline, SQLite)
│       ├── docs/                   # Contract and schema documentation
│       ├── prompts/                # Prompt templates
│       ├── schemas/                # JSON Schema for LLM output validation
│       ├── scripts/                # Developer entry points
│       ├── src/                    # Python library code
│       └── tests/                  # Pytest test suite (runs offline)
├── test/                           # Tests and utilities for the Flask API
├── .env.example                    # Environment variable reference (copy to .env)
├── environment.yml                 # Conda environment (source of truth)
├── requirements.txt                # pip fallback (keep consistent with environment.yml)
└── README.md
```
