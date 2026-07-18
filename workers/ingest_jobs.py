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
WORKABLE_BASE = "https://apply.workable.com/api/v3/accounts/{subdomain}/jobs?limit=100"
SMARTRECRUITERS_BASE = "https://api.smartrecruiters.com/v1/companies/{identifier}/postings?limit=100"
# Aggregators (keyed, env-gated). Unlike the per-company ATS boards, these are
# a single API queried by keywords/location — one source row = one saved query.
JOOBLE_BASE = "https://jooble.org/api/{apikey}"
ADZUNA_BASE = ("https://api.adzuna.com/v1/api/jobs/{country}/search/1"
               "?app_id={app_id}&app_key={app_key}&results_per_page=50"
               "&content-type=application/json&what={what}")
MANUAL_JOBS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "manual_jobs")
# Curated listings older than this are treated as expired and skipped —
# a stale manual file that hasn't been touched in a month shouldn't keep
# feeding stale roles into matches.
MANUAL_JOB_MAX_AGE_DAYS = 30
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


def _post_json(url: str, payload: dict):
    """POST JSON, return parsed JSON or None. Separate seam from _fetch (GET)
    for the Jooble aggregator; tests patch this directly, same pattern as
    _fetch. Kept tiny and stdlib-only."""
    try:
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={"Content-Type": "application/json",
                     "User-Agent": "Emploi-job-sourcer/1.0 (hello@emploihq.com)"})
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as r:
            return json.loads(r.read().decode())
    except Exception as exc:
        log.warning("post failed %s — %s", url, exc)
        return None


def _stable_id(*parts: str) -> str:
    h = hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()
    return h[:16]


# Company suffixes that never belong in a domain slug (Inc, Ltd, GmbH, etc.)
_COMPANY_STOPWORDS = {
    "inc", "inc.", "llc", "ltd", "ltd.", "limited", "corp", "corp.",
    "corporation", "co", "co.", "gmbh", "sa", "ag", "plc", "srl",
    "bv", "nv", "kk", "kg", "sarl", "s.a.", "s.l.", "s.r.l.",
    "group", "holdings", "the",
}


def _derive_company_domain(company_name: str) -> Optional[str]:
    """Best-effort guess at the employer's public web domain from a company name.

    Rationale: apply URLs for ATS-hosted jobs point at greenhouse.io / lever.co /
    ashbyhq.com / apply.workable.com / jobs.smartrecruiters.com — extracting
    the domain from apply_url attributes the trust score to the ATS, not the
    employer. Fixing this by storing a guessed employer domain at ingest lets
    verify_employers correctly probe the real company's DNS/MX/site.

    Heuristic (deliberately simple + honest):
      - lowercase
      - drop parenthetical clarifiers ("Loom (Atlassian)" → "loom")
      - split on whitespace/punctuation, drop stopwords ("Inc", "Ltd", ...)
      - join remaining tokens with no separator
      - append ".com"

    Returns None (not a guess) when: name is empty; the result would be too
    short (<3 chars) to be a plausible domain; every token is a stopword.
    A None result tells verify_employers to fall back to its existing logic.
    False positives (e.g. a `nomba.com` that isn't Nomba's) are handled at
    the verify layer — a domain that fails DNS produces "unverified", never
    a fabricated score. See verify.compute_trust.
    """
    if not company_name:
        return None
    name = company_name.strip().lower()
    # Drop parenthetical clarifiers like "Loom (Atlassian)" — keep only the
    # first head phrase, which is almost always the primary brand.
    name = re.sub(r"\([^)]*\)", "", name).strip()
    # Split on any non-alphanumeric — keeps letters/digits, drops &, -, ., etc.
    tokens = [t for t in re.split(r"[^a-z0-9]+", name) if t]
    tokens = [t for t in tokens if t not in _COMPANY_STOPWORDS]
    if not tokens:
        return None
    slug = "".join(tokens)
    if len(slug) < 3:
        return None
    return f"{slug}.com"


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


# ---- Per-ATS normalization (shared) ------------------------------------------
# One normalizer per ATS turning ONE raw job/posting object into the
# db.upsert_job fields dict. Used by both the ingest loops below AND
# core.extract_job_from_url (employer paste-a-URL role extraction) — the
# spec's "do not duplicate" rule for ATS normalization lives here.

