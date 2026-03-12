# How to Run Politics-Contradictor

## Prerequisites

- Python 3.10+
- Node.js 18+
- A `.env` file in the project root with:

```
OPENAI_API_KEY=your_key
BASE_URL=https://api.llmod.ai/v1
GPT_MODEL=RPRTHPB-gpt-5-mini
PINECONE_API_KEY=your_key
SUPABASE_URL=your_url
SUPABASE_KEY=your_key
```

---

## Backend (Flask API)

```bash
# 1. Create and activate virtual environment
cd Politics-Contradictor
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt
pip install langchain-openai langgraph

# 3. Start the server
python api/index.py
```

The API will run on `http://localhost:5000`.

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/stats` | System parameters |
| POST | `/api/prompt` | Simple RAG (tweets only) |
| POST | `/api/agent/query` | ReAct agent (tweets only) |
| POST | `/api/v2/query` | Multi-agent graph (tweets + news) |

#### Example request (Multi-agent graph)

```bash
curl -X POST http://localhost:5000/api/v2/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What did Trump say about Biden?"}'
```

---

## Frontend (React + Vite)

```bash
# 1. Install dependencies
cd frontend
npm install

# 2. Start dev server
npm run dev
```

The frontend will run on `http://localhost:5173` and proxy API calls to `http://localhost:5000`.

### Build for production

```bash
cd frontend
npm run build
```

The built files go to `frontend/dist/`, which Flask serves automatically.

---

## Running Both Together

Open two terminals:

**Terminal 1 — Backend:**
```bash
cd Politics-Contradictor
venv\Scripts\activate
python api/index.py
```

**Terminal 2 — Frontend:**
```bash
cd Politics-Contradictor/frontend
npm run dev
```

Then open `http://localhost:5173` in your browser.
