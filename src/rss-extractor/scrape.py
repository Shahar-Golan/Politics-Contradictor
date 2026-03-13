import sqlite3
from pathlib import Path

from src.utils.config import load_feeds, load_politicians, load_settings, load_topics
from src.storage.document_store import load_raw_html, save_raw_html
from src.storage.sql import (
    get_feed_item,
    get_feed_items_pending_fetch,
    get_raw_articles_pending_extraction,
    init_schema,
    insert_raw_article,
)
from src.pipelines.ingest_feed import ingest_feed
from src.pipelines.ingest_article import ingest_article
from src.scout.fetcher import fetch_article
from src.adapters.supabase_export import to_supabase_record, records_to_csv

# 1. Setup
Path("data").mkdir(parents=True, exist_ok=True)
conn = sqlite3.connect("data/tracker.db")
conn.row_factory = sqlite3.Row
init_schema(conn)

settings = load_settings("config/settings.yaml")
feeds = load_feeds("config/feeds.yaml")
politicians = load_politicians("config/politicians.yaml")
topics = load_topics("config/topics.yaml")

# 2. Poll feeds
polled_count = 0
for source in feeds:
    if source.enabled:
        ingest_feed(source, conn, settings)
        polled_count += 1
print(f"Polled feeds: {polled_count}")

# 3. Fetch articles
fetched_total = 0
fetched_success = 0
data_dir = Path(settings.storage.data_dir)
for item in get_feed_items_pending_fetch(conn):
    raw = fetch_article(item, settings)
    html_path = save_raw_html(raw.article_id, raw.html, data_dir)
    insert_raw_article(conn, raw, str(html_path))
    fetched_total += 1
    if raw.status.value == "success":
        fetched_success += 1
print(f"Fetched articles: {fetched_total} (success={fetched_success})")

# 4. Extract articles
supabase_records = []
extracted_success = 0
extraction_skipped_no_html = 0
for raw_article in get_raw_articles_pending_extraction(conn):
    html = load_raw_html(raw_article.article_id, data_dir) or ""
    if not html:
        feed_item = get_feed_item(conn, raw_article.feed_item_id)
        if feed_item is not None:
            refetched = fetch_article(feed_item, settings)
            if refetched.status.value == "success" and refetched.html:
                save_raw_html(raw_article.article_id, refetched.html, data_dir)
                html = refetched.html
    raw_article.html = html
    if not raw_article.html:
        extraction_skipped_no_html += 1
        continue

    result = ingest_article(raw_article, conn, politicians, topics, settings)
    if result.extracted_article and result.extracted_article.body:
        record = to_supabase_record(result.extracted_article, mentions=result.mentions)
        supabase_records.append(record)
        extracted_success += 1
print(f"Extracted articles: {extracted_success} (skipped_no_html={extraction_skipped_no_html})")

# 5. Export
csv_output = records_to_csv(supabase_records)
Path("output.csv").write_text(csv_output)
print(f"Exported records: {len(supabase_records)}")