def normalize_greenhouse_job(job: dict, company_name: str) -> dict:
    location = (job.get("location") or {}).get("name", "")
    dept = ""
    if job.get("departments"):
        dept = job["departments"][0].get("name", "")
    return {
        "title": job.get("title", ""),
        "company_name": company_name,
        "description": _strip_html(job.get("content", "")),
        "location": location,
        "is_remote": _is_remote(location) or _is_remote(job.get("content", "")),
        "salary_text": _salary_from_greenhouse(job),
        "apply_url": job.get("absolute_url", ""),
        "category": dept,
        "company_domain": _derive_company_domain(company_name),
    }


def normalize_lever_posting(posting: dict, company_name: str) -> dict:
    cats = posting.get("categories") or {}
    location = cats.get("location", "")
    team = cats.get("team", "") or cats.get("department", "")
    workplace = posting.get("workplaceType", "")
    description = _strip_html(posting.get("descriptionPlain", "")
                              or posting.get("description", ""))
    return {
        "title": posting.get("text", ""),
        "company_name": company_name,
        "description": description,
        "location": location,
        "is_remote": (workplace.lower() == "remote"
                      or _is_remote(location)
                      or _is_remote(description)),
        "salary_text": None,
        "apply_url": posting.get("hostedUrl", ""),
        "category": team,
        "company_domain": _derive_company_domain(company_name),
    }


def normalize_ashby_posting(posting: dict, company_name: str) -> dict:
    location = str(posting.get("location") or posting.get("locationName") or "")
    description = _strip_html(str(posting.get("descriptionHtml")
                                  or posting.get("descriptionPlain")
                                  or posting.get("description") or ""))
    return {"title": posting.get("title", ""),
            "company_name": company_name,
            "description": description, "location": location,
            "is_remote": _is_remote(location) or _is_remote(description),
            "salary_text": None,
            "apply_url": posting.get("jobUrl") or posting.get("applyUrl") or "",
            "category": posting.get("department") or posting.get("team") or "",
            "company_domain": _derive_company_domain(company_name)}


def normalize_workable_job(job: dict, company_name: str) -> Optional[dict]:
    """Returns None for non-published jobs (missing state = published)."""
    state = job.get("state")
    if state and str(state).lower() != "published":
        return None
    loc = job.get("location") if isinstance(job.get("location"), dict) else {}
    location_str = str(
        loc.get("location_str")
        or ", ".join(x for x in [loc.get("city"), loc.get("region"),
                                 loc.get("country")] if x)
        or "")
    workplace = str(loc.get("workplace_type") or "")
    remote = (workplace.lower() == "remote"
              or bool(loc.get("telecommuting"))
              or _is_remote(location_str))
    apply_url = (job.get("application_url")
                 or job.get("url")
                 or job.get("shortlink") or "")
    return {
        "title": job.get("title", ""),
        "company_name": company_name,
        "description": _strip_html(str(job.get("description")
                                       or job.get("title") or "")),
        "location": location_str,
        "is_remote": remote,
        "salary_text": None,
        "apply_url": apply_url,
        "category": job.get("department") or "",
        "company_domain": _derive_company_domain(company_name),
    }


def normalize_smartrecruiters_posting(posting: dict, company_name: str) -> dict:
    loc = posting.get("location") if isinstance(posting.get("location"), dict) else {}
    location_str = str(
        loc.get("fullLocation")
        or ", ".join(x for x in [loc.get("city"), loc.get("region"),
                                 loc.get("country")] if x)
        or "")
    remote_flag = bool(loc.get("remote"))
    dept = ""
    dept_obj = posting.get("department")
    if isinstance(dept_obj, dict):
        dept = dept_obj.get("label", "") or ""
    apply_url = posting.get("postingUrl") or posting.get("applyUrl") or ""
    description_text = ""
    job_ad = posting.get("jobAd")
    if isinstance(job_ad, dict):
        sections = job_ad.get("sections")
        if isinstance(sections, dict):
            desc = sections.get("jobDescription")
            if isinstance(desc, dict):
                description_text = desc.get("text", "") or ""
    return {
        "title": posting.get("name", ""),
        "company_name": company_name,
        "description": _strip_html(description_text
                                   or posting.get("name", "")),
        "location": location_str,
        "is_remote": remote_flag or _is_remote(location_str),
        "salary_text": None,
        "apply_url": apply_url,
        "category": dept,
        "company_domain": _derive_company_domain(company_name),
    }


