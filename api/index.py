from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from openai import OpenAI
import os
import sys
from dotenv import load_dotenv
from pathlib import Path
from collections import OrderedDict

# Add src directory to path for agent_tools import
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from agent_tools.vector_search import vector_search
from agent.react_agent import run_agent

# Load .env locally; Render will use its own Environment Variables
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

app = Flask(__name__, static_folder='../frontend/dist', static_url_path='/')
CORS(app)  # Enable CORS for React frontend

# --- Configuration ---
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
BASE_URL = os.environ.get("BASE_URL", "https://api.llmod.ai/v1")

GPT_MODEL = "RPRTHPB-gpt-5-mini"
TOP_K = 15
CHUNK_SIZE = 1024
OVERLAP = 0.2

# Initialize OpenAI Client (for GPT responses)
client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url=BASE_URL
)

SYSTEM_PROMPT = """You are a source of truth for what public figures have actually stated on social media. Your role is to provide accurate, concise information about public figures' opinions and statements based strictly on their tweets.

Response Format:
- Present the 3 most relevant tweets in chronological order (oldest to newest)
- For each tweet include: Author name, date, and direct quote or key statement
- Keep it concise - avoid repeating similar points
- omit urls that appear in the tweet's text
- If other public figures in the context have relevant perspectives, briefly mention them at the end
- Identify patterns or contradictions only if clearly evident
- Use bullet points or short paragraphs for clarity

Guidelines:
- Answer using ONLY the tweet content and metadata provided
- Provide direct quotes when available
- Clearly attribute statements to the public figure who made them
- Do NOT use external knowledge beyond the provided tweets
- If tweets are not relevant to the question: "I don't have tweets from public figures addressing this topic."

Keep responses focused and readable."""

# --- Routes ---

@app.route('/api/stats', methods=['GET'])
def stats():
    """Returns system parameters for automated grading."""
    return jsonify({
        "chunk_size": CHUNK_SIZE,
        "overlap_ratio": OVERLAP,
        "top_k": TOP_K
    })

@app.route('/api/prompt', methods=['POST'])
def chat():
    """Main RAG endpoint. Returns a compliant JSON object."""
    data = request.json
    user_query = data.get("question", "")
    if not user_query:
        return jsonify({"error": "No question provided"}), 400

    # 1. Search for relevant tweets using vector_search tool
    search_result = vector_search(user_query, top_k=TOP_K)
    
    if not search_result["success"]:
        return jsonify({"error": f"Search failed: {search_result['error']}"}), 500

    # 2. Process tweets into context list
    context_list = []
    for match in search_result['results']:
        meta = match['metadata']
        score = match['score']
        text = meta.get('text', '')
        context_list.append({
            "tweet_id": match['id'],
            "account_id": meta.get('account_id'),
            "author_name": meta.get('author_name'),
            "text": text,
            "text_len": len(text),
            "created_at": meta.get('created_at'),
            "score": score
        })

    # 3. Final Context List (Top 7 for better coverage)
    final_context_list = context_list[:7]
    
    # 4. Sort by date for chronological presentation (oldest first)
    final_context_list_sorted = sorted(
        final_context_list, 
        key=lambda x: x.get('created_at', ''), 
        reverse=False
    )

    # 5. Build Augmented Prompt (using chronologically sorted context)
    context_text = ""
    for item in final_context_list_sorted:
        context_text += f"Author: {item['author_name']}\nDate: {item['created_at']}\nTweet: {item['text']}\n\n"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Context:\n{context_text}\n\nQuestion: {user_query}"}
    ]
    
    # 6. Generate Answer (Non-streaming for JSON compliance)
    chat_res = client.chat.completions.create(model=GPT_MODEL, messages=messages)
    final_answer = chat_res.choices[0].message.content

    # 7. Ordered JSON Output (Required by assignment)
    response_data = OrderedDict([
        ("response", final_answer),
        ("context", final_context_list_sorted),
        ("Augmented_prompt", {
            "System": SYSTEM_PROMPT,
            "User": f"Context:\n{context_text}\n\nQuestion: {user_query}"
        })
    ])
    
    return jsonify(response_data)


@app.route('/api/agent/query', methods=['POST'])
def agent_query():
    """
    Agentic RAG endpoint - uses ReAct agent with LLM reasoning.
    Returns comprehensive response with thought process and sources.
    """
    data = request.json
    user_query = data.get('query', '')
    
    if not user_query:
        return jsonify({"error": "No query provided"}), 400
    
    # Run ReAct agent with LLM mode
    result = run_agent(
        user_query, 
        max_iterations=5, 
        verbose=False, 
        use_llm=True
    )
    
    if not result['success']:
        return jsonify({"error": "Agent failed to process query"}), 500
    
    # Format response
    response_data = OrderedDict([
        ("answer", result['final_answer']),
        ("mode", result['mode']),
        ("iterations", result['iterations']),
        ("thought_process", result['thoughts']),
        ("actions_taken", result['actions']),
        ("tweets_found", result['tweets_found']),
        ("tweets_used", result['tweets']),
        ("urls_analyzed", result['scraped_content'])
    ])
    
    return jsonify(response_data)


# Serve React frontend for all non-API routes
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, 'index.html')

if __name__ == '__main__':
    # Use the PORT environment variable if available, otherwise default to 5000
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)