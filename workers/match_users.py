"""Worker 3 — Nightly matching.

For each user with a complete Career Twin, scores the latest ingested jobs
against their profile using core.match_jobs (one Gemini call per batch) and
upserts the results into the `matches` table.

This is what makes the Career Twin feel alive — after this worker runs,
the dashboard shows personalised "I found N new job matches" with ranked,
reasoned results.

Run manually:
    python3 workers/match_users.py [--dry-run] [--db PATH] [--max-jobs N]
               [--days-fresh N] [--batch-size N]

Schedule on Render Cron (nightly, after ingest_jobs):
    command: python3 workers/match_users.py --db /data/emploi.sqlite3

Design:
- Reads ALL users whose career_twin has onboarding_complete = True.
- Per user: fetches fresh jobs (ingested in the last `days_fresh` days) that
  haven't been matched yet, or re-scores all if --force.
- Batches job lists (batch_size jobs per Gemini call) to stay within prompt
  token limits and keep cost predictable.
- Cost guard: max_jobs cap per user per run; logged in the event.
- A single user failure doesn't stop the run.
- --dry-run prints what would be scored without calling Gemini or writing.
"""

import argparse
import logging
import os
import sys
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db
import core

log = logging.getLogger("emploi.match")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")

DEFAULT_MAX_JOBS = 200      # cap per user per run
DEFAULT_DAYS_FRESH = 7      # only match jobs ingested in this window
DEFAULT_BATCH_SIZE = 50     # jobs per Gemini call


def _get_model():
    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        return None
    import google.generativeai as genai
    genai.configure(api_key=key)
    return genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))


def _get_users_with_twins(conn) -> list:
    """All users with a completed Career Twin."""
    rows = conn.execute("SELECT user_id, data FROM career_twins").fetchall()
    users = []
    for row in rows:
        try:
            import json
            twin = json.loads(row["data"])
            if twin and isinstance(twin, dict) and twin.get("onboarding_complete"):
                users.append({"user_id": row["user_id"], "twin": twin})
        except Exception:
            pass
    return users


def _get_fresh_unmatched_jobs(conn, user_id: str, days_fresh: int,
                               max_jobs: int) -> list:
    """Jobs ingested in the last N days that this user hasn't been matched to."""
    rows = conn.execute(
        "SELECT j.* FROM ingested_jobs j "
        "WHERE j.fetched_at >= datetime('now', ? || ' days') "
        "  AND j.id NOT IN "
        "      (SELECT job_id FROM matches WHERE user_id = ?) "
        "ORDER BY j.fetched_at DESC LIMIT ?",
        (f"-{days_fresh}", user_id, max_jobs)).fetchall()
    return [dict(r) for r in rows]


def _batch(lst: list, size: int):
    """Yield successive chunks of size from lst."""
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def run(db_path: str, dry_run: bool = False,
        max_jobs: int = DEFAULT_MAX_JOBS,
        days_fresh: int = DEFAULT_DAYS_FRESH,
        batch_size: int = DEFAULT_BATCH_SIZE,
        model=None) -> dict:
    """Main matching run. model is injectable for tests.

    Returns summary dict: {ok, users_processed, total_matches, total_calls, errors}
    """
    conn = db.connect(db_path, check_same_thread=False)

    if model is None and not dry_run:
        model = _get_model()
        if model is None:
            log.error("GEMINI_API_KEY not set — matching worker cannot run without a model")
            return {"ok": False, "error": "GEMINI_API_KEY not configured",
                    "dry_run": dry_run}

    users = _get_users_with_twins(conn)
    if not users:
        log.info("no users with completed Career Twins — nothing to match")
        return {"ok": True, "users_processed": 0, "total_matches": 0,
                "total_calls": 0, "errors": [], "dry_run": dry_run}

    total_matches = total_calls = 0
    errors = []

    for user in users:
        user_id = user["user_id"]
        twin = user["twin"]

        try:
            jobs = _get_fresh_unmatched_jobs(conn, user_id, days_fresh, max_jobs)
            if not jobs:
                log.info("user %s — no fresh unmatched jobs", user_id[-8:])
                continue

            log.info("user %s — scoring %d jobs in batches of %d",
                     user_id[-8:], len(jobs), batch_size)

            if dry_run:
                for job in jobs:
                    print(f"  [dry-run] would score: {job.get('title')} @ "
                          f"{job.get('company_name')} for user …{user_id[-8:]}")
                total_matches += len(jobs)
                continue

            user_matches = 0
            for chunk in _batch(jobs, batch_size):
                try:
                    scored = core.match_jobs(model, twin, chunk)
                    total_calls += 1
                    for result in scored:
                        fit_score = result.get("fit_score")
                        if fit_score is None:
                            continue
                        job_id = result.get("id")
                        if job_id is None:
                            continue
                        db.upsert_match(conn, user_id, job_id,
                                        fit_score, result.get("reason", ""))
                        user_matches += 1
                except Exception as exc:
                    log.exception("batch failed for user %s: %s", user_id[-8:], exc)
                    errors.append(f"user {user_id[-8:]}: {exc}")

            total_matches += user_matches
            log.info("user %s — %d matches written", user_id[-8:], user_matches)
            db.log_event(conn, "MatchesGenerated",
                         {"user_suffix": user_id[-8:], "matches": user_matches,
                          "jobs_scored": len(jobs), "gemini_calls": total_calls},
                         user_id=user_id)

        except Exception as exc:
            log.exception("user %s failed: %s", user_id[-8:], exc)
            errors.append(f"user {user_id[-8:]}: {exc}")

    summary = {
        "ok": len(errors) == 0,
        "users_processed": len(users),
        "total_matches": total_matches,
        "total_calls": total_calls,
        "errors": errors,
        "dry_run": dry_run,
    }

    if not dry_run:
        db.log_event(conn, "MatchingWorkerRun", summary)

    log.info("matching complete — users=%d matches=%d gemini_calls=%d errors=%d",
             len(users), total_matches, total_calls, len(errors))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Emploi matching worker (Worker 3)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be scored; no Gemini calls, no DB writes")
    parser.add_argument("--db", default=os.getenv("EMPLOI_DB_PATH", "emploi.sqlite3"),
                        help="Path to SQLite database")
    parser.add_argument("--max-jobs", type=int, default=DEFAULT_MAX_JOBS,
                        help=f"Max jobs to score per user (default: {DEFAULT_MAX_JOBS})")
    parser.add_argument("--days-fresh", type=int, default=DEFAULT_DAYS_FRESH,
                        help=f"Only score jobs ingested in the last N days (default: {DEFAULT_DAYS_FRESH})")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
                        help=f"Jobs per Gemini call (default: {DEFAULT_BATCH_SIZE})")
    args = parser.parse_args()

    result = run(args.db, dry_run=args.dry_run, max_jobs=args.max_jobs,
                 days_fresh=args.days_fresh, batch_size=args.batch_size)
    sys.exit(0 if result["ok"] else 1)
