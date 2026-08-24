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
# jobdataapi.com — structured global feed with a REAL ISO country filter
# (country_code=NG), so unlike the other aggregators it tags Nigeria at the
# source instead of relying on our string inference. DRF-style key in the
# Authorization header ("Api-Key <key>"). Env-gated on JOBDATAAPI_API_KEY.
JOBDATAAPI_BASE = "https://jobdataapi.com/api/jobs/"
# Techmap (jobdatafeeds.com) "Jobs In Nigeria" feed — a Nigeria-localised
# dataset. Header-keyed GET. The exact field names below are coded defensively
# against Techmap's documented job-posting shape and confirmed against a live
# sample when a key is provisioned; until then its seed rows ship inactive.
# Env-gated on TECHMAP_API_KEY; endpoint host is overridable for the RapidAPI
# vs direct-api split without a code change.
TECHMAP_BASE = os.getenv("TECHMAP_BASE", "https://api.techmap.io/v1/jobs")
# Workday. The single biggest coverage gap for the Nigerian market: banks and
# large corporates (the employers this product's users actually name) don't use
# Greenhouse/Lever — they run Workday, SuccessFactors or Taleo. Workday is the
# one with a genuinely PUBLIC, keyless JSON API (the same endpoints its own
# career-site JS calls), so it is implementable honestly; SuccessFactors' RCM
# OData API requires per-tenant credentials, so it stays a `career_page`
# placeholder until a partner supplies keys.
#   list  : POST .../wday/cxs/{tenant}/{site}/jobs   {limit, offset, searchText}
#   detail: GET  .../wday/cxs/{tenant}/{site}{externalPath}  -> jobPostingInfo
#   apply : https://{tenant}.{wd}.myworkdayjobs.com/en-US/{site}{externalPath}
WORKDAY_HOST = "https://{tenant}.{wd}.myworkdayjobs.com"
WORKDAY_LIST = WORKDAY_HOST + "/wday/cxs/{tenant}/{site}/jobs"
WORKDAY_DETAIL = WORKDAY_HOST + "/wday/cxs/{tenant}/{site}{path}"
WORKDAY_APPLY = WORKDAY_HOST + "/en-US/{site}{path}"
# Workday caps a page at 20; bound total work per source so one huge tenant
# can't stall a run (the detail fetch below is one request per posting).
WORKDAY_PAGE_LIMIT = 20
WORKDAY_MAX_JOBS = 100
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


