"""Load 3DLNews articles from parquet into Supabase + Pinecone.

1. Creates `news_articles` table in Supabase (if not exists)
2. Inserts article records into the table
3. Creates `politics-news` Pinecone index (if not exists)
4. Embeds article text and upserts vectors

Usage:
    python -m Politics-Contradictor.src.load_news_to_supabase_and_pinecone
    # or from the Politics-Contradictor directory:
    python src/load_news_to_supabase_and_pinecone.py
"""

import json
import os
import sys
import time
from pathlib import Path

import pandas as pd
import psycopg2
from dotenv import load_dotenv
from openai import OpenAI
from pinecone import Pinecone, ServerlessSpec

# Load environment
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_path)

# Config
PARQUET_PATH = Path(__file__).resolve().parent.parent.parent / \
    "data_collection" / "preprocessing" / "output" / "three_dl_news.parquet"

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip('"')
PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
BASE_URL = os.environ.get("BASE_URL", "https://api.llmod.ai/v1")

PINECONE_INDEX_NAME = "politics-news"
EMBEDDING_MODEL = "RPRTHPB-text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1024
BATCH_SIZE = 50


# ── Step 1: Supabase ─────────────────────────────────────────────────────────

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS news_articles (
    id              SERIAL PRIMARY KEY,
    doc_id          TEXT UNIQUE NOT NULL,
    title           TEXT,
    text            TEXT NOT NULL,
    date            TEXT,
    media_name      TEXT,
    media_type      TEXT,
    source_platform TEXT,
    state           TEXT,
    city            TEXT,
    link            TEXT,
    speakers_mentioned TEXT[],
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
"""

INSERT_SQL = """
INSERT INTO news_articles (doc_id, title, text, date, media_name, media_type,
                           source_platform, state, city, link, speakers_mentioned)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (doc_id) DO NOTHING;
"""


def load_to_supabase(df: pd.DataFrame) -> int:
    """Create table and insert records into Supabase."""
    print("\n--- SUPABASE ---")
    print(f"Connecting to Supabase...")
    conn = psycopg2.connect(
        SUPABASE_URL,
        connect_timeout=10,
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
    )

    try:
        conn.autocommit = True
        with conn.cursor() as cursor:
            cursor.execute(CREATE_TABLE_SQL)
            print("Table `news_articles` ready.")

        # Insert in batches with explicit commits
        inserted = 0
        conn.autocommit = False
        DB_BATCH = 50

        for batch_start in range(0, len(df), DB_BATCH):
            batch_df = df.iloc[batch_start:batch_start + DB_BATCH]
            with conn.cursor() as cursor:
                for _, row in batch_df.iterrows():
                    meta = json.loads(row["extra_metadata"])
                    speakers = meta.get("speakers_mentioned", [])

                    cursor.execute(INSERT_SQL, (
                        row["doc_id"],
                        row["title"],
                        row["text"][:50000],    # cap text size
                        row["date"],
                        row["source"],
                        meta.get("media_type", ""),
                        meta.get("source_platform", ""),
                        meta.get("state", ""),
                        meta.get("city", ""),
                        meta.get("link", ""),
                        speakers,
                    ))
                    inserted += 1

            conn.commit()
            print(f"  Inserted {inserted}/{len(df)}...")

        # Verify
        conn.autocommit = True
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM news_articles")
            total = cursor.fetchone()[0]
        print(f"\nSupabase done: {inserted} inserted, {total} total in table.")
        return inserted

    finally:
        conn.close()


# ── Step 2: Pinecone ─────────────────────────────────────────────────────────

def load_to_pinecone(df: pd.DataFrame) -> int:
    """Create index and upsert embeddings to Pinecone."""
    print("\n--- PINECONE ---")

    pc = Pinecone(api_key=PINECONE_API_KEY)
    client = OpenAI(api_key=OPENAI_API_KEY, base_url=BASE_URL)

    # Create or connect to index
    existing = [idx.name for idx in pc.list_indexes()]
    if PINECONE_INDEX_NAME not in existing:
        print(f"Creating index '{PINECONE_INDEX_NAME}'...")
        pc.create_index(
            name=PINECONE_INDEX_NAME,
            dimension=EMBEDDING_DIMENSIONS,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
        # Wait for index to be ready
        time.sleep(5)
    else:
        print(f"Index '{PINECONE_INDEX_NAME}' already exists.")

    index = pc.Index(PINECONE_INDEX_NAME)
    stats = index.describe_index_stats()
    print(f"Current vectors: {stats.total_vector_count:,}")

    # Process in batches
    total_upserted = 0
    records = df.to_dict("records")

    for batch_start in range(0, len(records), BATCH_SIZE):
        batch = records[batch_start:batch_start + BATCH_SIZE]

        # Prepare texts for embedding (title + text, truncated)
        texts = []
        for rec in batch:
            # Combine title and text for richer embedding
            combined = f"{rec['title']}\n\n{rec['text']}"
            # Truncate to ~8000 chars to stay within token limits
            texts.append(combined[:8000])

        # Batch embed
        try:
            emb_response = client.embeddings.create(
                input=texts,
                model=EMBEDDING_MODEL,
                dimensions=EMBEDDING_DIMENSIONS,
            )
        except Exception as e:
            print(f"  Embedding error at batch {batch_start}: {e}")
            continue

        # Build vectors
        vectors = []
        for i, rec in enumerate(batch):
            meta = json.loads(rec["extra_metadata"])
            vectors.append({
                "id": rec["doc_id"],
                "values": emb_response.data[i].embedding,
                "metadata": {
                    "doc_id": rec["doc_id"],
                    "title": rec["title"][:200],
                    "text": rec["text"][:500],
                    "date": rec["date"],
                    "media_name": rec["source"],
                    "media_type": meta.get("media_type", ""),
                    "state": meta.get("state", ""),
                    "link": meta.get("link", ""),
                    "speakers_mentioned": meta.get("speakers_mentioned", []),
                    "type": "news_article",
                },
            })

        # Upsert
        try:
            index.upsert(vectors=vectors)
            total_upserted += len(vectors)
            print(f"  Upserted {total_upserted}/{len(records)}...")
        except Exception as e:
            print(f"  Upsert error at batch {batch_start}: {e}")

        time.sleep(0.2)  # Rate limit buffer

    stats = index.describe_index_stats()
    print(f"\nPinecone done: {total_upserted} upserted, "
          f"{stats.total_vector_count:,} total vectors.")
    return total_upserted


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print(f"Loading parquet: {PARQUET_PATH}")
    if not PARQUET_PATH.exists():
        print(f"ERROR: {PARQUET_PATH} not found!")
        sys.exit(1)

    df = pd.read_parquet(PARQUET_PATH)
    print(f"Records: {len(df)}")

    load_to_supabase(df)
    load_to_pinecone(df)

    print("\n=== ALL DONE ===")


if __name__ == "__main__":
    main()
