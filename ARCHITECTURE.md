# Politics-Contradictor — System Architecture

## Overview

An autonomous political intelligence network that monitors 8 public figures, cross-references their statements (tweets) with local news coverage, detects contradictions, and maintains live per-figure profile pages.

### Tracked Figures

Donald Trump, Hillary Clinton, Barack Obama, Joe Biden, Kamala Harris, Elon Musk, Bill Gates, Mark Zuckerberg

---

## System Architecture

Two independent LangGraph systems that share the same data layer.

### System A — Background Pipeline (scheduled daily)

Autonomous batch pipeline that ingests data, analyzes it, and builds cached figure pages.

```
START
  ↓
Ingestion Agent       → finds and loads new tweets/articles into Supabase + Pinecone
  ↓
Topic Extractor       → tags new records with topics (healthcare, economy, climate, etc.)
  ↓
Contradiction Finder  → compares tweets vs news coverage per figure/topic
  ↓
Page Builder          → generates per-figure summary pages, writes to Supabase
  ↓
END
```

Each node reads from Supabase, calls the LLM, and writes results back. No user interaction.

### System B — Interactive Query (on-demand, user-facing)

Handles user questions via a router pattern with cached-first strategy.

```
START
  ↓
Page Lookup           → searches figure_pages in Supabase for cached answer
  ↓ (conditional)
  ├── SUFFICIENT      → synthesize answer from cached page data → END
  └── INSUFFICIENT
        ↓
      Router           → LLM classifies query → "tweet" / "news" / "both"
        ↓ (conditional)
        ├── Tweet Agent  → live search politics index (Pinecone) → END
        ├── News Agent   → live search politics-news index (Pinecone) → END
        └── Both Agents  → parallel search both indexes → END
```

---

## Agent Descriptions

### System A — Background Agents

| Agent | Job | Input | Output |
|---|---|---|---|
| **Ingestion Agent** | Finds and loads new data (tweets, news articles) | External data sources | New records in `tweets` / `news_articles` tables + Pinecone vectors |
| **Topic Extractor** | Tags articles/tweets with topics (healthcare, economy, etc.) | New untagged records | Topic tags in `article_topics` / `tweet_topics` tables |
| **Contradiction Finder** | Compares figure's statements vs news coverage, past vs present positions | Tweets + news for same figure/topic | Contradiction reports in `contradictions` table |
| **Page Builder** | Synthesizes all data into a readable per-figure profile page | All analysis data for a figure | Updated page in `figure_pages` table |

### System B — Interactive Agents

| Agent | Job | Input | Output |
|---|---|---|---|
| **Page Lookup** | Checks pre-built figure pages for a cached answer | User query | Cached page data (or "insufficient" signal) |
| **Router** | Classifies query and decides which RAG agent to use | User query + page lookup result | Route decision: "tweet" / "news" / "both" |
| **Tweet Agent** | Expert in short responses, rivalry between politicians, direct quotes | User query | Answer sourced from tweets |
| **News Agent** | Expert in detailed opinions, comprehensive analysis, regional coverage | User query | Answer sourced from news articles |

---

## Data Layer

### Supabase Tables

