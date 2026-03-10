import os
from dotenv import load_dotenv
from pathlib import Path
import psycopg2
from psycopg2 import sql

# Load .env
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

SUPABASE_URL = os.environ.get("SUPABASE_URL").strip('"')

print("=" * 70)
print("SUPABASE DATABASE INSPECTION")
print("=" * 70)

try:
    # Connect to Supabase
    print("\n📡 Connecting to Supabase...")
    conn = psycopg2.connect(SUPABASE_URL)
    print("✅ Connected successfully!")
    
    with conn.cursor() as cursor:
        # Get database name
        cursor.execute("SELECT current_database();")
        db_name = cursor.fetchone()[0]
        print(f"\n📊 Database: {db_name}")
        
        # Check if tweets table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'tweets'
            );
        """)
        table_exists = cursor.fetchone()[0]
        
        if not table_exists:
            print("\n❌ 'tweets' table does NOT exist in this database!")
            
            # List all tables
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name;
            """)
            tables = cursor.fetchall()
            print(f"\n📋 Available tables ({len(tables)}):")
            for table in tables:
                print(f"   - {table[0]}")
        else:
            print("\n✅ 'tweets' table found!")
            
            # Get table structure
            print("\n" + "=" * 70)
            print("TWEETS TABLE STRUCTURE")
            print("=" * 70)
            
            cursor.execute("""
                SELECT 
                    column_name, 
                    data_type, 
                    character_maximum_length,
                    is_nullable,
                    column_default
                FROM information_schema.columns
                WHERE table_name = 'tweets'
                ORDER BY ordinal_position;
            """)
            
            columns = cursor.fetchall()
            
            print(f"\n📋 Columns ({len(columns)}):")
            for col in columns:
                col_name, data_type, max_length, nullable, default = col
                length_str = f"({max_length})" if max_length else ""
                null_str = "NULL" if nullable == "YES" else "NOT NULL"
                default_str = f" DEFAULT {default}" if default else ""
                print(f"   {col_name:<25} {data_type}{length_str:<20} {null_str}{default_str}")
            
            # Check for indexes
            print("\n📑 Indexes:")
            cursor.execute("""
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE tablename = 'tweets'
                ORDER BY indexname;
            """)
            indexes = cursor.fetchall()
            for idx_name, idx_def in indexes:
                print(f"   {idx_name}")
                print(f"      {idx_def}")
            
            # Get row count
            print("\n📊 Data Statistics:")
            cursor.execute("SELECT COUNT(*) FROM tweets;")
            row_count = cursor.fetchone()[0]
            print(f"   Total rows: {row_count:,}")
            
            if row_count > 0:
                # Get sample data
                print("\n📄 Sample Data (first 3 rows):")
                cursor.execute("""
                    SELECT * FROM tweets 
                    ORDER BY created_at ASC 
                    LIMIT 3;
                """)
                sample_rows = cursor.fetchall()
                
                # Get column names
                col_names = [desc[0] for desc in cursor.description]
                
                for i, row in enumerate(sample_rows, 1):
                    print(f"\n   Row {i}:")
                    for col_name, value in zip(col_names, row):
                        # Truncate long text
                        if isinstance(value, str) and len(value) > 100:
                            value = value[:100] + "..."
                        print(f"      {col_name}: {value}")
                
                # Get author statistics
                print("\n👥 Top 10 Authors by Tweet Count:")
                cursor.execute("""
                    SELECT author_screen_name, COUNT(*) as count
                    FROM tweets
                    GROUP BY author_screen_name
                    ORDER BY count DESC
                    LIMIT 10;
                """)
                authors = cursor.fetchall()
                for author, count in authors:
                    print(f"   {author:<30} {count:>8,} tweets")
                
                # Date range
                print("\n📅 Date Range:")
                cursor.execute("""
                    SELECT 
                        MIN(created_at) as earliest,
                        MAX(created_at) as latest
                    FROM tweets;
                """)
                earliest, latest = cursor.fetchone()
                print(f"   Earliest: {earliest}")
                print(f"   Latest: {latest}")
            else:
                print("   ⚠️  Table is EMPTY!")
    
    conn.close()
    print("\n" + "=" * 70)
    print("✅ INSPECTION COMPLETE")
    print("=" * 70)

except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
