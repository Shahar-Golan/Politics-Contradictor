import os
from pathlib import Path
from dotenv import load_dotenv
import psycopg2
from pinecone import Pinecone, ServerlessSpec
from openai import OpenAI
from tqdm import tqdm
import time


def main() -> None:
    # Load environment variables
    env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(env_path)
    
    # Get configuration from .env
    database_url = os.environ.get("SUPABASE_URL", "").strip('"')  # Use Supabase URL
    pinecone_api_key = os.environ.get("PINECONE_API_KEY")
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    pinecone_index_name = os.environ.get("PINECONE_INDEX_NAME", "politics")
    base_url = os.environ.get("BASE_URL", "https://api.llmod.ai/v1")
    
    # Validate database URL
    if not database_url:
        raise RuntimeError("SUPABASE_URL not found in .env file")
    
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
    EMBEDDING_DIMENSIONS = 1024  # Using 1024 dimensions to match 'politics' index
    
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
    
    # Connect to PostgreSQL with connection timeout settings
    print("Connecting to PostgreSQL...")
    conn = psycopg2.connect(
        database_url,
        connect_timeout=10,
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5
    )
    
    try:
        with conn.cursor() as cursor:
            # Get total tweet count
            cursor.execute("SELECT COUNT(*) FROM tweets")
            total_tweets = cursor.fetchone()[0]
            print(f"Total tweets in database: {total_tweets:,}")
            
            # Check current progress in Pinecone (resume capability)
            stats = index.describe_index_stats()
            existing_count = stats.get('total_vector_count', 0)
            
            if existing_count > 0:
                print(f"\n⚠️  Found {existing_count:,} existing vectors in Pinecone")
                response = input(f"   Resume from tweet {existing_count + 1}? (yes/no): ")
                if response.lower() in ['yes', 'y']:
                    start_offset = existing_count
                    tweets_remaining = total_tweets - existing_count
                    print(f"   Resuming from offset {start_offset:,}")
                else:
                    response = input(f"   Start from beginning (will skip duplicates)? (yes/no): ")
                    if response.lower() not in ['yes', 'y']:
                        print("Operation cancelled")
                        return
                    start_offset = 0
                    tweets_remaining = total_tweets
            else:
                start_offset = 0
                tweets_remaining = total_tweets
            
            # Batch processing configuration
            BATCH_SIZE = 100
            total_batches = (tweets_remaining + BATCH_SIZE - 1) // BATCH_SIZE
            
            print(f"\n📋 Processing Configuration:")
            print(f"   Starting from tweet: {start_offset + 1:,}")
            print(f"   Tweets to process: {tweets_remaining:,}")
            print(f"   Batch size: {BATCH_SIZE}")
            print(f"   Total batches: {total_batches:,}")
            print(f"   Estimated time: {total_batches * 0.5 / 60:.1f} - {total_batches * 2 / 60:.1f} minutes")
            print(f"   (Using batched API calls for 100x speed improvement!)\n")
            
            # Confirm before starting
            response = input(f"Start embedding? (yes/no): ")
            if response.lower() not in ['yes', 'y']:
                print("Operation cancelled")
                return
            
            embedded_count = 0
            error_count = 0
            skipped_count = 0
            
            print("\n🚀 Starting embedding process...\n")
            
            # Process tweets in batches
            with tqdm(total=tweets_remaining, desc="Embedding tweets", unit="tweet") as pbar:
                offset = start_offset
                
                while offset < total_tweets:
                    try:
                        # Fetch batch
                        cursor.execute("""
                            SELECT tweet_id, account_id, author_name, text, 
                                   created_at, has_urls
                            FROM tweets 
                            ORDER BY created_at ASC
                            LIMIT %s OFFSET %s
                        """, (BATCH_SIZE, offset))
                        
                        rows = cursor.fetchall()
                        
                        if not rows:
                            break
                        
                        # Extract texts and metadata for batch processing
                        tweet_data = []
                        texts_to_embed = []
                        
                        for row in rows:
                            tweet_id, account_id, author_name, text, created_at, has_urls = row
                            tweet_data.append({
                                'tweet_id': tweet_id,
                                'account_id': account_id,
                                'author_name': author_name,
                                'text': text,
                                'created_at': created_at,
                                'has_urls': has_urls
                            })
                            texts_to_embed.append(text)
                        
                        # 🚀 BATCH EMBEDDING: Send all texts at once (100x faster!)
                        try:
                            emb_response = client.embeddings.create(
                                input=texts_to_embed,  # Send all 100 texts at once!
                                model=EMBEDDING_MODEL,
                                dimensions=EMBEDDING_DIMENSIONS
                            )
                            
                            # Process batch results
                            vectors_to_upsert = []
                            
                            for i, tweet_info in enumerate(tweet_data):
                                try:
                                    embedding = emb_response.data[i].embedding
                                    
                                    # Prepare metadata
                                    metadata = {
                                        "account_id": str(tweet_info['account_id']),
                                        "author_name": tweet_info['author_name'],
                                        "created_at": str(tweet_info['created_at']),
                                        "has_urls": tweet_info['has_urls'],
                                        "text": tweet_info['text']
                                    }
                                    
                                    # Prepare vector for upsert
                                    vector = {
                                        "id": str(tweet_info['tweet_id']),
                                        "values": embedding,
                                        "metadata": metadata
                                    }
                                    
                                    vectors_to_upsert.append(vector)
                                    
                                except Exception as e:
                                    error_count += 1
                                    tqdm.write(f"Error processing tweet {tweet_info['tweet_id']}: {e}")
                                    continue
                            
                            # Upsert batch to Pinecone
                            if vectors_to_upsert:
                                try:
                                    index.upsert(vectors=vectors_to_upsert)
                                    embedded_count += len(vectors_to_upsert)
                                except Exception as e:
                                    error_count += len(vectors_to_upsert)
                                    tqdm.write(f"Error upserting batch: {e}")
                                    
                        except Exception as e:
                            error_count += len(rows)
                            tqdm.write(f"Error in batch embedding API call: {e}")
                        
                        # Update progress bar
                        pbar.update(len(rows))
                        offset += BATCH_SIZE
                        
                        # Small delay to avoid rate limiting
                        time.sleep(0.1)
                        
                    except psycopg2.OperationalError as e:
                        tqdm.write(f"\n⚠️  Database connection lost. Attempting to reconnect...")
                        try:
                            conn.close()
                            time.sleep(2)
                            conn = psycopg2.connect(
                                database_url,
                                connect_timeout=10,
                                keepalives=1,
                                keepalives_idle=30,
                                keepalives_interval=10,
                                keepalives_count=5
                            )
                            cursor = conn.cursor()
                            tqdm.write(f"✅ Reconnected! Continuing from offset {offset}")
                            continue
                        except Exception as reconnect_error:
                            tqdm.write(f"❌ Reconnection failed: {reconnect_error}")
                            break
            
            # Final report
            print(f"\n{'='*60}")
            print("EMBEDDING COMPLETE!")
            print(f"{'='*60}")
            print(f"✅ Successfully embedded: {embedded_count:,} tweets")
            if error_count > 0:
                print(f"⚠️  Errors: {error_count}")
            
            # Get final index stats
            stats = index.describe_index_stats()
            print(f"\n📊 Final Index Stats:")
            print(f"   Total vectors: {stats.get('total_vector_count', 0):,}")
            print(f"   Dimension: {stats.get('dimension', 'N/A')}")
            
    finally:
        conn.close()
        print("Database connection closed")


if __name__ == "__main__":
    main()