#!/usr/bin/env python3
"""
run_pipeline.py
===============
Full RSS extraction pipeline: poll feeds → fetch articles → extract text →
export CSV → push to Supabase → update speaker profiles → export recent-news
JSON.

Designed to run unattended in GitHub Actions, but works locally too.

Usage — local
-------------
::

    cd src/rss-extractor
    python run_pipeline.py
    python run_pipeline.py --dry-run             # skip Supabase & profile pushes
    python run_pipeline.py --skip-poll           # skip feed polling
    python run_pipeline.py --skip-profile-update # skip speaker-profile updates

Usage — GitHub Actions
----------------------
Set ``SUPABASE_URL``, ``SUPABASE_KEY``, and ``OPENAI_API_KEY`` as repository
secrets, then::

    - name: Run RSS extraction pipeline
      working-directory: src/rss-extractor
      run: python run_pipeline.py
      env:
        SUPABASE_URL:    ${{ secrets.SUPABASE_URL }}
        SUPABASE_KEY:    ${{ secrets.SUPABASE_KEY }}
        OPENAI_API_KEY:  ${{ secrets.OPENAI_API_KEY }}

Exit codes
----------
0   All stages completed without fatal errors.
1   A required credential is missing or a stage raised an unrecoverable error.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
import sys
import textwrap
from io import StringIO
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure the rss-extractor directory is importable as the package root so
# that ``from src.X import ...`` resolves correctly, whether the script is
# invoked from the project root or from inside src/rss-extractor/.
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

# ---------------------------------------------------------------------------
# Pipeline-stage imports (after sys.path fixup)
# ---------------------------------------------------------------------------
from src.adapters.supabase_export import records_to_csv, to_supabase_record  # noqa: E402
from src.agents.profile_updater import (  # noqa: E402
    ArticleForProfile,
    update_speaker_profiles,
)
from src.agents.recent_news_builder import (  # noqa: E402
    build_recent_news,
)
from src.extractor.models import RelevanceLevel  # noqa: E402
from src.pipelines.ingest_article import ingest_article  # noqa: E402
from src.pipelines.ingest_feed import ingest_feed  # noqa: E402
from src.scout.fetcher import fetch_article  # noqa: E402
from src.storage.document_store import load_raw_html, save_raw_html  # noqa: E402
from src.storage.sql import (  # noqa: E402
    get_feed_item,
    get_feed_items_pending_fetch,
    get_raw_articles_pending_extraction,
    init_schema,
    insert_raw_article,
)
from src.utils.config import (  # noqa: E402
    load_feeds,
    load_politicians,
    load_settings,
    load_topics,
)
from src.utils.logging import configure_logging  # noqa: E402

# ---------------------------------------------------------------------------
# GitHub Actions workflow command helpers
# ---------------------------------------------------------------------------

_IN_GITHUB_ACTIONS: bool = os.environ.get("GITHUB_ACTIONS") == "true"


def _gha(command: str, message: str, **params: str) -> None:
    """Emit a GitHub Actions workflow command to stdout."""
    if not _IN_GITHUB_ACTIONS:
        return
    param_str = ",".join(f"{k}={v}" for k, v in params.items())
    prefix = f"::{command} {param_str}::" if param_str else f"::{command}::"
    print(f"{prefix}{message}", flush=True)


def gha_error(message: str) -> None:
    _gha("error", message)


def gha_warning(message: str) -> None:
    _gha("warning", message)


def gha_notice(message: str) -> None:
    _gha("notice", message)


def gha_group(title: str) -> None:
    _gha("group", title)


def gha_endgroup() -> None:
    if _IN_GITHUB_ACTIONS:
        print("::endgroup::", flush=True)


def gha_set_output(name: str, value: str) -> None:
    """Write a step output to $GITHUB_OUTPUT (Actions ≥ 2022-10)."""
    output_file = os.environ.get("GITHUB_OUTPUT")
    if output_file:
        with open(output_file, "a", encoding="utf-8") as f:
            f.write(f"{name}={value}\n")


def _write_step_summary(markdown: str) -> None:
    """Append *markdown* to $GITHUB_STEP_SUMMARY if available."""
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as f:
            f.write(markdown + "\n")


# ---------------------------------------------------------------------------
# .env loader (for local runs; GitHub Actions injects secrets as env vars)
# ---------------------------------------------------------------------------

def _load_env(env_path: Path) -> None:
    """Load KEY=VALUE pairs from a .env file into os.environ.

    Skips blank lines and comments. Does not override variables already set
    in the environment, so GitHub Actions secrets always take precedence.
    """
    if not env_path.exists():
        return
    with env_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value


# ---------------------------------------------------------------------------
# Supabase push (inlined to avoid subprocess overhead in CI)
# ---------------------------------------------------------------------------

def _push_to_supabase(
    csv_text: str,
    table: str,
    batch_size: int,
) -> tuple[int, int, int]:
    """Insert rows from *csv_text* into Supabase, skipping duplicates.

    Returns ``(uploaded, skipped, errors)`` counts.
    """
    try:
        from supabase import create_client  # type: ignore[import-untyped]
    except ImportError:
        raise RuntimeError(
            "The 'supabase' package is required. "
            "Install it with: pip install supabase"
        )

    supabase_url = os.environ.get("SUPABASE_URL", "")
    supabase_key = os.environ.get("SUPABASE_KEY", "")
    if not supabase_url or not supabase_key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_KEY environment variables must be set."
        )

    rows: list[dict[str, str]] = list(csv.DictReader(StringIO(csv_text)))
    if not rows:
        return 0, 0, 0

    client = create_client(supabase_url, supabase_key)

    # Fetch existing doc_ids for deduplication
    existing_doc_ids: set[str] = set()
    offset = 0
    page_size = 1000
    while True:
        response = (
            client.table(table)
            .select("doc_id")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        batch = response.data or []
        if not batch:
            break
        for record in batch:
            existing_doc_ids.add(record["doc_id"])
        if len(batch) < page_size:
            break
        offset += page_size

    new_rows = [r for r in rows if r.get("doc_id") not in existing_doc_ids]
    skipped = len(rows) - len(new_rows)

    uploaded = 0
    errors = 0
    for i in range(0, len(new_rows), batch_size):
        batch = new_rows[i : i + batch_size]
        try:
            client.table(table).insert(batch).execute()
            uploaded += len(batch)
        except Exception as exc:
            errors += len(batch)
            gha_error(f"Supabase insert error on batch {i // batch_size + 1}: {exc}")
            print(f"  ERROR on batch {i // batch_size + 1}: {exc}", file=sys.stderr)

    return uploaded, skipped, errors


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent("""\
            Full RSS extraction pipeline.
            Stages: poll → fetch → extract → push to Supabase.
        """),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run all stages but skip the final Supabase push.",
    )
    parser.add_argument(
        "--table",
        default="news_articles",
        help="Supabase table name (default: news_articles).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Records per Supabase insert batch (default: 100).",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to .env file with credentials (default: .env).",
    )
    parser.add_argument(
        "--csv-out",
        default="output.csv",
        help="Path to write the exported CSV (default: output.csv).",
    )
    parser.add_argument(
        "--skip-poll",
        action="store_true",
        help="Skip the feed-polling stage.",
    )
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Skip the article-fetching stage.",
    )
    parser.add_argument(
        "--skip-extract",
        action="store_true",
        help="Skip the article-extraction stage.",
    )
    parser.add_argument(
        "--skip-profile-update",
        action="store_true",
        help="Skip the speaker-profile update stage (Stage 6).",
    )
    parser.add_argument(
        "--json-out",
        default="recent_news.json",
        help=(
            "Path to write the per-speaker recent-news JSON (default: "
            "recent_news.json). Written during Stage 6."
        ),
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main() -> None:  # noqa: C901  (complexity is acceptable for a pipeline runner)
    args = _parse_args()

    # Credentials: .env file for local runs; env vars take precedence in CI
    _load_env(Path(args.env_file))

    configure_logging()

    # -----------------------------------------------------------------------
    # Setup
    # -----------------------------------------------------------------------
    gha_group("Setup")
    print("=== Politics-Contradictor RSS Pipeline ===", flush=True)

    Path("data").mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect("data/tracker.db")
    conn.row_factory = sqlite3.Row
    init_schema(conn)

    settings = load_settings("config/settings.yaml")
    feeds = load_feeds("config/feeds.yaml")
    politicians = load_politicians("config/politicians.yaml")
    topics = load_topics("config/topics.yaml")
    data_dir = Path(settings.storage.data_dir)

    enabled_feeds = [f for f in feeds if f.enabled]
    print(f"Loaded {len(enabled_feeds)} enabled feed(s).", flush=True)
    print(f"Tracking {len(politicians)} politician(s).", flush=True)
    gha_endgroup()

    # -----------------------------------------------------------------------
    # Stage 1: Poll feeds
    # -----------------------------------------------------------------------
    gha_group("Stage 1 — Poll feeds")
    polled = 0
    new_items_total = 0
    if args.skip_poll:
        print("Stage 1 skipped (--skip-poll).", flush=True)
    else:
        for source in enabled_feeds:
            result = ingest_feed(source, conn, settings)
            polled += 1
            new_items_total += result.items_new
            print(
                f"  [{source.id}] {result.items_new} new item(s) "
                f"(status={result.status.value})",
                flush=True,
            )
        print(
            f"Stage 1 complete: polled {polled} feed(s), "
            f"{new_items_total} new item(s).",
            flush=True,
        )
    gha_endgroup()

    # -----------------------------------------------------------------------
    # Stage 2: Fetch articles
    # -----------------------------------------------------------------------
    gha_group("Stage 2 — Fetch articles")
    fetched_total = 0
    fetched_success = 0
    if args.skip_fetch:
        print("Stage 2 skipped (--skip-fetch).", flush=True)
    else:
        for item in get_feed_items_pending_fetch(conn):
            raw = fetch_article(item, settings)
            html_path = save_raw_html(raw.article_id, raw.html, data_dir)
            insert_raw_article(conn, raw, str(html_path))
            fetched_total += 1
            if raw.status.value == "success":
                fetched_success += 1
        failed_fetch = fetched_total - fetched_success
        if failed_fetch:
            gha_warning(f"{failed_fetch} article fetch(es) failed.")
        print(
            f"Stage 2 complete: fetched {fetched_total} article(s), "
            f"{fetched_success} succeeded.",
            flush=True,
        )
    gha_endgroup()

    # -----------------------------------------------------------------------
    # Stage 3: Extract articles
    # -----------------------------------------------------------------------
    gha_group("Stage 3 — Extract articles")
    supabase_records = []
    extracted_success = 0
    skipped_no_html = 0
    # Mapping of politician_id → (politician_name, articles) for Stages 6 & 7.
    articles_by_politician: dict[str, tuple[str, list[ArticleForProfile]]] = {}
    if args.skip_extract:
        print("Stage 3 skipped (--skip-extract).", flush=True)
    else:
        for raw_article in get_raw_articles_pending_extraction(conn):
            html = load_raw_html(raw_article.article_id, data_dir) or ""
            if not html:
                # Attempt one re-fetch before giving up
                feed_item = get_feed_item(conn, raw_article.feed_item_id)
                if feed_item is not None:
                    refetched = fetch_article(feed_item, settings)
                    if refetched.status.value == "success" and refetched.html:
                        save_raw_html(raw_article.article_id, refetched.html, data_dir)
                        html = refetched.html

            if not html:
                skipped_no_html += 1
                continue

            raw_article.html = html
            result = ingest_article(raw_article, conn, politicians, topics, settings)
            if result.extracted_article and result.extracted_article.body:
                record = to_supabase_record(
                    result.extracted_article, mentions=result.mentions
                )
                supabase_records.append(record)
                extracted_success += 1

                # Collect articles for each politician where relevance is not
                # IRRELEVANT, so that Stages 6 & 7 have meaningful content.
                article_for_profile = ArticleForProfile(
                    doc_id=result.extracted_article.article_id,
                    title=result.extracted_article.metadata.title,
                    body=result.extracted_article.body,
                    date=(
                        result.extracted_article.metadata.published_at.isoformat()
                        if result.extracted_article.metadata.published_at
                        else None
                    ),
                    link=(
                        result.extracted_article.metadata.canonical_url
                        or result.extracted_article.url
                    ),
                )
                for mention in result.mentions or []:
                    if mention.relevance == RelevanceLevel.IRRELEVANT:
                        continue
                    pid = mention.politician_id
                    if pid not in articles_by_politician:
                        articles_by_politician[pid] = (mention.politician_name, [])
                    articles_by_politician[pid][1].append(article_for_profile)

        if skipped_no_html:
            gha_warning(f"{skipped_no_html} article(s) skipped (no HTML body).")
        print(
            f"Stage 3 complete: extracted {extracted_success} article(s), "
            f"{skipped_no_html} skipped.",
            flush=True,
        )
    gha_endgroup()

    # -----------------------------------------------------------------------
    # Stage 4: Export CSV
    # -----------------------------------------------------------------------
    gha_group("Stage 4 — Export CSV")
    csv_text = records_to_csv(supabase_records)
    csv_path = Path(args.csv_out)
    csv_path.write_text(csv_text, encoding="utf-8")
    print(
        f"Stage 4 complete: wrote {len(supabase_records)} record(s) → {csv_path}",
        flush=True,
    )
    gha_endgroup()

    # -----------------------------------------------------------------------
    # Stage 5: Push to Supabase
    # -----------------------------------------------------------------------
    gha_group("Stage 5 — Push to Supabase")
    uploaded = skipped_dup = push_errors = 0
    if args.dry_run:
        print(
            f"Stage 5 skipped (--dry-run). "
            f"Would have pushed {len(supabase_records)} record(s) to "
            f"'{args.table}'.",
            flush=True,
        )
        gha_notice(f"Dry-run: {len(supabase_records)} record(s) ready for Supabase.")
    elif not supabase_records:
        print("Stage 5: nothing to push (0 new records).", flush=True)
    else:
        supabase_url = os.environ.get("SUPABASE_URL", "")
        supabase_key = os.environ.get("SUPABASE_KEY", "")
        if not supabase_url or not supabase_key:
            gha_error(
                "SUPABASE_URL and SUPABASE_KEY are not set. "
                "Add them as repository secrets."
            )
            print(
                "ERROR: SUPABASE_URL and SUPABASE_KEY must be set.\n"
                "  • GitHub Actions: add them as repository secrets.\n"
                "  • Local: create a .env file (see .env.example).",
                file=sys.stderr,
            )
            conn.close()
            sys.exit(1)

        try:
            uploaded, skipped_dup, push_errors = _push_to_supabase(
                csv_text, args.table, args.batch_size
            )
        except RuntimeError as exc:
            gha_error(str(exc))
            print(f"ERROR: {exc}", file=sys.stderr)
            conn.close()
            sys.exit(1)

        if push_errors:
            gha_error(f"{push_errors} record(s) failed to upload.")
        print(
            f"Stage 5 complete: uploaded={uploaded}, "
            f"duplicates_skipped={skipped_dup}, errors={push_errors}.",
            flush=True,
        )
    gha_endgroup()

    # -----------------------------------------------------------------------
    # Stage 6: Update speaker profiles & export recent-news JSON
    # -----------------------------------------------------------------------
    gha_group("Stage 6 — Update speaker profiles & export recent-news JSON")
    profiles_updated = profiles_skipped = profile_errors = profiles_datasets_only = 0
    recent_news_politicians: list[str] = []

    if args.skip_profile_update:
        print("Stage 6 skipped (--skip-profile-update).", flush=True)
    elif not articles_by_politician:
        print(
            "Stage 6: no politician articles collected — nothing to process.",
            flush=True,
        )
    else:
        openai_api_key = os.environ.get("OPENAI_API_KEY", "")
        base_url = os.environ.get(
            "OPENAI_BASE_URL", "https://api.openai.com/v1"
        )
        gpt_model = os.environ.get("GPT_MODEL", "gpt-4o-mini")

        if not openai_api_key:
            gha_warning(
                "OPENAI_API_KEY is not set — Stage 6 (profile update & "
                "recent-news generation) will be skipped."
            )
            print(
                "WARNING: OPENAI_API_KEY not set; skipping Stage 6.",
                file=sys.stderr,
            )
        else:
            # Stage 6a: Generate per-speaker recent-news summaries.
            # The result is keyed by politician_id and will be stored inside
            # the speaker_profiles.profile JSON column in Supabase (Stage 6b).
            # A name-keyed copy is also written to a JSON file for inspection.
            recent_news_serialized: dict[str, list[dict]] = {}
            print(
                f"Building recent-news summaries for "
                f"{len(articles_by_politician)} politician(s)…",
                flush=True,
            )
            try:
                recent_news = build_recent_news(
                    articles_by_politician=articles_by_politician,
                    openai_api_key=openai_api_key,
                    base_url=base_url,
                    gpt_model=gpt_model,
                )
                # Serialise keyed by politician_id for Supabase upsert.
                recent_news_serialized = {
                    pid: [item.to_dict() for item in items]
                    for pid, items in recent_news.items()
                }
                # Write a name-keyed JSON file for human inspection.
                name_keyed_news: dict[str, list[dict]] = {
                    articles_by_politician[pid][0]: items_dicts
                    for pid, items_dicts in recent_news_serialized.items()
                }
                json_path = Path(args.json_out)
                json_path.write_text(
                    json.dumps(name_keyed_news, indent=2),
                    encoding="utf-8",
                )
                print(
                    f"Stage 6a complete: wrote recent-news for "
                    f"{len(recent_news_serialized)} speaker(s) → {json_path}",
                    flush=True,
                )
            except Exception as exc:
                gha_warning(f"Recent-news generation failed: {exc}")
                print(
                    f"WARNING: recent-news generation failed: {exc}",
                    file=sys.stderr,
                )

            # Stage 6b: Update Supabase speaker_profiles table.
            # recent_news_serialized (keyed by politician_id) is merged into
            # each politician's profile JSON before upsert.
            supabase_url = os.environ.get("SUPABASE_URL", "")
            supabase_key = os.environ.get("SUPABASE_KEY", "")
            if not supabase_url or not supabase_key:
                gha_warning(
                    "SUPABASE_URL / SUPABASE_KEY not set — "
                    "skipping speaker-profile upserts."
                )
                print(
                    "WARNING: SUPABASE_URL/SUPABASE_KEY not set; "
                    "skipping profile upserts.",
                    file=sys.stderr,
                )
            else:
                print(
                    f"Updating speaker profiles for "
                    f"{len(articles_by_politician)} politician(s)…",
                    flush=True,
                )
                try:
                    update_result = update_speaker_profiles(
                        articles_by_politician=articles_by_politician,
                        supabase_url=supabase_url,
                        supabase_key=supabase_key,
                        openai_api_key=openai_api_key,
                        base_url=base_url,
                        gpt_model=gpt_model,
                        dry_run=args.dry_run,
                        recent_news_by_politician=recent_news_serialized or None,
                    )
                    profiles_updated = update_result.profiles_updated
                    profiles_skipped = update_result.profiles_skipped
                    profiles_datasets_only = update_result.datasets_only_updated
                    profile_errors = update_result.errors
                    if profile_errors:
                        gha_warning(
                            f"{profile_errors} speaker-profile upsert(s) failed."
                        )
                    print(
                        f"Stage 6b complete: profiles updated={profiles_updated}, "
                        f"datasets-only={profiles_datasets_only}, "
                        f"skipped={profiles_skipped}, errors={profile_errors}.",
                        flush=True,
                    )
                except Exception as exc:
                    gha_warning(f"Speaker-profile update failed: {exc}")
                    print(
                        f"WARNING: speaker-profile update failed: {exc}",
                        file=sys.stderr,
                    )
    gha_endgroup()

    # -----------------------------------------------------------------------
    # Write GitHub Actions step summary
    # -----------------------------------------------------------------------
    summary_lines = [
        "## RSS Pipeline Summary",
        "",
        "| Stage | Result |",
        "|-------|--------|",
        f"| 1 · Poll feeds | {polled} feed(s), {new_items_total} new item(s) |",
        f"| 2 · Fetch articles | {fetched_success}/{fetched_total} succeeded |",
        f"| 3 · Extract articles | {extracted_success} extracted, {skipped_no_html} skipped |",
        f"| 4 · Export CSV | {len(supabase_records)} record(s) → `{csv_path}` |",
    ]
    if args.dry_run:
        summary_lines.append(
            f"| 5 · Push to Supabase | ⏭ dry-run ({len(supabase_records)} ready) |"
        )
    else:
        summary_lines.append(
            f"| 5 · Push to Supabase | {uploaded} uploaded, "
            f"{skipped_dup} duplicates, {push_errors} errors |"
        )
    if args.skip_profile_update:
        summary_lines.append("| 6 · Speaker profiles & recent news | ⏭ skipped |")
    elif not articles_by_politician:
        summary_lines.append(
            "| 6 · Speaker profiles & recent news | ⏭ no articles |"
        )
    else:
        speakers_str = ", ".join(recent_news_politicians) or "none"
        summary_lines.append(
            f"| 6 · Speaker profiles & recent news | "
            f"profiles updated={profiles_updated}, "
            f"datasets-only={profiles_datasets_only}, "
            f"skipped={profiles_skipped}, "
            f"errors={profile_errors}; recent-news for: {speakers_str} |"
        )
    _write_step_summary("\n".join(summary_lines))

    # Expose key counts as step outputs for downstream jobs
    gha_set_output("new_feed_items", str(new_items_total))
    gha_set_output("extracted_articles", str(extracted_success))
    gha_set_output("uploaded_records", str(uploaded))
    gha_set_output("profiles_updated", str(profiles_updated))

    # -----------------------------------------------------------------------
    # Exit
    # -----------------------------------------------------------------------
    conn.close()
    if push_errors:
        sys.exit(1)
    print("\nPipeline finished successfully.", flush=True)


if __name__ == "__main__":
    main()
