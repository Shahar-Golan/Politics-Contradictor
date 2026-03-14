-- schema.sql
-- ============================================================
-- Local SQLite schema for the statement-processor pipeline.
--
-- Tables:
--   news_articles   – imported from CSV export
--   stance_records  – extraction output, one row per stance
--   stance_relations – pairwise relations between stances
--
-- SQLite type notes:
--   * speakers_mentioned : stored as a JSON text string
--     (Postgres TEXT[] → SQLite TEXT, serialised with json.dumps)
--   * DATETIME columns use ISO-8601 text (SQLite has no native DATETIME)
--   * BOOLEAN columns use INTEGER (0/1)
-- ============================================================

-- ------------------------------------------------------------
-- news_articles
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS news_articles (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id           TEXT    NOT NULL UNIQUE,
    title            TEXT,
    text             TEXT,
    date             TEXT,
    media_name       TEXT,
    media_type       TEXT,
    source_platform  TEXT,
    state            TEXT,
    city             TEXT,
    link             TEXT,
    -- Postgres TEXT[] serialised as a JSON array string, e.g. '["Speaker A","Speaker B"]'
    speakers_mentioned TEXT DEFAULT '[]',
    created_at       TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- ------------------------------------------------------------
-- stance_records
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS stance_records (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id                 TEXT    NOT NULL,
    politician             TEXT,
    topic                  TEXT,
    subtopic               TEXT,
    normalized_proposition TEXT,
    stance_direction       TEXT,
    stance_mode            TEXT,
    speaker                TEXT,
    event_date             TEXT,
    event_date_precision   TEXT,
    evidence_role          TEXT,
    quote_text             TEXT,
    quote_start_char       INTEGER,
    quote_end_char         INTEGER,
    paraphrase             TEXT,
    confidence             REAL,
    review_status          TEXT    DEFAULT 'pending',
    created_at             TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at             TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (doc_id) REFERENCES news_articles (doc_id)
);

-- ------------------------------------------------------------
-- stance_relations
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS stance_relations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    from_stance_id INTEGER NOT NULL,
    to_stance_id   INTEGER NOT NULL,
    relation_type  TEXT    NOT NULL,
    confidence     REAL,
    reason         TEXT,
    created_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (from_stance_id) REFERENCES stance_records (id),
    FOREIGN KEY (to_stance_id)   REFERENCES stance_records (id)
);
