"""Worker 1 — Job ingestion.

Fetches jobs from public Greenhouse and Lever board APIs (no API keys required),
normalises them into ingested_jobs, and logs counts to stdout.

Run manually:
    python3 workers/ingest_jobs.py [--dry-run] [--db PATH]

Schedule on Render Cron (daily):
    command: python3 workers/ingest_jobs.py --db /data/emploi.sqlite3

Design:
- Per-source try/except: one dead board or network blip never kills the run.
- All writes use db.upsert_job — idempotent, dedup on (source, source_job_id).
- --dry-run prints what would be written, touches nothing.
- Normalise to the shared job dict shape: title/company_name/description/
  location/is_remote/salary_text/apply_url/category.
"""

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import time
import urllib.request
import urllib.error
from typing import Optional, Union

# Allow running from repo root or from workers/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db

log = logging.getLogger("emploi.ingest")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")

SOURCES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "job_sources.json")

GREENHOUSE_BASE = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
LEVER_BASE = "https://api.lever.co/v0/postings/{slug}?mode=json"
REQUEST_TIMEOUT = 15
RATE_SLEEP = 0.5  # seconds between requests — be a polite client


# ---- HTTP helpers -----------------------------------------------------------

def _fetch(url: str) -> Optional[Union[dict, list]]:
    """GET url, return parsed JSON or None on any error."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Emploi-job-sourcer/1.0 (hello@emploihq.com)"})
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as r:
            return json.loads(r.read().decode())
    except Exception as exc:
        log.warning("fetch failed %s — %s", url, exc)
        return None


def _stable_id(*parts: str) -> str:
    """Hash-based stable id when a source lacks one."""
    h = hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()
    return h[:16]


# ---- Normalisation helpers --------------------------------------------------

_REMOTE_RE = re.compile(r"\bremote\b", re.IGNORECASE)


def _is_remote(text: str) -> bool:
    return bool(_REMOTE_RE.search(text or ""))


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()[:8000]


def _salary_from_greenhouse(job: dict) -> Optional[str]:
    """Extract salary range from Greenhouse keyed_custom_fields if present."""
    fields = job.get("keyed_custom_fields") or {}
    for key in ("salary_range", "compensation", "salary"):
        val = fields.get(key, {})
        if isinstance(val, dict) and val.get("value"):
            return str(val["value"])
    return None


# ---- Greenhouse ingestion ---------------------------------------------------

def _ingest_greenhouse(token: str, conn, dry_run: bool):
    """Fetch all jobs for one Greenhouse board token. Returns (fetched, written)."""
    url = GREENHOUSE_BASE.format(token=token)
    data = _fetch(url)
    if data is None:
        return 0, 0

    jobs = data.get("jobs") if isinstance(data, dict) else []
    if not jobs:
        log.info("greenhouse/%s — 0 jobs found", token)
        return 0, 0

    written = 0
    for job in jobs:
        job_id = str(job.get("id") or _stable_id(token, job.get("title", "")))
        location = (job.get("location") or {}).get("name", "")
        dept = ""
        if job.get("departments"):
            dept = job["departments"][0].get("name", "")

        fields = {
            "title": job.get("title", ""),
            "company_name": token.replace("-", " ").title(),
            "description": _strip_html(job.get("content", "")),
            "location": location,
            "is_remote": _is_remote(location) or _is_remote(job.get("content", "")),
            "salary_text": _salary_from_greenhouse(job),
            "apply_url": job.get("absolute_url", ""),
            "category": dept,
        }

        if dry_run:
            print(f"  [dry-run] greenhouse/{token} job {job_id}: {fields['title']}")
        else:
            db.upsert_job(conn, f"greenhouse/{token}", job_id, fields)
        written += 1

    return len(jobs), written


# ---- Lever ingestion --------------------------------------------------------

def _ingest_lever(slug: str, conn, dry_run: bool):
    """Fetch all postings for one Lever company slug. Returns (fetched, written)."""
    url = LEVER_BASE.format(slug=slug)
    data = _fetch(url)
    if data is None:
        return 0, 0

    postings = data if isinstance(data, list) else []
    if not postings:
        log.info("lever/%s — 0 postings found", slug)
        return 0, 0

    written = 0
    for posting in postings:
        job_id = posting.get("id") or _stable_id(
            slug, posting.get("text", ""), posting.get("createdAt", ""))
        cats = posting.get("categories") or {}
        location = cats.get("location", "")
        team = cats.get("team", "") or cats.get("department", "")
        workplace = posting.get("workplaceType", "")

        description = _strip_html(posting.get("descriptionPlain", "")
                                  or posting.get("description", ""))

        fields = {
            "title": posting.get("text", ""),
            "company_name": slug.replace("-", " ").title(),
            "description": description,
            "location": location,
            "is_remote": (workplace.lower() == "remote"
                          or _is_remote(location)
                          or _is_remote(description)),
            "salary_text": None,
            "apply_url": posting.get("hostedUrl", ""),
            "category": team,
        }

        if dry_run:
            print(f"  [dry-run] lever/{slug} job {job_id}: {fields['title']}")
        else:
            db.upsert_job(conn, f"lever/{slug}", str(job_id), fields)
        written += 1

    return len(postings), written


# ---- Entry point ------------------------------------------------------------

def run(db_path: str, dry_run: bool = False, fetch_fn=None) -> dict:
    """Main ingestion run. Returns summary dict for logging/testing.

    fetch_fn is injectable for tests: replaces _fetch(url) -> data.
    """
    global _fetch
    if fetch_fn is not None:
        _orig = _fetch
        _fetch = fetch_fn

    try:
        sources = json.loads(open(SOURCES_PATH).read())
    except Exception as exc:
        log.error("could not load job_sources.json: %s", exc)
        return {"ok": False, "error": str(exc)}

    conn = None if dry_run else db.connect(db_path, check_same_thread=False)

    total_fetched = total_written = 0
    errors = []

    for token in sources.get("greenhouse", []):
        try:
            f, w = _ingest_greenhouse(token, conn, dry_run)
            total_fetched += f
            total_written += w
            log.info("greenhouse/%s — %d fetched, %d written", token, f, w)
        except Exception as exc:
            log.exception("greenhouse/%s failed: %s", token, exc)
            errors.append(f"greenhouse/{token}: {exc}")
        time.sleep(RATE_SLEEP)

    for slug in sources.get("lever", []):
        try:
            f, w = _ingest_lever(slug, conn, dry_run)
            total_fetched += f
            total_written += w
            log.info("lever/%s — %d fetched, %d written", slug, f, w)
        except Exception as exc:
            log.exception("lever/%s failed: %s", slug, exc)
            errors.append(f"lever/{slug}: {exc}")
        time.sleep(RATE_SLEEP)

    summary = {
        "ok": len(errors) == 0,
        "fetched": total_fetched,
        "written": total_written,
        "errors": errors,
        "dry_run": dry_run,
    }

    if not dry_run and conn:
        db.log_event(conn, "JobIngestionRun", summary)

    log.info("ingestion complete — fetched=%d written=%d errors=%d",
             total_fetched, total_written, len(errors))

    if fetch_fn is not None:
        _fetch = _orig  # restore

    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Emploi job ingestion worker")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be written; touch nothing")
    parser.add_argument("--db", default=os.getenv("EMPLOI_DB_PATH", "emploi.sqlite3"),
                        help="Path to SQLite database")
    args = parser.parse_args()

    result = run(args.db, dry_run=args.dry_run)
    sys.exit(0 if result["ok"] else 1)
