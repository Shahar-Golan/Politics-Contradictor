# Agentic RAG Implementation Guide

## OVERVIEW
Transform the current RAG-only system into an Agentic RAG system using the ReAct (Reasoning + Acting) framework. The agent will intelligently query Pinecone for tweets and scrape URLs found in tweets to provide comprehensive, contextual answers.

---

## STEP 1: UNDERSTAND CURRENT DATA STRUCTURE

### Pinecone Tweet Schema
```
ID: "780600557325156353"
account_id: "1339835893"
author_name: "Hillary Clinton"
created_at: "2016-09-27 00:00:00+00:00"
has_urls: true (boolean)
text: "Tweet content with possible URLs"
```

**Key Insight**: When `has_urls == true`, extract and analyze URLs to provide richer context.

---

## STEP 2: SET UP ENVIRONMENT VARIABLES

### Required Keys in `.env`
```env
PINECONE_API_KEY=your_pinecone_key
PINECONE_ENVIRONMENT=your_environment
PINECONE_INDEX_NAME=your_index_name
OPENAI_API_KEY=your_openai_key
```

**Action**: Verify all keys are present in `.env` file before proceeding.

---

## STEP 3: IMPLEMENT CORE AGENT TOOLS

### Tool 1: `vector_search(query: str, top_k: int = 5)`
**Purpose**: Search Pinecone for relevant tweets based on user query.

**Implementation Steps**:
1. Create `src/agent_tools/vector_search.py`
2. Initialize Pinecone client using environment variables
3. Generate query embedding using OpenAI embeddings
4. Query Pinecone index with the embedding
5. Parse and return results

**Return Format**:
```python
{
    "results": [
        {
            "id": "tweet_id",
            "score": 0.95,
            "metadata": {
                "text": "tweet text",
                "author_name": "author",
                "created_at": "timestamp",
                "has_urls": true/false,
                "account_id": "account_id"
            }
        }
    ]
}
```

### Tool 2: `web_scraper(url: str)`
**Purpose**: Fetch and extract content from URLs found in tweets.

**Implementation Steps**:
1. Create `src/agent_tools/web_scraper.py`
2. Install dependencies: `requests`, `beautifulsoup4`, `markdownify`
3. Handle URL expansion (Twitter shortened links like t.co)
4. Extract main content, title, and metadata
5. Convert HTML to clean Markdown
6. Handle errors gracefully (404, timeouts, etc.)

**Return Format**:
```python
{
    "url": "expanded_url",
    "title": "page_title",
    "content_markdown": "cleaned content",
    "summary": "brief summary",
    "has_statistics": true/false,
    "error": null
}
```

### Tool 3: `extract_urls(tweet_text: str)`
**Purpose**: Extract URLs from tweet text.

**Implementation Steps**:
1. Create `src/agent_tools/url_extractor.py`
2. Use regex to find URLs (http/https patterns)
3. Return list of unique URLs
4. Handle Twitter shortened URLs (t.co)

---

## STEP 4: IMPLEMENT REACT AGENT FRAMEWORK

### Create Agent Core: `src/agent/react_agent.py`

**Implementation Steps**:

1. **Define Agent State**:
```python
class AgentState:
    - user_query: str
    - conversation_history: List[dict]
    - thought: str
    - action: str
    - observation: str
    - scraped_urls: Set[str]  # Track already scraped URLs
    - final_answer: str
```

2. **Implement ReAct Loop**:
```python
def run_agent(user_query: str, max_iterations: int = 5):
    for iteration in range(max_iterations):
        # THOUGHT: Use LLM to analyze situation
        thought = generate_thought(state)
        
        # ACTION: Decide which tool to use
        action = decide_action(thought, state)
        
        # OBSERVATION: Execute tool and collect results
        observation = execute_action(action)
        
        # Check if we have enough information
        if should_finalize(state):
            break
    
    # FINAL ANSWER: Generate comprehensive response
    return generate_final_answer(state)
```

