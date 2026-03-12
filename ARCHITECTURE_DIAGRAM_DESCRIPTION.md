# Architecture Diagram Description for Task 2.C

## Overview
The diagram should illustrate a **ReAct-based X-Platform Intelligence Agent** that searches tweets and scrapes linked content to answer user queries about public figures' statements.

---

## Component Layout (Top to Bottom / Left to Right)

### 1. **User Layer** (Top)
- **Frontend (React + Vite)**
  - Text input box for user queries
  - "Run Agent" button
  - Response display area
  - Steps trace visualization
  - Connects to API via HTTP POST

### 2. **API Layer** (Middle-Top)
- **Flask API Server**
  - **Endpoints:**
    - `GET /api/team_info` - Returns team information
    - `GET /api/agent_info` - Returns agent metadata and usage
    - `GET /api/model_architecture` - Returns architecture diagram (PNG)
    - `POST /api/execute` - Main entry point for agent queries
    - `POST /api/prompt` - Simple RAG endpoint (legacy)
    - `POST /api/agent/query` - Agentic RAG endpoint
  - Routes requests to ReAct Agent
  - Manages CORS for frontend communication

### 3. **ReAct Agent Core** (Middle-Center) - Main Brain
**Box labeled: "ReAct Agent Loop (max 5 iterations)"**

This is the central orchestrator with three repeating phases:

#### 3.1 **THOUGHT Module** (Reasoning)
- **Purpose:** Analyze current state and decide next steps
- **Powered by:** LLM Interface (GPT-5-mini via llmod.ai)
- **Inputs:**
  - User query
  - Current iteration number
  - Previous thoughts, actions, observations
  - Tweets retrieved so far
  - URLs already scraped
- **Output:** Reasoning text (e.g., "I need to search for tweets about X" or "I should scrape URL Y for more context")

#### 3.2 **ACTION Module** (Decision)
- **Purpose:** Choose which tool to execute
- **Powered by:** LLM Interface (GPT-5-mini via llmod.ai)
- **Inputs:** Current thought, agent state
- **Available Actions:**
  1. `vector_search` - Search for tweets
  2. `web_scraper` - Scrape a URL from a tweet
  3. `finalize` - Stop and generate final answer
- **Output:** JSON with tool name, parameters, and reason

#### 3.3 **OBSERVATION Module** (Execution & Results)
- **Purpose:** Execute the chosen action and capture results
- **Calls:** Agent Tools (see section 4 below)
- **Updates:** Agent state with new data
- **Output:** Observation text describing what was found

**Loop Control:**
- Continues until `finalize` action is chosen OR max 5 iterations reached
- Each iteration adds to agent state (cumulative knowledge)

### 4. **Agent Tools** (Middle-Bottom) - Tool Layer
**Three distinct tools the agent can invoke:**

#### 4.1 **Vector Search Tool**
- **Module Name:** `vector_search`
- **Location:** `src/agent_tools/vector_search.py`
- **Function:** Search Pinecone for relevant tweets
- **Process:**
  1. Takes query text
  2. Generates embedding via OpenAI Embeddings API (text-embedding-3-small, 1024 dims)
  3. Queries Pinecone index ("politics")
  4. Returns top-k tweets with metadata
- **Returns:**
  - Tweet ID, score, author name, text, date, has_urls flag
- **Connects to:** Pinecone Vector Database ↓

#### 4.2 **URL Extractor Tool**
- **Module Name:** `url_extractor`
- **Location:** `src/agent_tools/url_extractor.py`
- **Function:** Extract URLs from tweet text
- **Process:** Uses regex to identify http/https URLs in text
- **Returns:** List of URLs found

#### 4.3 **Web Scraper Tool**
- **Module Name:** `web_scraper`
- **Location:** `src/agent_tools/web_scraper.py`
- **Function:** Fetch and analyze content from URLs
- **Process:**
  1. Makes HTTP request to URL
  2. Parses HTML content
  3. Extracts text, title, statistics
  4. Handles URL shorteners
- **Returns:**
  - Page title, content preview, word count, statistics
- **Connects to:** External Web (Twitter links, articles, etc.) ↓

### 5. **LLM Interface** (Right Side) - AI Engine
**Box labeled: "LLM Interface (GPT-5-mini)"**
- **Location:** `src/agent/llm_interface.py`
- **Connected to:** OpenAI API (via llmod.ai base URL)
- **Functions:**
  - `generate_thought_llm()` - Produces reasoning
  - `generate_action_llm()` - Decides which tool to use
  - `generate_final_answer_llm()` - Synthesizes comprehensive answer
- **Uses:** System prompts from `src/agent/prompts.py`
- **Model:** RPRTHPB-gpt-5-mini

### 6. **External Data Sources** (Bottom)
**Three external systems:**