```
EXISTING
────────────────────────────────────────────────────────────────
tweets
  tweet_id            TEXT PRIMARY KEY
  account_id          TEXT
  author_name         TEXT
  text                TEXT
  created_at          TIMESTAMPTZ
  has_urls            BOOLEAN

news_articles
  id                  SERIAL PRIMARY KEY
  doc_id              TEXT UNIQUE NOT NULL
  title               TEXT
  text                TEXT NOT NULL
  date                TEXT
  media_name          TEXT
  media_type          TEXT          -- newspaper / radio / tv / broadcast
  source_platform     TEXT          -- Google / Twitter
  state               TEXT
  city                TEXT
  link                TEXT
  speakers_mentioned  TEXT[]
  created_at          TIMESTAMPTZ DEFAULT NOW()

PHASE 2 — Topic Extraction
────────────────────────────────────────────────────────────────
topics
  id                  SERIAL PRIMARY KEY
  name                TEXT UNIQUE NOT NULL    -- "healthcare", "economy", "climate"
  description         TEXT

tweet_topics
  tweet_id            TEXT REFERENCES tweets(tweet_id)
  topic_id            INTEGER REFERENCES topics(id)
  confidence          FLOAT
  PRIMARY KEY (tweet_id, topic_id)

article_topics
  doc_id              TEXT REFERENCES news_articles(doc_id)
  topic_id            INTEGER REFERENCES topics(id)
  confidence          FLOAT
  PRIMARY KEY (doc_id, topic_id)

NOTE: Topic Extractor also updates existing records for faster RAG filtering:
  - Adds `topics TEXT[]` column to `tweets` table
  - Adds `topics TEXT[]` column to `news_articles` table
  - Updates Pinecone vector metadata with `topics: ["healthcare", "economy", ...]`
  This allows Tweet Agent / News Agent to do filtered vector search:
    index.query(vector=emb, filter={"topics": {"$in": ["healthcare"]}})

PHASE 3 — Contradiction Detection
────────────────────────────────────────────────────────────────
contradictions
  id                  SERIAL PRIMARY KEY
  figure_name         TEXT NOT NULL
  topic_id            INTEGER REFERENCES topics(id)
  tweet_id            TEXT                    -- source tweet (nullable)
  doc_id              TEXT                    -- source article (nullable)
  contradiction_type  TEXT                    -- "tweet_vs_news", "past_vs_present"
  explanation         TEXT NOT NULL
  severity            TEXT                    -- "minor", "major"
  detected_at         TIMESTAMPTZ DEFAULT NOW()

PHASE 4 — Figure Pages
────────────────────────────────────────────────────────────────
figure_pages
  id                  SERIAL PRIMARY KEY
  figure_name         TEXT UNIQUE NOT NULL
  overview            TEXT                    -- general summary
  top_topics          JSONB                   -- [{topic, stance, evidence}]
  recent_news         JSONB                   -- [{title, date, source, summary}]
  recent_tweets       JSONB                   -- [{text, date}]
  contradictions      JSONB                   -- [{type, explanation, evidence}]
  last_updated        TIMESTAMPTZ DEFAULT NOW()

INFRASTRUCTURE
────────────────────────────────────────────────────────────────
agent_runs
  id                  SERIAL PRIMARY KEY
  agent_name          TEXT NOT NULL
  status              TEXT                    -- "running", "completed", "failed"
  records_processed   INTEGER DEFAULT 0
  error_message       TEXT
  started_at          TIMESTAMPTZ DEFAULT NOW()
  completed_at        TIMESTAMPTZ
```

### Pinecone Indexes

| Index | Dimension | Metric | Content | Vectors |
|---|---|---|---|---|
| `politics` | 1024 | cosine | Tweet embeddings | ~52K |
| `politics-news` | 1024 | cosine | News article embeddings | ~400 (subset) |

Both use embedding model `RPRTHPB-text-embedding-3-small` via `https://api.llmod.ai/v1`.

---

## Tech Stack

| Component | Technology |
|---|---|
| Agent framework | LangGraph |
| LLM | `RPRTHPB-gpt-5-mini` via `api.llmod.ai` |
| Embeddings | `RPRTHPB-text-embedding-3-small` (1024-dim) via `api.llmod.ai` |
| Vector DB | Pinecone (serverless, AWS us-east-1) |
| SQL DB | Supabase (PostgreSQL) |
| Backend API | Flask |
| Frontend | React (Vite) |
| Deployment | Render |

---

## Project Structure