3. **Implement Decision Logic**:
```python
def decide_action(thought: str, state: AgentState) -> dict:
    """
    Decides which tool to use based on current state.
    Priority:
    1. If no tweets fetched yet -> vector_search
    2. If tweets have has_urls=true and not scraped -> web_scraper
    3. If sufficient context -> finalize
    """
```

4. **Implement Tool Execution**:
```python
def execute_action(action: dict) -> str:
    if action['tool'] == 'vector_search':
        return vector_search(action['query'])
    elif action['tool'] == 'web_scraper':
        return web_scraper(action['url'])
    elif action['tool'] == 'finalize':
        return None
```

---

## STEP 5: INTEGRATE WITH LLM (OpenAI)

### Create LLM Interface: `src/agent/llm_interface.py`

**Implementation Steps**:

1. **Thought Generation**:
```python
def generate_thought(state: AgentState) -> str:
    """
    Use GPT-4 to analyze current state and decide next step.
    Prompt should include:
    - User's original query
    - Previous thoughts and observations
    - Available tools
    - Current context
    """
```

2. **Action Decision**:
```python
def generate_action(thought: str, state: AgentState) -> dict:
    """
    Use GPT-4 to output structured action:
    {
        "tool": "vector_search|web_scraper|finalize",
        "parameters": {...}
    }
    Use JSON mode for reliable parsing.
    """
```

3. **Final Answer Generation**:
```python
def generate_final_answer(state: AgentState) -> str:
    """
    Synthesize all observations into coherent answer.
    Include:
    - Direct answer to user query
    - Supporting evidence from tweets
    - Information from scraped URLs (if applicable)
    - Clickable URLs for user reference
    """
```

---

## STEP 6: CREATE AGENT PROMPTS

### Create `src/agent/prompts.py`

**System Prompt Template**:
```
You are an X-Platform Intelligence Agent analyzing tweets and their linked content.

AVAILABLE TOOLS:
1. vector_search(query) - Search Pinecone for relevant tweets
2. web_scraper(url) - Extract content from URLs in tweets

DATA STRUCTURE:
- Tweets have: id, text, author_name, created_at, has_urls
- When has_urls=true, investigate URLs for full context

REACT FRAMEWORK:
1. THOUGHT: Analyze what information you need
2. ACTION: Choose a tool and parameters
3. OBSERVATION: Review tool results
4. REPEAT if needed, or provide FINAL ANSWER

GUIDELINES:
- Always search tweets first
- If tweets contain URLs and query needs details, scrape them
- Don't scrape same URL twice (check scraped_urls)
- Provide concise, evidence-based answers
```

**Thought Prompt Template**:
```
Current State:
User Query: {user_query}
Previous Actions: {action_history}
Current Context: {observations}
Scraped URLs: {scraped_urls}

What should you do next? Analyze the situation and explain your reasoning.
```

**Action Prompt Template**:
```
Based on your thought: "{thought}"

Choose your next action as JSON:
{{
    "tool": "vector_search" | "web_scraper" | "finalize",
    "parameters": {{...}},
    "reason": "brief explanation"
}}
```

---

## STEP 7: UPDATE API ENDPOINT

### Modify `api/index.py`

**Implementation Steps**:

1. **Add Agent Import**:
```python
from src.agent.react_agent import run_agent
```

2. **Create New Agent Endpoint**:
```python
@app.route('/api/agent/query', methods=['POST'])
def agent_query():
    """
    New endpoint for agentic RAG queries.
    """
    data = request.json
    user_query = data.get('query')
    
    # Run ReAct agent
    result = run_agent(user_query)
    
    return jsonify({
        "answer": result['final_answer'],
        "thought_process": result['thoughts'],
        "sources": result['tweets_used'],
        "urls_analyzed": result['scraped_urls']
    })
```

3. **Keep Old Endpoint for Comparison**:
```python
@app.route('/api/query', methods=['POST'])
def simple_rag_query():
    """
    Original RAG-only endpoint (keep for A/B testing).
    """
    # existing implementation
```