#### 6.1 **Pinecone Vector Database**
- **Contains:** Embedded tweets from public figures
- **Index Name:** "politics"
- **Dimensions:** 1024
- **Accessed by:** Vector Search Tool
- **Data:** Tweet IDs, embeddings, metadata (author, text, date, URLs)

#### 6.2 **OpenAI Embeddings API**
- **Model:** text-embedding-3-small (1024 dimensions)
- **Used by:** Vector Search Tool to embed queries
- **Provider:** llmod.ai (BASE_URL)

#### 6.3 **External Web Content**
- **Accessed by:** Web Scraper Tool
- **Sources:** Twitter/X links, news articles, policy pages referenced in tweets

---

## Data Flow (Show with Arrows)

1. **User Query** → Frontend → API (`POST /api/execute`)
2. API → **ReAct Agent** (initialize with query)
3. **ReAct Loop** (repeat up to 5 times):
   - **THOUGHT** ← LLM Interface (analyze state)
   - **ACTION** ← LLM Interface (decide tool)
   - **OBSERVATION**:
     - IF action = `vector_search` → Vector Search Tool → Pinecone + OpenAI Embeddings
     - IF action = `web_scraper` → Web Scraper Tool → External Web
     - IF action = `finalize` → Exit loop
   - Update agent state with observation
4. **Final Answer Generation** ← LLM Interface (synthesize all data)
5. ReAct Agent → API → Frontend (response + steps)

---

## Color Coding Suggestions

- **Frontend (React):** Light blue
- **API Layer (Flask):** Green
- **ReAct Agent Core:** Orange/Gold (central importance)
- **Agent Tools:** Purple
- **LLM Interface:** Red/Pink
- **External Data Sources:** Gray
- **Arrows:** Black with labels

---

## Key Labels to Include

**Module Names (must match code and API responses):**
- `vector_search`
- `web_scraper`
- `url_extractor`
- `thought_generation`
- `action_decision`
- `final_answer_synthesis`
- `react_agent`
- `llm_interface`

**Technologies:**
- React + Vite
- Flask + CORS
- Python
- OpenAI API (GPT-5-mini, text-embedding-3-small)
- Pinecone Vector Database
- llmod.ai (API provider)

---

## Important Notes

1. **Consistency:** All module names in diagram MUST match:
   - Code filenames (`vector_search.py`, `web_scraper.py`, etc.)
   - API response "module" fields in steps
   - Agent tool names in actions

2. **ReAct Loop:** Emphasize that this is iterative (show cycle with up to 5 iterations)

3. **LLM Calls:** Show three distinct LLM calls:
   - Thought generation (reasoning)
   - Action decision (tool selection)
   - Final answer synthesis (comprehensive response)

4. **State Management:** Show that agent state accumulates data across iterations (tweets_retrieved, scraped_urls, observations)

5. **Fallback Mode:** Optionally mention "Rule-based fallback" if LLM unavailable (not critical for diagram)

---

## Layout Suggestion

```
┌─────────────────────────────────────────────────────┐
│              Frontend (React + Vite)                │
│  [Text Input] [Run Agent Button] [Response Display]│
└────────────────────┬────────────────────────────────┘
                     │ HTTP POST /api/execute
                     ▼
┌─────────────────────────────────────────────────────┐
│                Flask API Server                     │
│  /api/execute  /api/agent_info  /api/team_info     │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
         ┌───────────────────────────┐
         │   ReAct Agent Loop        │◄─────────┐
         │  (max 5 iterations)       │          │
         │                           │          │
         │  ┌──────────────────┐    │          │
         │  │ 1. THOUGHT       │◄───┼──────────┤
         │  │    (Reasoning)   │    │          │
         │  └────────┬─────────┘    │          │
         │           │               │    ┌─────┴─────┐
         │           ▼               │    │    LLM    │
         │  ┌──────────────────┐    │    │ Interface │
         │  │ 2. ACTION        │◄───┼────│ GPT-5-mini│
         │  │    (Decision)    │    │    └───────────┘
         │  └────────┬─────────┘    │
         │           │               │
         │           ▼               │
         │  ┌──────────────────┐    │
         │  │ 3. OBSERVATION   │    │
         │  │    (Execute)     │────┤
         │  └────────┬─────────┘    │
         │           │               │
         └───────────┼───────────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
        ▼                         ▼
┌──────────────┐          ┌──────────────┐
│ Vector Search│          │ Web Scraper  │
│     Tool     │          │     Tool     │
└──────┬───────┘          └──────┬───────┘
       │                         │
       ▼                         ▼
┌──────────────┐          ┌──────────────┐
│  Pinecone    │          │ External Web │
│   Database   │          │   Content    │
└──────────────┘          └──────────────┘
```

---

## Diagram Format
- **Format:** PNG image
- **Resolution:** High enough to read all text clearly (min 1920x1080)
- **Style:** Clean, professional, technical architecture diagram
- **Tools:** Can use draw.io, Lucidchart, Mermaid, or any diagramming tool
