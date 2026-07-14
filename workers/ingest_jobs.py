"""Worker 1 — Job ingestion.

Fetches jobs from public Greenhouse and Lever board APIs (no API keys required),
normalises them into ingested_jobs, and logs counts to stdout.

Source list comes from the `job_sources` DB table (seeded from
data/job_sources.json on first run). After seeding, the DB is the source
of truth — add/remove/disable sources via the admin API or directly in the DB.

Priority governs polling frequency when used with an external scheduler:
  10 = hourly, 7 = every 3h, 5 = twice daily, 1 = daily
Pass --min-priority N to only run sources at or above that threshold.

Run manually:
    python3 workers/ingest_jobs.py [--dry-run] [--db PATH] [--min-priority N]

Schedule on Render Cron (daily, all sources):
    command: python3 workers/ingest_jobs.py --db /data/emploi.sqlite3
"""

import argparse
import hashlib
import html as html_lib
import json
import logging
import os
import re
import sys
import time
import urllib.request
import urllib.error
from typing import Optional, Union

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
ASHBY_BASE = "https://api.ashbyhq.com/posting-public/apiPostings/{token}"
REQUEST_TIMEOUT = 15
RATE_SLEEP = 0.5


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
    h = hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()
    return h[:16]


# ---- Normalisation helpers --------------------------------------------------

_REMOTE_RE = re.compile(r"\bremote\b", re.IGNORECASE)


def _is_remote(text: str) -> bool:
    return bool(_REMOTE_RE.search(text or ""))


def _strip_html(text: str) -> str:
    # Greenhouse's `content` field arrives HTML-ESCAPED (&lt;div&gt;...), so
    # unescape first or the tag-stripper sees no tags and the entity soup
    # ends up in stored descriptions and match prompts (was a real bug).
    # Unescape twice for double-encoded payloads; plain text is unaffected.
    text = html_lib.unescape(html_lib.unescape(text or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:8000]


def _salary_from_greenhouse(job: dict) -> Optional[str]:
    fields = job.get("keyed_custom_fields") or {}
    for key in ("salary_range", "compensation", "salary"):
        val = fields.get(key, {})
        if isinstance(val, dict) and val.get("value"):
            return str(val["value"])
    return None


# ---- Per-ATS ingestion ------------------------------------------------------

def _ingest_greenhouse(source: dict, conn, dry_run: bool):
    """Fetch all jobs for one Greenhouse board token. Returns (fetched, written)."""
    token = source["token"]
    url = GREENHOUSE_BASE.format(token=token)
    data = _fetch(url)
    if data is None:
        return 0, 0

    jobs = data.get("jobs") if isinstance(data, dict) else []
    if not jobs:
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
            "company_name": source.get("company", token.replace("-", " ").title()),
            "description": _strip_html(job.get("content", "")),
            "location": location,
            "is_remote": _is_remote(location) or _is_remote(job.get("content", "")),
            "salary_text": _salary_from_greenhouse(job),
            "apply_url": job.get("absolute_url", ""),
            "category": dept,
        }

        source_key = f"greenhouse/{token}"
        if dry_run:
            print(f"  [dry-run] {source_key} job {job_id}: {fields['title']}")
        else:
            db.upsert_job(conn, source_key, job_id, fields)
        written += 1

    return len(jobs), written


def _ingest_lever(source: dict, conn, dry_run: bool):
    """Fetch all postings for one Lever company slug. Returns (fetched, written)."""
    slug = source["token"]
    url = LEVER_BASE.format(slug=slug)
    data = _fetch(url)
    if data is None:
        return 0, 0

    postings = data if isinstance(data, list) else []
    if not postings:
        return 0, 0

    written = 0
    for posting in postings:
        job_id = posting.get("id") or _stable_id(
            slug, posting.get("text", ""), str(posting.get("createdAt", "")))
        cats = posting.get("categories") or {}
        location = cats.get("location", "")
        team = cats.get("team", "") or cats.get("department", "")
        workplace = posting.get("workplaceType", "")
        description = _strip_html(posting.get("descriptionPlain", "")
                                  or posting.get("description", ""))

        fields = {
            "title": posting.get("text", ""),
            "company_name": source.get("company", slug.replace("-", " ").title()),
            "description": description,
            "location": location,
            "is_remote": (workplace.lower() == "remote"
                          or _is_remote(location)
                          or _is_remote(description)),
            "salary_text": None,
            "apply_url": posting.get("hostedUrl", ""),
            "category": team,
        }

        source_key = f"lever/{slug}"
        if dry_run:
            print(f"  [dry-run] {source_key} job {job_id}: {fields['title']}")
        else:
            db.upsert_job(conn, source_key, str(job_id), fields)
        written += 1

    return len(postings), written


