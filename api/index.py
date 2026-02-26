from flask import Flask, request, jsonify
from flask_cors import CORS
from pinecone import Pinecone
from openai import OpenAI
import os
from dotenv import load_dotenv
from pathlib import Path
from collections import OrderedDict

# Load .env locally; Vercel will use its own Environment Variables
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

app = Flask(__name__)
CORS(app)  # Enable CORS for React frontend

# --- Configuration ---
PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "politics-tweets")

EMBEDDING_MODEL = "RPRTHPB-text-embedding-3-small"
GPT_MODEL = "RPRTHPB-gpt-5-mini"
TOP_K = 10
CHUNK_SIZE = 1024
OVERLAP = 0.2

# Initialize Clients
pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(PINECONE_INDEX_NAME)
client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url="https://api.llmod.ai/v1"
)

SYSTEM_PROMPT = """You are a Politics Tweet assistant that answers questions strictly and only based on the politics tweet dataset context provided to you (tweet metadata and content).
You must not use any external knowledge, the open internet, or information that is not explicitly contained in the retrieved context.
If the answer cannot be determined from the provided context, respond: "I don't know based on the provided tweet data."
Always explain your answer using the given context, quoting or paraphrasing the relevant tweets or metadata when helpful.
You can analyze sentiment, themes, authors, and content patterns from the provided tweets.
You may add additional clarifications (e.g., response style), but you must keep the above constraints."""

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

    # 1. Embed Question
    emb_res = client.embeddings.create(input=user_query, model=EMBEDDING_MODEL, dimensions=1024)
    query_vector = emb_res.data[0].embedding

    # 2. Retrieve from Pinecone
    search_results = index.query(vector=query_vector, top_k=TOP_K, include_metadata=True)

    # 3. Process tweets (no deduplication needed since each tweet is unique)
    context_list = []
    for match in search_results['matches']:
        meta = match['metadata']
        score = match['score']
        context_list.append({
            "tweet_id": meta.get('tweet_id'),
            "account_id": meta.get('account_id'),
            "author_name": meta.get('author_name'),
            "author_screen_name": meta.get('author_screen_name'),
            "text": meta.get('text'),
            "text_len": meta.get('text_len'),
            "score": score
        })

    # 4. Final Context List (Top 5)
    final_context_list = context_list[:5]

    # 5. Build Augmented Prompt
    context_text = ""
    for item in final_context_list:
        context_text += f"Author: {item['author_name']} (@{item['author_screen_name']})\nTweet: {item['text']}\nLength: {item['text_len']} chars\n\n"

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
        ("context", final_context_list),
        ("Augmented_prompt", {
            "System": SYSTEM_PROMPT,
            "User": f"Context:\n{context_text}\n\nQuestion: {user_query}"
        })
    ])
    
    return jsonify(response_data)

if __name__ == '__main__':
    app.run(debug=True, port=3000, use_reloader=False)