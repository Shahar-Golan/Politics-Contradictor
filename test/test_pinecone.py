import os
from dotenv import load_dotenv
from pathlib import Path
from pinecone import Pinecone
from openai import OpenAI

# Load .env
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

# Configuration
PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "politics-tweets")

print("=" * 60)
print("PINECONE & OPENAI CONNECTION TEST")
print("=" * 60)

# Test 1: Check environment variables
print("\n1. Environment Variables:")
print(f"   PINECONE_API_KEY: {'✅ Set' if PINECONE_API_KEY else '❌ Missing'}")
print(f"   OPENAI_API_KEY: {'✅ Set' if OPENAI_API_KEY else '❌ Missing'}")
print(f"   PINECONE_INDEX_NAME: {PINECONE_INDEX_NAME}")

# Test 2: Connect to Pinecone
print("\n2. Pinecone Connection:")
try:
    pc = Pinecone(api_key=PINECONE_API_KEY)
    print("   ✅ Connected to Pinecone")
    
    # List indexes
    indexes = pc.list_indexes()
    print(f"   Available indexes: {[idx.name for idx in indexes]}")
    
    # Check if our index exists
    index_names = [idx.name for idx in indexes]
    if PINECONE_INDEX_NAME in index_names:
        print(f"   ✅ Index '{PINECONE_INDEX_NAME}' exists")
    else:
        print(f"   ❌ Index '{PINECONE_INDEX_NAME}' NOT FOUND!")
        print(f"   Available indexes: {index_names}")
        
except Exception as e:
    print(f"   ❌ Error: {e}")
    exit(1)

# Test 3: Get index stats
print("\n3. Index Statistics:")
try:
    index = pc.Index(PINECONE_INDEX_NAME)
    stats = index.describe_index_stats()
    print(f"   Total vectors: {stats.get('total_vector_count', 0)}")
    print(f"   Dimension: {stats.get('dimension', 'N/A')}")
    print(f"   Namespaces: {stats.get('namespaces', {})}")
    
    if stats.get('total_vector_count', 0) == 0:
        print("   ⚠️  WARNING: Index is EMPTY! No data loaded.")
    else:
        print(f"   ✅ Index has {stats.get('total_vector_count', 0)} vectors")
        
except Exception as e:
    print(f"   ❌ Error: {e}")
    exit(1)

# Test 4: Test a sample query
print("\n4. Sample Query Test:")
try:
    client = OpenAI(api_key=OPENAI_API_KEY, base_url="https://api.llmod.ai/v1")
    
    # Create embedding
    test_query = "Kamala Harris"
    print(f"   Query: '{test_query}'")
    
    emb_res = client.embeddings.create(
        input=test_query, 
        model="RPRTHPB-text-embedding-3-small",
        dimensions=1024
    )
    query_vector = emb_res.data[0].embedding
    print(f"   ✅ Generated embedding (dimension: {len(query_vector)})")
    
    # Query Pinecone
    results = index.query(vector=query_vector, top_k=5, include_metadata=True)
    print(f"   Matches found: {len(results.get('matches', []))}")
    
    if results.get('matches'):
        print("\n   Top 3 matches:")
        for i, match in enumerate(results['matches'][:3], 1):
            meta = match.get('metadata', {})
            print(f"   {i}. Score: {match['score']:.4f}")
            print(f"      Author: {meta.get('author_name', 'N/A')}")
            print(f"      Text: {meta.get('text', 'N/A')[:100]}...")
    else:
        print("   ❌ No matches found! The index might be empty or query failed.")
        
except Exception as e:
    print(f"   ❌ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)