```
Politics-Contradictor/
├── src/
│   ├── graphs/                         # LangGraph definitions
│   │   ├── query_graph.py              # System B — interactive query + SSE streaming [DONE]
│   │   └── background_graph.py         # System A — daily pipeline [PLANNED]
│   ├── agents/                         # Agent node implementations
│   │   ├── page_lookup.py              # Check cached figure pages [DONE — stub, instant return]
│   │   ├── router.py                   # Classify and route queries, supports token streaming [DONE]
│   │   ├── tweet_agent.py              # RAG over tweets, supports token streaming [DONE]
│   │   ├── news_agent.py               # RAG over news articles, supports token streaming [DONE]
│   │   ├── ingestion_agent.py          # Load new data [PLANNED]
│   │   ├── topic_extractor.py          # Tag topics [PLANNED]
│   │   ├── contradiction_finder.py     # Detect contradictions [PLANNED]
│   │   └── page_builder.py             # Generate figure pages [PLANNED]
│   ├── agent_tools/                    # Shared tools
│   │   ├── vector_search.py            # Pinecone search (tweets) [DONE]
│   │   ├── news_search.py              # Pinecone search (news articles) [DONE]
│   │   ├── web_scraper.py              # URL content extraction [DONE]
│   │   └── url_extractor.py            # Extract URLs from text [DONE]
│   ├── agent/                          # Legacy ReAct agent (kept for backward compatibility)
│   │   ├── react_agent.py
│   │   ├── prompts.py
│   │   └── llm_interface.py
│   ├── load_news_to_supabase_and_pinecone.py  # Data loader script
│   ├── load_tweets_to_pinecone.py             # Tweet loader script
│   ├── prep_data.py                           # Data preparation
│   └── read_first_tweet.py                    # Utility
├── api/
│   ├── index.py                        # Flask API (all endpoints + SSE stream) [DONE]
│   └── test_request.py                 # Legacy API test
├── frontend/                           # React UI (Vite)
│   ├── src/
│   │   ├── components/
│   │   │   ├── ChatInterface.jsx       # Three-column layout with live streaming [DONE]
│   │   │   ├── ChatInterface.css       # Dark theme styles [DONE]
│   │   │   ├── FlowChart.jsx           # Animated pipeline flowchart [DONE]
│   │   │   └── FlowChart.css           # Flowchart styles [DONE]
│   │   ├── services/
│   │   │   └── api.js                  # API client + SSE stream consumer [DONE]
│   │   ├── App.jsx
│   │   ├── App.css
│   │   ├── index.css
│   │   └── main.jsx
│   ├── package.json
│   └── vite.config.js                  # Vite proxy config for API + SSE [DONE]
├── test/                               # Tests
│   ├── test_endpoints.py               # Unit tests for all API endpoints (9/9 pass) [DONE]
│   ├── check_all_indexes.py            # Pinecone index inspection
│   ├── inspect_supabase_db.py          # Supabase data inspection
│   ├── test_pinecone.py                # Pinecone connectivity test
│   └── ...                             # Other test utilities
├── .env                                # API keys and config
├── requirements.txt                    # Python dependencies
├── ARCHITECTURE.md                     # This file
└── SETUP.md                           # How to run backend and frontend
```

---

## Implementation Phases

### Phase 1 — Interactive Query Graph + UI (System B) [COMPLETED]

Built the LangGraph query system with router + tweet_agent + news_agent, SSE streaming, and a full real-time UI.

**Phase 1a — Core graph (planned, completed):**

- `src/graphs/query_graph.py` — StateGraph with 6 nodes: page_lookup, page_answer, router, tweet_agent, news_agent, both_agents. Conditional edges route based on page_found and route classification.
- `src/agents/router.py` — LLM-based query classifier using ChatOpenAI. Outputs JSON with `route` ("tweet_agent" | "news_agent" | "both") and `reason`.
- `src/agents/tweet_agent.py` — Searches `politics` Pinecone index via `vector_search`, synthesizes answer with chronologically sorted tweets.
- `src/agents/news_agent.py` — Searches `politics-news` Pinecone index via `news_search`, synthesizes answer citing media outlet, state, and date.
- `src/agents/page_lookup.py` — Stub returning `{"found": False}` until Phase 4 builds the `figure_pages` table. Executes instantly (too fast to see in the flowchart during loading, but shows green when done).
- `api/index.py` — Added `POST /api/v2/query` endpoint. Also fixed a syntax error in the existing agent endpoint.

**Phase 1b — SSE streaming (not in original plan):**

Real-time token streaming from each agent to the frontend via Server-Sent Events.

- `run_query_stream()` in `query_graph.py` — runs the pipeline in a background thread, pushes events (`node_start`, `node_end`, `token`, `done`) through a `queue.Queue`. The main thread yields them as SSE data.
- All three agents (`router`, `tweet_agent`, `news_agent`) now accept an `on_token` callback. When provided, they use `llm.stream()` instead of `llm.invoke()` and emit each token as it arrives.
- `POST /api/v2/query/stream` — SSE endpoint that streams `text/event-stream` responses.
- `frontend/src/services/api.js` — `streamGraphQuery()` uses `fetch` + `ReadableStream` to consume SSE events and dispatch them to React state.
- `vite.config.js` — Vite proxy config forwards `/api` to Flask at `:5000`, solving CORS and SSE buffering issues.