def normalize_jooble_job(job: dict) -> dict:
    """Jooble aggregator result. Company/domain come from the posting itself
    (it's cross-company), so company can be blank — downstream tolerates it."""
    company = str(job.get("company") or "").strip()
    location = str(job.get("location") or "")
    description = _strip_html(str(job.get("snippet") or ""))
    return {
        "title": str(job.get("title") or ""),
        "company_name": company,
        "description": description,
        "location": location,
        "is_remote": _is_remote(location) or _is_remote(description)
                     or _is_remote(str(job.get("title") or "")),
        "salary_text": (str(job.get("salary")).strip() or None) if job.get("salary") else None,
        "apply_url": str(job.get("link") or ""),
        "category": str(job.get("type") or ""),
        # Aggregator rows have no reliable employer domain — leave it unset so
        # verify_employers doesn't probe a guess derived from a noisy name.
        "company_domain": _derive_company_domain(company) if company else None,
    }


def normalize_adzuna_job(job: dict) -> dict:
    company = str((job.get("company") or {}).get("display_name") or "").strip()
    location = str((job.get("location") or {}).get("display_name") or "")
    description = _strip_html(str(job.get("description") or ""))
    smin, smax = job.get("salary_min"), job.get("salary_max")
    salary = None
    if smin or smax:
        salary = (f"{int(smin):,}–{int(smax):,}" if smin and smax
                  else f"{int(smin or smax):,}")
    return {
        "title": str(job.get("title") or ""),
        "company_name": company,
        "description": description,
        "location": location,
        "is_remote": _is_remote(location) or _is_remote(description)
                     or _is_remote(str(job.get("title") or "")),
        "salary_text": salary,
        "apply_url": str(job.get("redirect_url") or ""),
        "category": str((job.get("category") or {}).get("label") or ""),
        "company_domain": _derive_company_domain(company) if company else None,
    }


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
        company_name = source.get("company", token.replace("-", " ").title())
        fields = normalize_greenhouse_job(job, company_name)

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
        company_name = source.get("company", slug.replace("-", " ").title())
        fields = normalize_lever_posting(posting, company_name)

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
        company_name = source.get("company", token.replace("-", " ").title())
        fields = normalize_ashby_posting(posting, company_name)
        source_key = f"ashby/{token}"
        if dry_run:
            print(f"  [dry-run] {source_key} job {job_id}: {fields['title']}")
        else:
            db.upsert_job(conn, source_key, job_id, fields)
        written += 1
    return len(postings), written


def _ingest_workable(source: dict, conn, dry_run: bool):
    """Fetch published jobs from one Workable subdomain. The list endpoint
    returns titles/locations/URLs but not full descriptions (Workable exposes
    those on the per-job detail endpoint, which would multiply HTTP calls per
    company). v1 stores the title as a description stub — matching still ranks
    by title/skills; users who want a tailored draft can Import-a-Job to paste
    the full JD. Supports both {"results": [...]} and bare-list responses."""
    subdomain = source["token"]
    data = _fetch(WORKABLE_BASE.format(subdomain=subdomain))
    if data is None:
        return 0, 0
    jobs = data.get("results") if isinstance(data, dict) else data
    if not isinstance(jobs, list):
        return 0, 0
    written = 0
    for job in jobs:
        if not isinstance(job, dict):
            continue
        # Only ingest published jobs; a missing state field is treated as published
        # (some tenants omit the field entirely) — a state that IS present must be "published".
        company_name = source.get("company",
                                   subdomain.replace("-", " ").title())
        fields = normalize_workable_job(job, company_name)
        if fields is None:
            continue
        shortcode = job.get("shortcode") or job.get("id") or ""
        job_id = str(job.get("id") or shortcode
                     or _stable_id(subdomain, job.get("title", "")))
        source_key = f"workable/{subdomain}"
        if dry_run:
            print(f"  [dry-run] {source_key} job {job_id}: {fields['title']}")
        else:
            db.upsert_job(conn, source_key, job_id, fields)
        written += 1
    return len(jobs), written


