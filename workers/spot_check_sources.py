"""Spot-check every active job source against its live ATS API.

Solves the launch-checklist item "spot-check 10 of 130 job source tokens":
a token that guesses wrong (e.g. `boards.greenhouse.io/pistack` instead of
`paystack`) returns 0 jobs forever without erroring — the ingest worker's
graceful-per-source behaviour hides the miss. This script hits each source
once, prints a per-source line with fetched count, and exits non-zero if any
active source came back with zero jobs.

It does NOT write to the DB — it uses the ingest worker's dry-run path so
running it is safe on prod.

Run locally:
    python3 workers/spot_check_sources.py
Run against prod's seeded sources (reads them from the DB):
    python3 workers/spot_check_sources.py --db /var/data/emploi.sqlite3 --from-db

Exit code: 0 if every checked source returned >0 jobs OR the run was
otherwise clean; non-zero if any active source returned 0 (candidate for
disabling or subdomain correction).
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


def _load_sources_from_json(path: str) -> list:
    """Read the JSON seed file. Ignores _doc keys, only picks entries with a token."""
    raw = json.loads(open(path).read())
    out = []
    for category, entries in raw.items():
        if category.startswith("_") or not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get("token"):
                continue
            out.append({
                "company": entry.get("company", ""),
                "ats": entry.get("ats", ""),
                "token": entry["token"],
                "priority": int(entry.get("priority", 5)),
                "active": bool(entry.get("active", True)),
                "region": entry.get("region", ""),
            })
    return out


def _load_sources_from_db(db_path: str) -> list:
    conn = db.connect(db_path, check_same_thread=False)
    return list(db.list_job_sources(conn))


def run(db_path: Optional[str] = None, from_db: bool = False,
        include_inactive: bool = False, only_ats: Optional[str] = None,
        sleep_fn=time.sleep, fetch_fn=None) -> dict:
    """Return {ok, checked, dead, sources: [{company, ats, token, active, fetched, note}]}.

    ok=True iff no active-and-supported source returned 0 jobs.
    Inactive or unsupported-ATS sources never count against ok.
    """
    if from_db:
        if not db_path:
            raise ValueError("--from-db requires --db")
        sources = _load_sources_from_db(db_path)
    else:
        sources = _load_sources_from_json(ingest_worker.SOURCES_PATH)

    if only_ats:
        sources = [s for s in sources if s["ats"] == only_ats]

    results = []
    dead_active = 0

    for src in sources:
        active = bool(src.get("active", True))
        ats = src.get("ats", "")
        handler = ingest_worker._ATS_HANDLERS.get(ats)

        if not active and not include_inactive:
            results.append({**src, "fetched": None, "note": "skipped (inactive)"})
            continue
        if handler is None:
            results.append({**src, "fetched": None,
                            "note": f"skipped (no handler for ats={ats!r})"})
            continue

        # Use the worker's per-handler function with dry_run=True so no writes
        # happen. Temporarily override _fetch if the caller passed one (tests).
        if fetch_fn is not None:
            _orig = ingest_worker._fetch
            ingest_worker._fetch = fetch_fn
        try:
            fetched, _written = handler(src, None, True)
        except Exception as exc:
            results.append({**src, "fetched": 0, "note": f"error: {exc}"})
            if active:
                dead_active += 1
            continue
        finally:
            if fetch_fn is not None:
                ingest_worker._fetch = _orig

        note = "ok" if fetched > 0 else "DEAD — 0 jobs returned"
        if fetched == 0 and active:
            dead_active += 1
        results.append({**src, "fetched": fetched, "note": note})
        sleep_fn(0.25)

    # Print a readable table
    ats_col = max((len(r["ats"]) for r in results), default=4)
    for r in results:
        fetched = "—" if r["fetched"] is None else str(r["fetched"])
        print(f"  {r['ats']:<{ats_col}}  {r['token']:<28}  fetched={fetched:>4}  {r['note']}   [{r['company']}]")

    print(f"\nchecked {sum(1 for r in results if r['fetched'] is not None)} sources, "
          f"{dead_active} active source(s) returned 0 jobs "
          f"(skipped: {sum(1 for r in results if r['fetched'] is None)})")
    return {"ok": dead_active == 0, "checked": len(results),
            "dead_active": dead_active, "sources": results}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=os.getenv("EMPLOI_DB_PATH", "emploi.sqlite3"))
    p.add_argument("--from-db", action="store_true",
                   help="Read seeded sources from the DB instead of the JSON file")
    p.add_argument("--include-inactive", action="store_true",
                   help="Also probe sources currently marked active=false")
    p.add_argument("--only-ats", default=None,
                   help="Limit to one ATS (greenhouse|lever|ashby|workable|smartrecruiters)")
    args = p.parse_args()
    result = run(args.db, from_db=args.from_db,
                 include_inactive=args.include_inactive,
                 only_ats=args.only_ats)
    sys.exit(0 if result["ok"] else 1)