---

## STEP 8: UPDATE FRONTEND

### Modify `frontend/src/components/ChatInterface.jsx`

**Implementation Steps**:

1. **Add Mode Toggle**:
```javascript
const [agentMode, setAgentMode] = useState(true);
```

2. **Update API Call**:
```javascript
const endpoint = agentMode ? '/api/agent/query' : '/api/query';
```

3. **Display Agent Reasoning** (Optional):
```javascript
{message.thought_process && (
    <details>
        <summary>Show reasoning steps</summary>
        <ul>
            {message.thought_process.map((step, i) => (
                <li key={i}>{step}</li>
            ))}
        </ul>
    </details>
)}
```

4. **Render Clickable URLs**:
```javascript
{message.urls_analyzed && (
    <div className="sources">
        <h4>Sources Analyzed:</h4>
        {message.urls_analyzed.map(url => (
            <a href={url} target="_blank" rel="noopener">
                {url}
            </a>
        ))}
    </div>
)}
```

---

## STEP 9: TESTING & VALIDATION

### Create Test Suite: `test/test_agent.py`

**Test Cases**:

1. **Test Tool Execution**:
   - Test vector_search returns proper results
   - Test web_scraper handles various URL types
   - Test URL extraction from tweets

2. **Test Agent Logic**:
   - Agent searches tweets before answering
   - Agent scrapes URLs when has_urls=true
   - Agent doesn't scrape same URL twice
   - Agent terminates after finding answer

3. **Test Edge Cases**:
   - No tweets found
   - URL scraping fails (404, timeout)
   - Malformed URLs
   - Empty query

4. **Integration Test**:
   - End-to-end query flow
   - Compare RAG vs Agentic RAG results

---

## STEP 10: DEPLOYMENT & MONITORING

**Implementation Steps**:

1. **Add Logging**:
   - Log each thought/action/observation
   - Track agent iterations
   - Monitor URL scraping success rate

2. **Performance Optimization**:
   - Cache scraped URL content (24h TTL)
   - Parallel URL scraping (if multiple URLs)
   - Limit max iterations to prevent loops

3. **User Feedback Loop**:
   - Add "Was this helpful?" button
   - Track which queries trigger URL scraping
   - Monitor average iterations per query

---

## EXAMPLE USER FLOW

**User Query**: "What climate challenge did Bill Gates tweet about?"

**Agent Process**:
1. **THOUGHT**: Need to search for Bill Gates tweets about climate challenges
2. **ACTION**: `vector_search("Bill Gates climate challenge")`
3. **OBSERVATION**: Found tweet: "Check out my latest climate challenge: [URL]", has_urls=true
4. **THOUGHT**: Tweet mentions challenge but doesn't explain it. Need to scrape URL.
5. **ACTION**: `web_scraper("https://t.co/xyz")`
6. **OBSERVATION**: Page content: "Guess the Carbon Footprint Game - can you estimate..."
7. **THOUGHT**: Now I have complete context. Ready to answer.
8. **FINAL ANSWER**: "Bill Gates tweeted about the 'Guess the Carbon Footprint' challenge, an interactive game where users estimate the carbon emissions of everyday items. [View original tweet and play the game](https://t.co/xyz)"

---

## IMPLEMENTATION PRIORITY

**Phase 1 (Core)**:
- [ ] Step 2: Verify environment variables
- [ ] Step 3: Implement vector_search tool
- [ ] Step 3: Implement web_scraper tool
- [ ] Step 4: Build ReAct agent framework

**Phase 2 (Integration)**:
- [ ] Step 5: Integrate OpenAI for reasoning
- [ ] Step 6: Create agent prompts
- [ ] Step 7: Update API endpoint

**Phase 3 (UI & Testing)**:
- [ ] Step 8: Update frontend
- [ ] Step 9: Create test suite
- [ ] Step 10: Add monitoring

**Phase 4 (Polish)**:
- [ ] Add caching layer
- [ ] Optimize performance
- [ ] Add user feedback collection