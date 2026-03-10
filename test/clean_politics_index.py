"""
Script to clean the 'politics' index by deleting all existing vectors
This removes the 200 broken vectors to prepare for fresh embedding
"""

import os
from dotenv import load_dotenv
from pathlib import Path
from pinecone import Pinecone
import time

# Load .env
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

# Configuration
PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")
INDEX_NAME = "politics"


def clean_index():
    """Clean the 'politics' index by deleting all vectors"""
    print("=" * 70)
    print("CLEANING THE 'POLITICS' INDEX")
    print("=" * 70)
    
    # Initialize Pinecone
    pc = Pinecone(api_key=PINECONE_API_KEY)
    
    # Connect to index
    try:
        index = pc.Index(INDEX_NAME)
        print(f"\n✅ Connected to index: {INDEX_NAME}")
    except Exception as e:
        print(f"\n❌ Error connecting to index: {e}")
        return False
    
    # Get current stats
    print("\n📊 Current Index Status:")
    try:
        stats = index.describe_index_stats()
        vector_count = stats.get('total_vector_count', 0)
        dimension = stats.get('dimension', 'N/A')
        namespaces = stats.get('namespaces', {})
        
        print(f"   Total vectors: {vector_count}")
        print(f"   Dimension: {dimension}")
        print(f"   Namespaces: {list(namespaces.keys()) if namespaces else 'default'}")
        
        if vector_count == 0:
            print("\n✅ Index is already empty!")
            return True
            
    except Exception as e:
        print(f"   ❌ Error getting stats: {e}")
        return False
    
    # Confirm deletion
    print(f"\n⚠️  WARNING: About to delete {vector_count} vectors from '{INDEX_NAME}' index")
    response = input("   Are you sure you want to continue? (yes/no): ")
    
    if response.lower() not in ['yes', 'y']:
        print("\n❌ Deletion cancelled by user")
        return False
    
    # Delete all vectors
    print("\n🗑️  Deleting all vectors...")
    try:
        # Delete from all namespaces
        if namespaces:
            for namespace in namespaces.keys():
                print(f"   Deleting from namespace: {namespace}")
                index.delete(delete_all=True, namespace=namespace)
        else:
            # Delete from default namespace
            print(f"   Deleting from default namespace")
            index.delete(delete_all=True)
        
        # Wait a moment for deletion to complete
        print("   Waiting for deletion to complete...")
        time.sleep(3)
        
        # Verify deletion
        stats_after = index.describe_index_stats()
        vector_count_after = stats_after.get('total_vector_count', 0)
        
        if vector_count_after == 0:
            print(f"\n✅ SUCCESS! All vectors deleted from '{INDEX_NAME}' index")
            print(f"   Before: {vector_count} vectors")
            print(f"   After: {vector_count_after} vectors")
            print("\n   The index is now clean and ready for fresh embeddings!")
            return True
        else:
            print(f"\n⚠️  WARNING: {vector_count_after} vectors still remain")
            return False
            
    except Exception as e:
        print(f"\n❌ Error during deletion: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main execution"""
    print("\n🧹 PINECONE INDEX CLEANING SCRIPT")
    print("   Removes broken vectors from the 'politics' index\n")
    
    success = clean_index()
    
    if success:
        print("\n" + "=" * 70)
        print("✅ CLEANING COMPLETE!")
        print("=" * 70)
        print("\n📝 Next Step:")
        print("   Run 'embed_tweets_to_pinecone.py' to embed your 52,000 tweets\n")
    else:
        print("\n" + "=" * 70)
        print("❌ CLEANING FAILED")
        print("=" * 70)


if __name__ == "__main__":
    main()