def _ingest_smartrecruiters(source: dict, conn, dry_run: bool):
    """Fetch public postings for one SmartRecruiters company identifier.
    The postings list carries the posting name, location, and department but
    only a short `jobAd.sections.jobDescription.text` blurb (the full JD sits
    on a per-posting detail endpoint) — v1 stores whatever blurb is present,
    falling back to the title so matching always has something non-empty."""
    identifier = source["token"]
    data = _fetch(SMARTRECRUITERS_BASE.format(identifier=identifier))
    if data is None:
        return 0, 0
    postings = data.get("content") if isinstance(data, dict) else data
    if not isinstance(postings, list):
        return 0, 0
    written = 0
    for posting in postings:
        if not isinstance(posting, dict):
            continue
        posting_id = str(posting.get("id") or posting.get("uuid")
                         or _stable_id(identifier, posting.get("name", "")))
        company_name = source.get("company",
                                   identifier.replace("-", " ").title())
        fields = normalize_smartrecruiters_posting(posting, company_name)
        source_key = f"smartrecruiters/{identifier}"
        if dry_run:
            print(f"  [dry-run] {source_key} job {posting_id}: {fields['title']}")
        else:
            db.upsert_job(conn, source_key, posting_id, fields)
        written += 1
    return len(postings), written


def _ingest_manual(source: dict, conn, dry_run: bool):
    """Curated jobs from a human-maintained JSON file at
    `data/manual_jobs/{token}.json`. This is the honest answer for Nigerian
    banks / Workday shops / any employer without a public ATS feed —
    scraping was rejected as legal/reliability risk, aggregators like Jooble
    are weak on NG coverage, and a human maintaining 5-15 open roles per
    company for a top-20 curated set is realistic (~30 min/week).

    File shape:
        [{"job_id": "req-123", "title": "...", "description": "...",
          "location": "Lagos, Nigeria", "is_remote": false,
          "apply_url": "https://gtco.com/careers/...",
          "salary_text": null, "category": "Risk",
          "posted_at": "2026-07-01"}, ...]

    Jobs with a `posted_at` older than MANUAL_JOB_MAX_AGE_DAYS are silently
    skipped — a stale file that hasn't been refreshed shouldn't keep feeding
    30-day-old roles into matches. Missing `posted_at` is tolerated (treated
    as fresh); the diagnostics endpoint separately warns about file mtime.
    Malformed entries are skipped with a warning; a single bad row never
    kills the whole company's ingest.
    """
    import json as _json
    from datetime import datetime, timedelta

    token = source["token"]
    file_path = os.path.join(MANUAL_JOBS_DIR, f"{token}.json")
    if not os.path.exists(file_path):
        log.info("manual/%s — file not found at %s", token, file_path)
        return 0, 0

    try:
        payload = _json.loads(open(file_path, encoding="utf-8").read())
    except Exception as exc:
        log.warning("manual/%s — could not parse JSON: %s", token, exc)
        return 0, 0

    if not isinstance(payload, list):
        log.warning("manual/%s — expected a list at top level, got %s",
                    token, type(payload).__name__)
        return 0, 0

    cutoff = datetime.utcnow() - timedelta(days=MANUAL_JOB_MAX_AGE_DAYS)
    written = 0
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        posted = entry.get("posted_at")
        if posted:
            try:
                # Accept either date or datetime ISO strings.
                dt = datetime.fromisoformat(str(posted)[:19])
                if dt < cutoff:
                    continue
            except Exception:
                # Bad date format doesn't force a skip — better to include
                # than to hide it; curator will notice on next update.
                pass

        job_id = str(entry.get("job_id") or entry.get("id")
                     or _stable_id(token, entry.get("title", ""),
                                    entry.get("apply_url", "")))
        company_name = source.get("company",
                                   token.replace("-", " ").title())
        location = str(entry.get("location") or "")
        description = _strip_html(str(entry.get("description") or ""))
        fields = {
            "title": entry.get("title", "") or "",
            "company_name": company_name,
            "description": description,
            "location": location,
            "is_remote": bool(entry.get("is_remote")) or _is_remote(location)
                         or _is_remote(description),
            "salary_text": entry.get("salary_text"),
            "apply_url": entry.get("apply_url", "") or "",
            "category": entry.get("category", "") or "",
            "company_domain": _derive_company_domain(company_name),
        }
        source_key = f"manual/{token}"
        if dry_run:
            print(f"  [dry-run] {source_key} job {job_id}: {fields['title']}")
        else:
            db.upsert_job(conn, source_key, job_id, fields)
        written += 1
    return len(payload), written