def _get_json_auth(url: str, headers: dict):
    """GET url with custom (auth) headers, return parsed JSON or None.

    Separate seam from _fetch (which sends only a User-Agent) for header-keyed
    aggregators — jobdataapi.com and Techmap authenticate with an Authorization
    / x-api-key header, not a query-string key. Tests patch this directly, the
    same pattern the docstring on _post_json describes for Jooble. Kept tiny and
    stdlib-only; never raises (a bad key / down endpoint becomes a logged None
    so the source no-ops instead of failing the whole run)."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Emploi-job-sourcer/1.0 (hello@emploihq.com)",
                     **(headers or {})})
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as r:
            return json.loads(r.read().decode())
    except Exception as exc:
        log.warning("get(auth) failed %s — %s", url, exc)
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


# ---- Country inference ------------------------------------------------------
# Why: the source pool is global (90 of 151 seeded sources are global boards),
# so a Nigerian job seeker browsing "all jobs" mostly sees US on-site roles they
# can't take. Storing an ISO-3166 alpha-2 country at ingest lets the pool be
# filtered "Nigeria + remote" WITHOUT discarding remote-global roles, which are
# genuinely valuable to a remote seeker in Africa. Inference is deliberately
# conservative: an unrecognised location stores NULL ("unknown"), never a guess,
# and NULL is treated as "don't filter it out" downstream — we never hide a job
# because our parser didn't recognise a place name.

# Nigeria first and separately: precision here matters most (this is the home
# market). Districts of Lagos appear as bare locations on local boards.
_NG_PLACES = (
    "nigeria", "lagos", "abuja", "ibadan", "kano", "port harcourt", "portharcourt",
    "benin city", "enugu", "kaduna", "abeokuta", "ilorin", "jos", "calabar",
    "uyo", "owerri", "warri", "onitsha", "aba", "akure", "maiduguri", "zaria",
    "victoria island", "lekki", "ikeja", "yaba", "ikoyi", "surulere", "ajah",
    "asaba", "awka", "minna", "sokoto", "bauchi", "makurdi", "lokoja",
    "osogbo", "ado ekiti", "umuahia", "yenagoa", "gombe", "katsina", "abia",
)

# Other countries, matched on whole words. Order matters only for aliases that
# contain each other; the regex uses word boundaries so "India" never matches
# "Indiana". Kept to markets that actually show up in the seeded sources.
_COUNTRY_MARKERS = (
    ("KE", ("kenya", "nairobi", "mombasa")),
    ("GH", ("ghana", "accra", "kumasi")),
    ("ZA", ("south africa", "johannesburg", "cape town", "pretoria", "durban")),
    ("EG", ("egypt", "cairo")),
    ("RW", ("rwanda", "kigali")),
    ("UG", ("uganda", "kampala")),
    ("TZ", ("tanzania", "dar es salaam")),
    ("ET", ("ethiopia", "addis ababa")),
    ("SN", ("senegal", "dakar")),
    ("CI", ("ivory coast", "côte d'ivoire", "cote d'ivoire", "abidjan")),
    ("MA", ("morocco", "casablanca")),
    ("GB", ("united kingdom", "england", "scotland", "wales", "london",
            "manchester", "edinburgh", "u.k.", "uk")),
    ("IE", ("ireland", "dublin")),
    ("CA", ("canada", "toronto", "vancouver", "montreal", "ottawa", "calgary")),
    ("DE", ("germany", "deutschland", "berlin", "munich", "hamburg")),
    ("FR", ("france", "paris")),
    ("NL", ("netherlands", "amsterdam")),
    ("ES", ("spain", "madrid", "barcelona")),
    ("PT", ("portugal", "lisbon")),
    ("PL", ("poland", "warsaw", "krakow")),
    ("IN", ("india", "bangalore", "bengaluru", "mumbai", "delhi", "hyderabad")),
    ("SG", ("singapore",)),
    ("AE", ("united arab emirates", "dubai", "abu dhabi")),
    ("AU", ("australia", "sydney", "melbourne")),
    ("BR", ("brazil", "brasil", "sao paulo", "são paulo")),
    ("MX", ("mexico", "méxico")),
    ("US", ("united states", "usa", "u.s.a.", "u.s.", "america",
            "new york", "san francisco", "los angeles", "seattle", "austin",
            "boston", "chicago", "denver", "atlanta", "washington dc",
            "silicon valley", "bay area")),
)

# Trailing US state codes ("San Francisco, CA"). Only consulted after the
# explicit country pass, so "Toronto, CA" resolves to Canada (matched by city)
# rather than California.
_US_STATES = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id",
    "il", "in", "ia", "ks", "ky", "la", "ma", "md", "me", "mi", "mn", "ms",
    "mo", "mt", "nc", "nd", "ne", "nh", "nj", "nm", "nv", "ny", "oh", "ok",
    "or", "pa", "ri", "sc", "sd", "tn", "tx", "ut", "va", "vt", "wa", "wi",
    "wv", "wy", "dc",
}


def _mentions(text: str, needle: str) -> bool:
    """Whole-word(ish) containment. Word boundaries stop 'India' matching
    'Indiana' and 'aba' matching 'Abadan'; needles with punctuation (u.s.)
    fall back to plain containment since \\b behaves oddly around dots."""
    if not needle:
        return False
    if any(c in needle for c in ".'’"):
        return needle in text
    return re.search(r"\b%s\b" % re.escape(needle), text) is not None


def _derive_country(location: str) -> Optional[str]:
    """Best-effort ISO-3166 alpha-2 country for a job location string.

    Returns None when nothing is recognised — an honest "unknown" that the
    filters treat as "keep", so a job is never hidden by a parser miss.
    Nigeria is checked first: a listing open to several places including
    Nigeria is Nigeria-relevant, which is the bias this product wants.
    """
    text = (location or "").strip().lower()
    if not text:
        return None
    # "Benin City" is Nigeria; bare "Benin" is a different country. Resolve the
    # city form before any generic matching can see the substring.
    if "benin city" in text:
        return "NG"
    for place in _NG_PLACES:
        if _mentions(text, place):
            return "NG"
    for code, markers in _COUNTRY_MARKERS:
        for marker in markers:
            if _mentions(text, marker):
                return code
    # Trailing US state code, e.g. "Austin, TX" or "Remote - Austin, TX (US)".
    tail = re.split(r"[,/|()\-–]", text)
    for part in reversed(tail):
        token = part.strip()
        if token in _US_STATES:
            return "US"
    return None


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
        "country": _derive_country(location),
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
        "country": _derive_country(location),
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
            "company_domain": _derive_company_domain(company_name),
            "country": _derive_country(location)}


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
        "country": _derive_country(location_str),
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
        "country": _derive_country(location_str),
    }


def _parse_workday_token(token: str):
    """`tenant:site` or `tenant:wdN:site` (host shard defaults to wd3).

    Examples: `mtn:MTN_Careers`, `dangote:wd3:Dangote_External`.
    Returns (tenant, wd, site) or None when the token is malformed — a bad
    token must skip the source, never build a nonsense URL.
    """
    parts = [p.strip() for p in str(token or "").split(":") if p.strip()]
    if len(parts) == 2:
        tenant, site = parts
        wd = "wd3"
    elif len(parts) == 3:
        tenant, wd, site = parts
    else:
        return None
    wd = wd.lower()
    if not re.fullmatch(r"wd\d+", wd):
        return None
    # Tenant/site land in a URL — keep them to the charset Workday actually
    # uses so a hostile source row can't inject a different host or path.
    if not re.fullmatch(r"[A-Za-z0-9_-]+", tenant):
        return None
    if not re.fullmatch(r"[A-Za-z0-9_-]+", site):
        return None
    return tenant, wd, site


def normalize_workday_posting(posting: dict, company_name: str, tenant: str,
                              wd: str, site: str, description: str = "") -> dict:
    """One Workday jobPostings entry -> the upsert_job fields dict.

    The list response carries no description (Workday returns it only from the
    per-job detail endpoint), so `description` is passed in by the caller and
    falls back to the title + location rather than an empty string — an empty
    description would make the job unscoreable by the match rubric.
    """
    title = str(posting.get("title") or "").strip()
    location = str(posting.get("locationsText") or "").strip()
    path = str(posting.get("externalPath") or "")
    apply_url = (WORKDAY_APPLY.format(tenant=tenant, wd=wd, site=site, path=path)
                 if path else "")
    body = _strip_html(description) if description else ""
    if not body:
        body = " — ".join(x for x in (title, location) if x)
    return {
        "title": title,
        "company_name": company_name,
        "description": body,
        "location": location,
        "is_remote": _is_remote(location) or _is_remote(body),
        "salary_text": None,
        "apply_url": apply_url,
        "category": None,
        "company_domain": _derive_company_domain(company_name),
        "country": _derive_country(location),
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
        "country": _derive_country(location),
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
        "country": _derive_country(location),
    }


def normalize_jobdataapi_job(job: dict) -> dict:
    """jobdataapi.com job object -> upsert_job fields.

    Richer than the other aggregators: `company` is a nested object and the
    feed carries its OWN ISO country code. We TRUST that code over string
    inference when present (it's the source of truth for this feed's whole
    value proposition — server-side country filtering), and fall back to
    _derive_country only when the field is missing. Every access is defensive:
    a shape surprise drops one field, never raises."""
    company_obj = job.get("company") if isinstance(job.get("company"), dict) else {}
    company = str(company_obj.get("name") or "").strip()
    location = str(job.get("location") or "")
    description = _strip_html(str(job.get("description") or ""))
    # The feed's own country code beats string inference; fall back when absent.
    country_obj = job.get("country") if isinstance(job.get("country"), dict) else {}
    country = str(country_obj.get("code") or "").strip().upper()[:2] or None
    if not country:
        country = _derive_country(location)
    smin, smax = job.get("salary_min"), job.get("salary_max")
    salary = None
    try:
        if smin or smax:
            salary = (f"{int(smin):,}–{int(smax):,}" if smin and smax
                      else f"{int(smin or smax):,}")
    except (TypeError, ValueError):
        salary = None  # non-numeric salary -> omit rather than crash
    return {
        "title": str(job.get("title") or ""),
        "company_name": company,
        "description": description,
        "location": location,
        # The feed exposes an explicit remote flag; OR it with text detection.
        "is_remote": bool(job.get("has_remote")) or _is_remote(location)
                     or _is_remote(description) or _is_remote(str(job.get("title") or "")),
        "salary_text": salary,
        "apply_url": str(job.get("application_url") or job.get("apply_url")
                         or job.get("url") or ""),
        "category": "",  # feed has employment `types`, not a job category
        "company_domain": _derive_company_domain(company) if company else None,
        "country": country,
    }


def normalize_techmap_job(job: dict) -> dict:
    """Techmap "Jobs In Nigeria" posting -> upsert_job fields.

    Techmap posts are flat documents; location may arrive as a single string or
    split across locality/region/country. We reuse _derive_country on whichever
    country/location text is present (so "Nigeria" -> NG through the existing
    place tables), and read title/description/url from either of the field
    names Techmap's data dictionary uses. Provisional until confirmed against a
    live sample — hence purely defensive `.get` access."""
    company = str(job.get("company") or job.get("orgName") or "").strip()
    # Location: prefer an explicit combined string, else assemble parts.
    location = str(job.get("location") or "").strip()
    if not location:
        parts = [str(job.get(k) or "").strip()
                 for k in ("locality", "region", "country")]
        location = ", ".join(p for p in parts if p)
    description = _strip_html(str(job.get("text") or job.get("description") or ""))
    title = str(job.get("name") or job.get("title") or "")
    # Country: the feed's country field first (full name or code both resolve
    # through _derive_country), then the assembled location as a fallback.
    country = _derive_country(str(job.get("country") or "")) or _derive_country(location)
    salary = str(job.get("salary") or "").strip() or None
    return {
        "title": title,
        "company_name": company,
        "description": description,
        "location": location,
        "is_remote": _is_remote(location) or _is_remote(description)
                     or _is_remote(title),
        "salary_text": salary,
        "apply_url": str(job.get("url") or job.get("link") or ""),
        "category": str(job.get("category") or ""),
        "company_domain": _derive_company_domain(company) if company else None,
        "country": country,
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


def _ingest_workday(source: dict, conn, dry_run: bool):
    """Fetch postings from one public Workday career site. Returns
    (fetched, written).

    Paginates the POST list endpoint (20/page, capped at WORKDAY_MAX_JOBS) and
    then fetches each posting's detail for the real description. Every step
    degrades instead of raising: a bad token skips the source, a failed page
    stops pagination with what we already have, and a failed detail fetch falls
    back to the title/location summary so the job is still ingested.
    """
    parsed = _parse_workday_token(source.get("token"))
    if not parsed:
        log.warning("workday: malformed token %r — skipping", source.get("token"))
        return 0, 0
    tenant, wd, site = parsed
    company_name = source.get("company") or tenant.replace("-", " ").title()
    list_url = WORKDAY_LIST.format(tenant=tenant, wd=wd, site=site)

    postings, offset = [], 0
    while len(postings) < WORKDAY_MAX_JOBS:
        data = _post_json(list_url, {"appliedFacets": {}, "searchText": "",
                                     "limit": WORKDAY_PAGE_LIMIT, "offset": offset})
        page = data.get("jobPostings") if isinstance(data, dict) else None
        if not isinstance(page, list) or not page:
            break
        postings.extend(p for p in page if isinstance(p, dict))
        if len(page) < WORKDAY_PAGE_LIMIT:
            break
        offset += WORKDAY_PAGE_LIMIT
        time.sleep(RATE_SLEEP)
    postings = postings[:WORKDAY_MAX_JOBS]
    if not postings:
        return 0, 0

    written = 0
    for posting in postings:
        path = str(posting.get("externalPath") or "")
        description = ""
        # Skip the per-job detail fetch on a dry run: spot_check_sources calls
        # every handler with dry_run=True purely to see whether a token is
        # alive, and N+1 requests (plus N rate-limit sleeps) per source would
        # turn a liveness probe into a crawl.
        if path and not dry_run:
            detail = _fetch(WORKDAY_DETAIL.format(tenant=tenant, wd=wd, site=site,
                                                  path=path))
            info = detail.get("jobPostingInfo") if isinstance(detail, dict) else None
            if isinstance(info, dict):
                description = str(info.get("jobDescription") or "")
            time.sleep(RATE_SLEEP)
        fields = normalize_workday_posting(posting, company_name, tenant, wd,
                                           site, description)
        if not fields["title"]:
            continue
        # bulletFields usually carries the requisition id; fall back to the
        # path so the dedup key is stable across runs either way.
        bullets = posting.get("bulletFields")
        req_id = (str(bullets[0]) if isinstance(bullets, list) and bullets
                  else (path or _stable_id(tenant, site, fields["title"])))
        source_key = f"workday/{tenant}:{site}"
        if dry_run:
            print(f"  [dry-run] {source_key} job {req_id}: {fields['title']}")
        else:
            db.upsert_job(conn, source_key, req_id, fields)
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
            "country": _derive_country(location),
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


def _ingest_jobdataapi(source: dict, conn, dry_run: bool):
    """jobdataapi.com aggregator. source['token'] = 'CC' or 'CC:keywords'
    (ISO country + optional title search), e.g. 'NG' or 'NG:developer'.
    Env-gated on JOBDATAAPI_API_KEY; without the key the source no-ops so an
    unconfigured deploy stays quiet (same posture as Jooble/Adzuna)."""
    from urllib.parse import urlencode
    api_key = os.getenv("JOBDATAAPI_API_KEY", "").strip()
    if not api_key:
        log.info("jobdataapi skipped — JOBDATAAPI_API_KEY unset")
        return 0, 0
    token = str(source["token"])
    country, _, keywords = token.partition(":") if ":" in token else (token, "", "")
    params = {"country_code": (country.strip() or "NG").upper(),
              "page_size": 50, "max_age": 30}
    if keywords.strip():
        params["title"] = keywords.strip()
    url = JOBDATAAPI_BASE + "?" + urlencode(params)
    data = _get_json_auth(url, {"Authorization": f"Api-Key {api_key}"})
    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list):
        return 0, 0
    written = 0
    for job in results:
        if not isinstance(job, dict):
            continue
        job_id = str(job.get("id") or _stable_id(
            "jobdataapi", str(job.get("application_url", "")), str(job.get("title", ""))))
        fields = normalize_jobdataapi_job(job)
        if not (fields.get("title") or "").strip():
            continue
        source_key = f"jobdataapi/{token}"
        if dry_run:
            print(f"  [dry-run] {source_key} job {job_id}: {fields['title']}")
        else:
            db.upsert_job(conn, source_key, job_id, fields)
        written += 1
    return len(results), written


def _ingest_techmap(source: dict, conn, dry_run: bool):
    """Techmap "Jobs In Nigeria" feed. source['token'] = a country/location
    query (e.g. 'NG' or 'Lagos'). Env-gated on TECHMAP_API_KEY; header-keyed
    GET via the shared _get_json_auth seam. Response shape is read defensively
    (see normalize_techmap_job) — a paginated {results:[...]} or a bare list
    are both accepted so a documented-vs-live schema drift can't crash a run."""
    from urllib.parse import urlencode
    api_key = os.getenv("TECHMAP_API_KEY", "").strip()
    if not api_key:
        log.info("techmap skipped — TECHMAP_API_KEY unset")
        return 0, 0
    token = str(source["token"])
    url = TECHMAP_BASE + "?" + urlencode({"countryCode": token.strip() or "NG",
                                          "limit": 50})
    data = _get_json_auth(url, {"x-api-key": api_key})
    if isinstance(data, dict):
        results = data.get("results") or data.get("jobs") or data.get("result")
    else:
        results = data  # some feeds return a bare array
    if not isinstance(results, list):
        return 0, 0
    written = 0
    for job in results:
        if not isinstance(job, dict):
            continue
        job_id = str(job.get("id") or job.get("_id") or _stable_id(
            "techmap", str(job.get("url", "")), str(job.get("name", ""))))
        fields = normalize_techmap_job(job)
        if not (fields.get("title") or "").strip():
            continue
        source_key = f"techmap/{token}"
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
    "workday": _ingest_workday,
    "jooble": _ingest_jooble,
    "adzuna": _ingest_adzuna,
    "jobdataapi": _ingest_jobdataapi,
    "techmap": _ingest_techmap,
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
