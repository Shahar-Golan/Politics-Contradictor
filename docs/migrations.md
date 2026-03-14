# Migration Guide — Politics-Contradictor

## Overview

This document describes how schema changes should be handled across the two
database layers used by this project:

- **Local SQLite** — used by the `statement-processor` pipeline for offline development
- **Supabase (PostgreSQL)** — the production database (Phases 1–5)

---

## Local SQLite (statement-processor)

### Where the schema lives

The canonical local schema is defined in a single file:

```
src/statement-processor/src/db/schema.sql
```

This file is the **single source of truth** for the local SQLite database. All
three tables (`news_articles`, `stance_records`, `stance_relations`) are defined
here with `CREATE TABLE IF NOT EXISTS` statements.

### Applying the schema locally

To create or re-apply the schema:

```bash
cd src/statement-processor
python scripts/init_local_db.py
```

This is idempotent — running it multiple times is safe. The script calls
`src/db/init_db.py`, which reads `schema.sql` and executes it against the
local database file at `data/political_dossier.db`.

To use a different database path:

```bash
python scripts/init_local_db.py --db-path /tmp/my_test.db
```

### How to make a schema change

The project does not yet use a migration framework (e.g. Alembic, Flyway). The
current approach is:

1. **Edit `schema.sql`** — make your structural change to the canonical file.
2. **Drop and recreate the local database** — there is no incremental migration
   runner yet, so the simplest approach is to recreate the database from scratch:

   ```bash
   rm src/statement-processor/data/political_dossier.db
   python scripts/init_local_db.py
   python scripts/import_news_articles_csv.py  # re-import data if needed
   ```

3. **Update `docs/data_model.md`** — add or update the table description.
4. **Update `src/statement-processor/docs/stance_extraction_contract.md`** — if
   the change affects `stance_records` or the extraction output shape.
5. **Update the tests** — any test that asserts on column names, table structure,
   or row shapes must be updated in the same PR.
6. **Regenerate fixtures if needed** — if the contract changes, update the JSON
   fixtures under `src/statement-processor/tests/fixtures/`.

> **Rule:** Schema changes, documentation updates, and test updates go in the
> same PR. Never land a schema change without updating the docs.

### Type mapping compromises (SQLite vs Postgres)

The local SQLite schema makes the following compromises relative to the
production Supabase schema:

| Column | Postgres type | SQLite type | Notes |
|---|---|---|---|
| `speakers_mentioned` | `TEXT[]` | `TEXT` | Serialised as a JSON array string, e.g. `'["Alice","Bob"]'` |
| `created_at`, `updated_at` | `TIMESTAMPTZ` | `TEXT` | ISO-8601 string, e.g. `2025-01-15T12:00:00Z` |
| `id` (all tables) | `SERIAL` | `INTEGER PRIMARY KEY AUTOINCREMENT` | Semantically equivalent |
| `confidence` | `FLOAT` | `REAL` | Equivalent precision |
| `BOOLEAN` fields | `BOOLEAN` | `INTEGER` | 0/1 encoding |

These compromises are intentional. The ingestion layer (`import_news_articles.py`)
handles normalisation automatically when reading CSVs.

---

## Supabase (PostgreSQL)

### Current state

The Supabase schema for Phases 1–2 is documented in `docs/data_model.md`. There
is no migration runner configured yet for Supabase. Schema changes are currently
applied manually via the Supabase dashboard or SQL editor.

### Planned approach (Phase 5)

In Phase 5 (Deployment and automation), a proper migration approach will be
established. Candidates include:

- **Supabase Migrations** — Supabase CLI supports generating and applying SQL
  migration files. This is the preferred approach.
- **Alembic** — if a Python-native migration runner is needed.

Until Phase 5, contributors should:

1. Apply Supabase schema changes manually using the Supabase SQL editor.
2. Document the change in `docs/data_model.md`.
3. Ensure the change is backward compatible where possible.

---

## Schema change PR checklist

When opening a PR that changes any schema:

- [ ] `src/statement-processor/src/db/schema.sql` updated (if local schema changed)
- [ ] `docs/data_model.md` updated (if Supabase or local schema changed)
- [ ] `src/statement-processor/docs/stance_extraction_contract.md` updated (if extraction output shape changed)
- [ ] Tests updated for column or structure changes
- [ ] Fixtures updated if contract changed
- [ ] No schema change is mixed with unrelated refactors in the same PR

---

## Adding a new table

### Local SQLite

1. Add `CREATE TABLE IF NOT EXISTS <name> (...)` to `schema.sql`.
2. Run `python scripts/init_local_db.py` to apply.
3. Add a test to `tests/test_db_bootstrap.py` asserting the table exists.
4. Document the table in `docs/data_model.md`.

### Supabase

1. Apply the `CREATE TABLE` statement in the Supabase SQL editor.
2. Document the table in `docs/data_model.md`.
3. Update Pinecone metadata documentation in `docs/data_model.md` if applicable.

---

## Renaming or dropping a column

Because there is no migration runner yet:

1. Edit `schema.sql` with the new column name or remove the column.
2. Drop and recreate the local database.
3. Update all code that references the old column name.
4. Update `docs/data_model.md`.
5. Update the extraction contract if applicable.
6. Update tests and fixtures.

Include all of these steps in one PR.