**Phase 1c — UI and flowchart (not in original plan):**

Full three-column dark-theme UI with real-time pipeline visualization.

- `FlowChart.jsx` + `FlowChart.css` — Animated pipeline component with 3 layout modes:
  - **Linear** (RAG): Query → Embed → Search → Top 7 → LLM → Answer
  - **Loop** (Agent): Query → Think → Choose → Execute → Observe (loop) → Answer
  - **Vertical branching** (Graph): Query → Page Lookup → Router → [Tweet Agent | News Agent | Both] → Answer
  - Nodes glow blue (active/pulse animation) during loading, turn green when pipeline completes. Unselected branches dim to 30% opacity.
  - Graph mode uses real SSE `node_start` events for highlighting instead of timer-based animation.
- `ChatInterface.jsx` — Three-column layout:
  - **Left sidebar** (240px): mode selector (Graph/Agent/RAG), routing metadata card, agent info card
  - **Main content**: response in styled cards with badge headers, source tweets (blue border) and articles (green border) with "View article" links, agent reasoning expandable section
  - **Right sidebar** (320px): flowchart at top, live feed console (node events with colored dots), model output section showing per-node token streams with labeled sections and blinking cursor
- `ChatInterface.css` — Dark theme (`#0f1923` bg, `#15202b` sidebars), responsive collapse for mobile
- `index.css` — Cleaned up Vite defaults that conflicted with component styles

**Phase 1d — Testing and docs (not in original plan):**

- `test/test_endpoints.py` — Unit tests covering all 5 API endpoints (9 tests: `GET /api/stats`, `POST /api/prompt`, `POST /api/agent/query`, `POST /api/v2/query` with tweet/news/both routing, plus empty-input validation). All 9 pass.
- `src/agent_tools/news_search.py` — Dedicated Pinecone search tool for the `politics-news` index.
- `SETUP.md` — How to run backend and frontend, API endpoint reference, example curl request.
- `ARCHITECTURE.md` — This file, kept up to date with implementation status.

**Verified with:**

- End-to-end graph test: `run_query()` for 3 query types — correct routing with proper tweet/article counts.
- Streaming test: `run_query_stream()` — router streams 44 tokens, news_agent streams 717 tokens, proper node_start/node_end events.
- API integration test: `test/test_endpoints.py` — 9/9 passed against live local server.
- SSE curl test: `curl.exe --no-buffer` against `/api/v2/query/stream` — confirmed real-time token delivery.
- Frontend build: `npm run build` succeeds with no errors.

**Known behaviors:**

- Page Lookup node completes too fast to see blue highlighting during loading (it's a stub). Will be visible once Phase 4 adds real Supabase lookup.

---

### Phase 2 — Topic Extraction [NOT STARTED]

- Create `topics`, `tweet_topics`, `article_topics` tables in Supabase
- Curate initial topic taxonomy (~20 topics)
- `src/agents/topic_extractor.py` — LLM tags records with topics
- Partial `src/graphs/background_graph.py` — ingestion → topic extraction

### Phase 3 — Contradiction Detection [NOT STARTED]

- Create `contradictions` table in Supabase
- `src/agents/contradiction_finder.py` — compare tweets vs news per figure/topic
- Extend background graph — add contradiction node

### Phase 4 — Figure Pages [NOT STARTED]

- Create `figure_pages` table in Supabase
- `src/agents/page_builder.py` — generate per-figure summary pages
- `src/agents/page_lookup.py` — replace stub with real Supabase lookup (will make the node visible in the flowchart during loading)
- Complete background graph — full pipeline
- Frontend — per-figure profile pages with tabs (overview, news, contradictions)

### Phase 5 — Deployment and Automation [NOT STARTED]

- `src/orchestrator.py` — cron entrypoint for daily pipeline
- Deploy to Render (web service + background worker)
- `agent_runs` table for monitoring
- Error handling and retry logic
