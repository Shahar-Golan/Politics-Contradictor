import os
from dotenv import load_dotenv
from pathlib import Path
from pinecone import Pinecone

# Load .env
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")
pc = Pinecone(api_key=PINECONE_API_KEY)

indexes = ['ted-vector-db', 'politics-tweets', 'politics']

print("=" * 60)
print("CHECKING ALL INDEXES FOR DATA")
print("=" * 60)

for index_name in indexes:
    print(f"\n📊 Index: {index_name}")
    try:
        index = pc.Index(index_name)
        stats = index.describe_index_stats()
        vector_count = stats.get('total_vector_count', 0)
        dimension = stats.get('dimension', 'N/A')
        
        print(f"   Vectors: {vector_count}")
        print(f"   Dimension: {dimension}")
        
        if vector_count > 0:
            print(f"   ✅ HAS DATA!")
        else:
            print(f"   ❌ Empty")
            
    except Exception as e:
        print(f"   ❌ Error: {e}")

print("\n" + "=" * 60)