def _ingest_jooble(source: dict, conn, dry_run: bool):
    """Jooble aggregator. One source row = one saved query (source['token'],
    optionally 'cc:query' where cc is the location). Env-gated on JOOBLE_API_KEY;
    without the key the source no-ops so an unconfigured deploy stays quiet."""
    api_key = os.getenv("JOOBLE_API_KEY", "").strip()
    if not api_key:
        log.info("jooble skipped — JOOBLE_API_KEY unset")
        return 0, 0
    token = str(source["token"])
    location, _, keywords = token.partition(":") if ":" in token else ("", "", token)
    payload = {"keywords": keywords.strip() or token}
    if location.strip():
        payload["location"] = location.strip()
    data = _post_json(JOOBLE_BASE.format(apikey=api_key), payload)
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        return 0, 0
    written = 0
    for job in jobs:
        if not isinstance(job, dict):
            continue
        job_id = str(job.get("id") or _stable_id("jooble", str(job.get("link", "")),
                                                 job.get("title", "")))
        fields = normalize_jooble_job(job)
        if not (fields.get("title") or "").strip():
            continue
        source_key = f"jooble/{token}"
        if dry_run:
            print(f"  [dry-run] {source_key} job {job_id}: {fields['title']}")
        else:
            db.upsert_job(conn, source_key, job_id, fields)
        written += 1
    return len(jobs), written


def _ingest_adzuna(source: dict, conn, dry_run: bool):
    """Adzuna aggregator. source['token'] = 'country:keywords' (e.g.
    'za:solar engineer'); country defaults to ADZUNA_COUNTRY or 'gb'. Env-gated
    on ADZUNA_APP_ID + ADZUNA_APP_KEY."""
    from urllib.parse import quote
    app_id = os.getenv("ADZUNA_APP_ID", "").strip()
    app_key = os.getenv("ADZUNA_APP_KEY", "").strip()
    if not (app_id and app_key):
        log.info("adzuna skipped — ADZUNA_APP_ID/ADZUNA_APP_KEY unset")
        return 0, 0
    token = str(source["token"])
    country, _, keywords = token.partition(":") if ":" in token else ("", "", token)
    country = (country.strip() or os.getenv("ADZUNA_COUNTRY", "gb")).lower()
    url = ADZUNA_BASE.format(country=country, app_id=app_id, app_key=app_key,
                             what=quote(keywords.strip() or token))
    data = _fetch(url)
    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list):
        return 0, 0
    written = 0
    for job in results:
        if not isinstance(job, dict):
            continue
        job_id = str(job.get("id") or _stable_id("adzuna", str(job.get("redirect_url", "")),
                                                 job.get("title", "")))
        fields = normalize_adzuna_job(job)
        if not (fields.get("title") or "").strip():
            continue
        source_key = f"adzuna/{token}"
        if dry_run:
            print(f"  [dry-run] {source_key} job {job_id}: {fields['title']}")
        else:
            db.upsert_job(conn, source_key, job_id, fields)
        written += 1
    return len(results), written


_ATS_HANDLERS = {
    "greenhouse": _ingest_greenhouse,
    "lever": _ingest_lever,
    "ashby": _ingest_ashby,
    "workable": _ingest_workable,
    "smartrecruiters": _ingest_smartrecruiters,
    "jooble": _ingest_jooble,
    "adzuna": _ingest_adzuna,
    "manual": _ingest_manual,
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
