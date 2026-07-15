"""Heal the job_sources DB by disabling sources whose ATS endpoint returns 0 jobs.

The seed at `data/job_sources.json` was verified on 2026-07-15 and 85 of 100
active tokens returned 0 jobs — some companies rotated their board slugs, some
migrated to Ashby/Workable, some pulled the public feed. The JSON has been
patched for fresh installs, but a running prod DB still has the stale rows
(the DB is source of truth after first seed). This script probes each active
DB source once, disables the dead ones via `db.set_job_source_active`, and
logs a summary event.

Safe on prod: never touches jobs / matches / trust records — only flips the
`active` column on job_sources. Use `--dry-run` to preview without writing.

Run locally:
    python3 workers/heal_job_sources.py --dry-run
Run against prod:
    python3 workers/heal_job_sources.py --db /var/data/emploi.sqlite3

Followed by (optional) a spot_check to confirm all remaining active sources
now return >0 jobs:
    python3 workers/spot_check_sources.py --from-db --db /var/data/emploi.sqlite3
"""
import argparse
import json
import os
import sys
import time
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db  # noqa: E402
import workers.ingest_jobs as ingest_worker  # noqa: E402


def run(db_path: str, dry_run: bool = False,
        sleep_fn=time.sleep, fetch_fn=None) -> dict:
    """Probe every active DB source, disable the dead ones.

    Returns {ok, disabled, kept_active, unsupported, dead_sources, dry_run}.
    An unsupported-ATS source (e.g. career_page) is never disabled — it's
    already skipped by the ingest worker's handler dispatch, and disabling
    would lose the "we know about this employer but can't source yet" note.
    """
    conn = db.connect(db_path, check_same_thread=False)
    sources = db.list_job_sources(conn, active_only=True)

    if fetch_fn is not None:
        _orig = ingest_worker._fetch
        ingest_worker._fetch = fetch_fn

    try:
        disabled: list = []
        kept: list = []
        unsupported: list = []

        for src in sources:
            ats = src.get("ats", "")
            handler = ingest_worker._ATS_HANDLERS.get(ats)
            if handler is None:
                # e.g. career_page — no probe possible; leave the active flag
                # alone since the ingest worker's dispatcher already no-ops it.
                unsupported.append({"id": src["id"], "ats": ats,
                                    "company": src.get("company", ""),
                                    "token": src.get("token", "")})
                continue

            try:
                fetched, _written = handler(src, None, True)
            except Exception as exc:
                # Unexpected handler error — treat as dead but note the reason.
                fetched = 0
                error = str(exc)
            else:
                error = None

            row = {"id": src["id"], "ats": ats,
                   "company": src.get("company", ""),
                   "token": src.get("token", ""),
                   "fetched": fetched, "error": error}

            if fetched > 0:
                kept.append(row)
            else:
                disabled.append(row)
                if not dry_run:
                    db.set_job_source_active(conn, src["id"], False)

            sleep_fn(0.25)

        summary = {
            "ok": True,
            "disabled": len(disabled),
            "kept_active": len(kept),
            "unsupported": len(unsupported),
            "dead_sources": disabled,
            "dry_run": dry_run,
        }

        # Print a readable table
        ats_col = max((len(r["ats"]) for r in disabled + kept), default=4)
        for r in kept:
            print(f"  KEEP    {r['ats']:<{ats_col}}  {r['token']:<28}  "
                  f"fetched={r['fetched']:>4}   [{r['company']}]")
        for r in disabled:
            action = "would disable" if dry_run else "DISABLED"
            print(f"  {action}  {r['ats']:<{ats_col}}  {r['token']:<28}  "
                  f"fetched=   0   [{r['company']}]")

        print(f"\n{'[dry-run] ' if dry_run else ''}"
              f"kept={len(kept)} disabled={len(disabled)} "
              f"unsupported={len(unsupported)}")

        if not dry_run:
            db.log_event(conn, "HealJobSourcesRun", {
                "disabled": len(disabled),
                "kept_active": len(kept),
                "unsupported": len(unsupported),
                "disabled_ids": [r["id"] for r in disabled],
            })

    finally:
        if fetch_fn is not None:
            ingest_worker._fetch = _orig

    return summary


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=os.getenv("EMPLOI_DB_PATH", "emploi.sqlite3"))
    p.add_argument("--dry-run", action="store_true",
                   help="Print what would be disabled; touch nothing")
    args = p.parse_args()
    result = run(args.db, dry_run=args.dry_run)
    sys.exit(0 if result["ok"] else 1)
