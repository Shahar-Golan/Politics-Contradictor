import os
from pathlib import Path

from dotenv import load_dotenv
import psycopg2


def main() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env" 
    load_dotenv(env_path)
    database_url = os.environ.get("DATABASE_URL")
    
    # Fallback if .env doesn't have DATABASE_URL
    if not database_url:
        database_url = "postgresql://postgres:Shir%40106@localhost:5432/politics"

    conn = psycopg2.connect(database_url)
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM tweets LIMIT 1;")
            row = cursor.fetchone()
            print("First tweet from database:")
            print(row)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
