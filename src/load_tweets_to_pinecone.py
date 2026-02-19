import os
from pathlib import Path
from dotenv import load_dotenv
import psycopg2
from pinecone import Pinecone, ServerlessSpec
from openai import OpenAI


def main() -> None:
    # Load environment variables
    env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(env_path)
    
    # Get configuration from .env
    database_url = os.environ.get("DATABASE_URL")
    pinecone_api_key = os.environ.get("PINECONE_API_KEY")
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    pinecone_index_name = os.environ.get("PINECONE_INDEX_NAME", "politics")
    base_url = os.environ.get("BASE_URL", "https://api.llmod.ai/v1")
    
    # Fallback for DATABASE_URL if not in .env
    if not database_url:
        database_url = "postgresql://postgres:Shir%40106@localhost:5432/politics"
    
    if not pinecone_api_key or not openai_api_key:
        raise RuntimeError("Missing required API keys in .env file")
    
    # Initialize clients
    pc = Pinecone(api_key=pinecone_api_key)
    client = OpenAI(
        api_key=openai_api_key,
        base_url=base_url
    )
    
    # Constants - using the only available embedding model
    EMBEDDING_MODEL = "RPRTHPB-text-embedding-3-small"
    EMBEDDING_DIMENSIONS = 1536  # This model produces 1536-dimensional embeddings
    
    # Check if index exists and has correct dimensions
    try:
        index_info = pc.describe_index(pinecone_index_name)
        existing_dimensions = index_info['dimension']
        print(f"Existing index '{pinecone_index_name}' has {existing_dimensions} dimensions")
        
        if existing_dimensions != EMBEDDING_DIMENSIONS:
            print(f"Dimension mismatch! Expected {EMBEDDING_DIMENSIONS}, got {existing_dimensions}")
            
            # Create a new index with correct dimensions
            new_index_name = f"{pinecone_index_name}-tweets"
            print(f"Creating new index '{new_index_name}' with {EMBEDDING_DIMENSIONS} dimensions...")
            
            pc.create_index(
                name=new_index_name,
                dimension=EMBEDDING_DIMENSIONS,
                metric='cosine',
                spec=ServerlessSpec(
                    cloud='aws',
                    region='us-east-1'
                )
            )
            
            # Use the new index
            index = pc.Index(new_index_name)
            pinecone_index_name = new_index_name
            print(f"Using new index: {new_index_name}")
        else:
            print(f"Using existing index: {pinecone_index_name}")
            index = pc.Index(pinecone_index_name)
            
    except Exception as e:
        print(f"Index doesn't exist or error checking: {e}")
        print(f"Creating new index '{pinecone_index_name}' with {EMBEDDING_DIMENSIONS} dimensions...")
        
        pc.create_index(
            name=pinecone_index_name,
            dimension=EMBEDDING_DIMENSIONS,
            metric='cosine',
            spec=ServerlessSpec(
                cloud='aws',
                region='us-east-1'
            )
        )
        index = pc.Index(pinecone_index_name)
    
    # Connect to PostgreSQL and fetch first 10 tweets
    print("Connecting to PostgreSQL...")
    conn = psycopg2.connect(database_url)
    
    try:
        with conn.cursor() as cursor:
            # Query for the specific fields we need
            query = """
                SELECT tweet_id, account_id, author_name, author_screen_name, text, text_len
                FROM tweets 
                LIMIT 10
            """
            cursor.execute(query)
            rows = cursor.fetchall()
            
            print(f"Retrieved {len(rows)} tweets from database")
            
            # Process each tweet
            vectors_to_upsert = []
            
            for row in rows:
                tweet_id, account_id, author_name, author_screen_name, text, text_len = row
                
                print(f"Processing tweet {tweet_id} by {author_screen_name}...")
                
                # Generate embedding for the tweet text
                emb_response = client.embeddings.create(
                    input=text,
                    model=EMBEDDING_MODEL
                )
                embedding = emb_response.data[0].embedding
                
                # Prepare metadata
                metadata = {
                    "tweet_id": str(tweet_id),
                    "account_id": str(account_id),
                    "author_name": author_name,
                    "author_screen_name": author_screen_name,
                    "text": text,
                    "text_len": text_len
                }
                
                # Prepare vector for upsert
                vector = {
                    "id": str(tweet_id),
                    "values": embedding,
                    "metadata": metadata
                }
                
                vectors_to_upsert.append(vector)
            
            # Upsert all vectors to Pinecone
            print(f"Upserting {len(vectors_to_upsert)} vectors to Pinecone index '{pinecone_index_name}'...")
            upsert_response = index.upsert(vectors=vectors_to_upsert)
            print(f"Upsert completed: {upsert_response}")
            
            # Get index stats
            stats = index.describe_index_stats()
            print(f"Index stats: {stats}")
            
    finally:
        conn.close()
        print("Database connection closed")


if __name__ == "__main__":
    main()