def _ingest_ashby(source: dict, conn, dry_run: bool):
    """Fetch public Ashby postings. The API has varied between a top-level
    list and {jobs: [...]}; support both without coupling to optional fields."""
    token = source["token"]
    data = _fetch(ASHBY_BASE.format(token=token))
    postings = data.get("jobs", []) if isinstance(data, dict) else data
    if not isinstance(postings, list):
        return 0, 0
    written = 0
    for posting in postings:
        if not isinstance(posting, dict):
            continue
        job_id = str(posting.get("id") or posting.get("jobUrl") or _stable_id(token, posting.get("title", "")))
        location = str(posting.get("location") or posting.get("locationName") or "")
        description = _strip_html(str(posting.get("descriptionHtml") or posting.get("descriptionPlain") or posting.get("description") or ""))
        fields = {"title": posting.get("title", ""),
                  "company_name": source.get("company", token.replace("-", " ").title()),
                  "description": description, "location": location,
                  "is_remote": _is_remote(location) or _is_remote(description),
                  "salary_text": None,
                  "apply_url": posting.get("jobUrl") or posting.get("applyUrl") or "",
                  "category": posting.get("department") or posting.get("team") or ""}
        source_key = f"ashby/{token}"
        if dry_run:
            print(f"  [dry-run] {source_key} job {job_id}: {fields['title']}")
        else:
            db.upsert_job(conn, source_key, job_id, fields)
        written += 1
    return len(postings), written


_ATS_HANDLERS = {
    "greenhouse": _ingest_greenhouse,
    "lever": _ingest_lever,
    "ashby": _ingest_ashby,
}


# ---- Entry point ------------------------------------------------------------

def run(db_path: str, dry_run: bool = False, min_priority: int = 1,
        fetch_fn=None) -> dict:
    """Main ingestion run. Returns summary dict.

    fetch_fn: injectable for tests — replaces the module-level _fetch.
    min_priority: only process sources at or above this priority level.
    """
    global _fetch
    if fetch_fn is not None:
        _orig = _fetch
        _fetch = fetch_fn

    try:
        conn = None if dry_run else db.connect(db_path, check_same_thread=False)

        if not dry_run:
            seeded = db.seed_job_sources(conn, SOURCES_PATH)
            if seeded:
                log.info("seeded %d job sources from %s", seeded, SOURCES_PATH)

            sources = [s for s in db.list_job_sources(conn, active_only=True)
                       if s["priority"] >= min_priority]
        else:
            # dry-run: load directly from JSON (no DB write)
            try:
                raw = json.loads(open(SOURCES_PATH).read())
            except Exception as exc:
                log.error("could not load job_sources.json: %s", exc)
                return {"ok": False, "error": str(exc), "dry_run": True}
            sources = []
            for category, entries in raw.items():
                if category.startswith("_") or not isinstance(entries, list):
                    continue
                for entry in entries:
                    if (isinstance(entry, dict)
                            and entry.get("active", True)
                            and int(entry.get("priority", 5)) >= min_priority):
                        sources.append({
                            "company": entry.get("company", ""),
                            "ats": entry.get("ats", "greenhouse"),
                            "token": entry["token"],
                            "priority": int(entry.get("priority", 5)),
                        })

        total_fetched = total_written = 0
        errors = []

        for source in sources:
            ats = source.get("ats", "greenhouse")
            handler = _ATS_HANDLERS.get(ats)
            if handler is None:
                log.debug("skipping %s/%s — ATS %r not yet supported",
                          ats, source.get("token"), ats)
                continue
            try:
                f, w = handler(source, conn, dry_run)
                total_fetched += f
                total_written += w
                log.info("%s/%s — %d fetched, %d written",
                         ats, source.get("token"), f, w)
            except Exception as exc:
                label = f"{ats}/{source.get('token')}"
                log.exception("%s failed: %s", label, exc)
                errors.append(f"{label}: {exc}")
            time.sleep(RATE_SLEEP)

        summary = {
            "ok": len(errors) == 0,
            "fetched": total_fetched,
            "written": total_written,
            "sources_processed": len(sources),
            "errors": errors,
            "dry_run": dry_run,
        }

        if not dry_run and conn:
            db.log_event(conn, "JobIngestionRun", summary)

        log.info("ingestion complete — sources=%d fetched=%d written=%d errors=%d",
                 len(sources), total_fetched, total_written, len(errors))

    finally:
        if fetch_fn is not None:
            _fetch = _orig  # restore

    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Emploi job ingestion worker")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be written; touch nothing")
    parser.add_argument("--db", default=os.getenv("EMPLOI_DB_PATH", "emploi.sqlite3"),
                        help="Path to SQLite database")
    parser.add_argument("--min-priority", type=int, default=1,
                        help="Only run sources with priority >= this (default: 1 = all)")
    args = parser.parse_args()

    result = run(args.db, dry_run=args.dry_run, min_priority=args.min_priority)
    sys.exit(0 if result["ok"] else 1)
