"""Emploi API — thin FastAPI layer over core.py / verify.py / db.py.

Invariant: NO business logic here. Every endpoint validates input, dispatches
to the UI-free modules, and shapes the response. Trust scores stay
deterministic (verify.compute_trust); Gemini-backed endpoints return 503 with
a clear message when GEMINI_API_KEY is absent instead of failing weirdly.

Auth model (service-to-service): the Next.js server calls this API with
  X-API-Key:  shared secret (EMPLOI_API_KEY). If the env var is unset the API
              runs in open dev mode and logs a warning.
  X-User-Id:  the authenticated user's stable id (Google `sub`), asserted by
              the web tier after NextAuth session validation. This API is not
              internet-facing for browsers; deploy it private to the web tier.

Run: python3 -m uvicorn api.main:app --port 8000
"""
import json
import os
import secrets
import sys
import logging
from collections import defaultdict
from time import time
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, UploadFile, File, Request, Response
from pydantic import BaseModel, Field

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core  # noqa: E402
import db  # noqa: E402
import verify  # noqa: E402
import workers.ingest_jobs as ingest_worker  # noqa: E402
import workers.match_users as match_worker  # noqa: E402
import workers.verify_employers as verify_worker  # noqa: E402
import workers.notify_users as notify_worker  # noqa: E402
import workers.backup_db as backup_worker  # noqa: E402

log = logging.getLogger("emploi.api")
logging.basicConfig(level=logging.INFO)

API_KEY = os.getenv("EMPLOI_API_KEY", "")
DB_PATH = os.getenv("EMPLOI_DB_PATH", "emploi.sqlite3")

if not API_KEY:
    log.warning("EMPLOI_API_KEY not set — API running in OPEN DEV MODE. "
                "Set it before any deployment.")

# Injectable I/O — tests patch these module attributes; production uses the
# real implementations from verify.py.
dns_fn = verify.dns_resolves
mx_fn = verify.has_mx
fetch_fn = verify.fetch_site

_verify_cache: dict = {}
_rate_counters: dict[str, list[float]] = defaultdict(list)
RATE_LIMITS = {
    "default": (60, 60),
    "/verify": (10, 60),
    "/career-twin/extract": (5, 300),
    "/career-twin/upload": (5, 300),
    "/matches": (30, 60),
    "/applications/generate": (10, 3600),
    "/chat": (20, 60),
}


def get_conn():
    """One connection per process; sqlite serializes writes internally."""
    if not hasattr(get_conn, "_conn"):
        get_conn._conn = db.connect(DB_PATH, check_same_thread=False)
    return get_conn._conn


def get_model():
    """Duck-typed Gemini model, or None when no key is configured."""
    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        return None
    import google.generativeai as genai
    genai.configure(api_key=key)
    return genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))


def require_model():
    model = app.state.model_factory()
    if model is None:
        raise HTTPException(
            status_code=503,
            detail="AI features are unavailable: GEMINI_API_KEY is not "
                   "configured on the API service.")
    return model


def auth(x_api_key: str = Header(default=""),
         x_user_id: str = Header(default="")) -> str:
    if API_KEY and not secrets.compare_digest(x_api_key, API_KEY):
        raise HTTPException(status_code=401, detail="invalid API key")
    if not x_user_id:
        raise HTTPException(status_code=401, detail="missing X-User-Id")
    return x_user_id


def admin_key_auth(x_api_key: str = Header(default="")) -> None:
    """Auth for the /admin/run/* worker-trigger endpoints — API key only, no
    X-User-Id. Render Cron Jobs cannot mount a persistent disk (a Render
    product limitation, not a config mistake), so the nightly/hourly
    workers can't run as their own cron services against the shared
    SQLite file. Instead they run inside this always-on API process (which
    already has the disk mounted) and Render Cron just fires the HTTP
    trigger on schedule. See render.yaml and docs/engineering/05."""
    if not API_KEY:
        raise HTTPException(status_code=503,
                            detail="EMPLOI_API_KEY must be configured before "
                                   "worker-trigger endpoints can run")
    if not secrets.compare_digest(x_api_key, API_KEY):
        raise HTTPException(status_code=401, detail="invalid API key")


def rate_limit(request: Request, user_id: str = Depends(auth)) -> str:
    """Small in-process per-user guard for costly and probe-heavy endpoints.

    The deployment intentionally uses one API process today. Counters reset on
    restart; that limitation is preferable to leaving Gemini and DNS calls
    unlimited until shared rate-limit infrastructure is warranted.
    """
    limit, window = RATE_LIMITS.get(request.url.path, RATE_LIMITS["default"])
    now = time()
    key = f"{user_id}:{request.url.path}"
    calls = [stamp for stamp in _rate_counters[key] if now - stamp < window]
    if len(calls) >= limit:
        raise HTTPException(status_code=429,
                            detail=f"Rate limit: {limit} requests per {window}s")
    calls.append(now)
    _rate_counters[key] = calls
    return user_id


# Upload / payload bounds — the wizard caps uploads at 10 MB client-side; the
# API enforces its own ceiling so a direct caller can't exhaust memory, and
# career-twin blobs stay small enough for the JSON-in-SQLite design.
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_TWIN_BYTES = 64 * 1024


def run_extraction(fn, *args):
    """Call a Gemini-backed core function; a provider failure (rate limit,
    network, safety block) becomes a clean 502 instead of a raw 500."""
    try:
        return fn(*args)
    except Exception:
        log.exception("model call failed in %s", getattr(fn, "__name__", fn))
        raise HTTPException(
            status_code=502,
            detail="The AI service is temporarily unavailable — try again in a moment.")


app = FastAPI(title="Emploi API", version="1.0.0")
app.state.model_factory = get_model


# ---------------- schemas ----------------
class CareerTwinIn(BaseModel):
    data: dict


class ResumeIn(BaseModel):
    cv_text: str = Field(min_length=50, description="Extracted CV text")


class VerifyIn(BaseModel):
    company: str = ""
    contact: str = ""
    job_text: str = ""
    role: str = ""


class ApplicationIn(BaseModel):
    company: str = ""
    role: str = ""
    status: str = "applied"
    extra: dict = Field(default_factory=dict)


class StatusIn(BaseModel):
    status: str

    def validated(self) -> str:
        allowed = {"applied", "interview", "offer", "rejected", "withdrawn"}
        if self.status not in allowed:
            raise HTTPException(status_code=422,
                                detail=f"status must be one of {sorted(allowed)}")
        return self.status


class MatchIn(BaseModel):
    jobs: list[dict]


class GenerateIn(BaseModel):
    job: dict
    include_review: bool = True


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    # [{"role": "user"|"assistant", "content": "..."}]; capped so a hostile
    # client can't stuff the prompt.
    history: list[dict] = Field(default_factory=list, max_length=30)


# ---------------- endpoints ----------------
@app.get("/health")
def health():
    return {
        "ok": True,
        "version": app.version,
        "ai": app.state.model_factory() is not None,
        "auth": bool(API_KEY),
    }


@app.get("/career-twin")
def get_career_twin(user_id: str = Depends(auth)):
    return {"career_twin": db.load_career_twin(get_conn(), user_id)}


@app.patch("/career-twin")
def patch_career_twin(body: CareerTwinIn, user_id: str = Depends(auth)):
    """Merge incoming fields into the stored Career Twin (partial update)."""
    if len(json.dumps(body.data)) > MAX_TWIN_BYTES:
        raise HTTPException(status_code=413, detail="career twin payload too large")
    conn = get_conn()
    existing = db.load_career_twin(conn, user_id)
    existing.update(body.data)
    db.save_career_twin(conn, user_id, existing)
    return {"ok": True}


@app.post("/career-twin/extract")
def career_twin_extract(body: ResumeIn, user_id: str = Depends(rate_limit)):
    """CV text → structured Career Twin data (Gemini), merged into the store."""
    model = require_model()
    profile = run_extraction(core.extract_career_twin, model, body.cv_text)
    if not profile:
        raise HTTPException(status_code=422,
                            detail="could not extract a profile from that text")
    conn = get_conn()
    existing = db.load_career_twin(conn, user_id)
    existing.update(profile)
    db.save_career_twin(conn, user_id, existing)
    return {"career_twin": existing}


@app.post("/career-twin/upload")
async def career_twin_upload(
    file: UploadFile = File(...),
    user_id: str = Depends(rate_limit),
):
    """PDF binary → extracted Career Twin (Gemini), merged into the store."""
    model = require_model()
    pdf_bytes = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(pdf_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="PDF too large (max 15 MB)")
    try:
        cv_text = core.pdf_to_text(pdf_bytes)
    except Exception:
        raise HTTPException(status_code=422, detail="could not read that PDF")
    if len(cv_text.strip()) < 50:
        raise HTTPException(status_code=422,
                            detail="PDF appears to be image-only or too short to extract text")
    profile = run_extraction(core.extract_career_twin, model, cv_text)
    if not profile:
        raise HTTPException(status_code=422,
                            detail="could not extract a profile from that PDF")
    conn = get_conn()
    existing = db.load_career_twin(conn, user_id)
    existing.update(profile)
    db.save_career_twin(conn, user_id, existing)
    return {"career_twin": existing}


@app.post("/career-twin/complete")
def career_twin_complete(user_id: str = Depends(auth)):
    """Mark the Career Twin as activated (onboarding finished)."""
    conn = get_conn()
    existing = db.load_career_twin(conn, user_id)
    existing["onboarding_complete"] = True
    db.save_career_twin(conn, user_id, existing)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Legacy aliases — kept so any in-flight calls don't hard-break
# ---------------------------------------------------------------------------
@app.get("/profile")
def _legacy_get_profile(user_id: str = Depends(auth)):
    return {"profile": db.load_career_twin(get_conn(), user_id)}


@app.post("/resume/extract")
def _legacy_resume_extract(body: ResumeIn, user_id: str = Depends(auth)):
    """Deprecated — use POST /career-twin/extract."""
    model = require_model()
    profile = run_extraction(core.extract_profile, model, body.cv_text)
    if not profile:
        raise HTTPException(status_code=422,
                            detail="could not extract a profile from that text")
    conn = get_conn()
    existing = db.load_career_twin(conn, user_id)
    existing.update(profile)
    db.save_career_twin(conn, user_id, existing)
    return {"profile": existing}


@app.post("/verify")
def verify_endpoint(body: VerifyIn, user_id: str = Depends(rate_limit)):
    """Deterministic employer trust check. The only AI involvement is the
    narrow site-content consistency judgment, which degrades to None without
    a model — scores never come from an LLM."""
    if not (body.company or body.contact):
        raise HTTPException(status_code=422,
                            detail="provide a company name or contact")
    result = verify.verify_employer(
        body.company, body.contact, body.job_text, body.role,
        model=app.state.model_factory(),
        dns_fn=dns_fn, mx_fn=mx_fn, fetch_fn=fetch_fn,
        cache=_verify_cache)
    return result


@app.get("/applications")
def list_apps(user_id: str = Depends(auth)):
    return {"applications": db.list_applications(get_conn(), user_id)}


@app.post("/applications", status_code=201)
def create_app_row(body: ApplicationIn, user_id: str = Depends(auth)):
    StatusIn(status=body.status).validated()
    row = {"company": body.company, "role": body.role,
           "status": body.status, **body.extra}
    app_id = db.add_application(get_conn(), user_id, row)
    return {"id": app_id}


@app.post("/applications/generate")
def generate_application_endpoint(body: GenerateIn,
                                  user_id: str = Depends(rate_limit)):
    """Generate an honest tailored draft from a stored Career Twin.

    Reviewer mode costs one additional model call; the web UI must disclose
    that before invoking this endpoint.
    """
    model = require_model()
    profile = db.load_career_twin(get_conn(), user_id)
    if not profile:
        raise HTTPException(status_code=409,
                            detail="complete Career Twin setup first")
    job = body.job if isinstance(body.job, dict) else {}
    job_text = str(job.get("description") or job.get("job_text") or "").strip()
    if not job_text:
        raise HTTPException(status_code=422, detail="job description is required")
    company = str(job.get("company") or job.get("company_name") or "")
    result = run_extraction(core.generate_application, model, profile, job_text,
                            company, body.include_review)
    return {"generated": result}


@app.patch("/applications/{app_id}")
def set_app_status(app_id: int, body: StatusIn, user_id: str = Depends(auth)):
    status = body.validated()
    conn = get_conn()
    owned = conn.execute(
        "SELECT 1 FROM applications WHERE id = ? AND user_id = ?",
        (app_id, user_id)).fetchone()
    if not owned:
        raise HTTPException(status_code=404, detail="application not found")
    db.update_application_status(conn, app_id, status)
    return {"ok": True}


@app.post("/matches")
def matches_endpoint(body: MatchIn, user_id: str = Depends(rate_limit)):
    """Rank jobs against the stored profile (Gemini)."""
    model = require_model()
    profile = db.load_career_twin(get_conn(), user_id)
    if not profile:
        raise HTTPException(status_code=409,
                            detail="no Career Twin yet — complete setup first")
    if not body.jobs:
        raise HTTPException(status_code=422, detail="no jobs provided")
    return {"matches": run_extraction(core.match_jobs, model, profile, body.jobs)}


@app.post("/chat")
def chat_endpoint(body: ChatIn, user_id: str = Depends(rate_limit)):
    """One Career Twin chat turn (Gemini). Profile facts the candidate states
    are merged into their stored twin via core.apply_chat_updates — appended,
    never overwritten wholesale."""
    model = require_model()
    conn = get_conn()
    twin = db.load_career_twin(conn, user_id)
    if not twin:
        raise HTTPException(status_code=409,
                            detail="no Career Twin yet — complete setup first")
    history = "\n".join(
        f"{'user' if h.get('role') == 'user' else 'assistant'}: {str(h.get('content', ''))[:1000]}"
        for h in body.history if str(h.get("content", "")).strip())
    reply, updates = run_extraction(core.chat_turn, model, twin, body.message, history)
    if updates:
        core.apply_chat_updates(twin, updates)
        db.save_career_twin(conn, user_id, twin)
    return {"reply": reply, "profile_updates": updates}


@app.delete("/user")
def delete_user(user_id: str = Depends(auth)):
    """NDPA/GDPR deletion right — removes everything stored for the user."""
    db.clear_user(get_conn(), user_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Job sourcing — read endpoints (writes happen via the ingest worker only)
# ---------------------------------------------------------------------------

class JobsQuery(BaseModel):
    remote_only: bool = False
    category: Optional[str] = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


@app.get("/jobs")
def list_ingested_jobs(
    remote_only: bool = False,
    category: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    user_id: str = Depends(auth),
):
    """Return ingested jobs with optional filters (incl. free-text q). Newest first."""
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=422, detail="limit must be 1–200")
    q = (q or "").strip()[:200] or None
    conn = get_conn()
    jobs = db.list_jobs(conn, remote_only=remote_only, category=category,
                        q=q, limit=limit, offset=offset)
    total = db.count_jobs(conn, remote_only=remote_only, category=category, q=q)
    return {"jobs": jobs, "total": total, "limit": limit, "offset": offset}


@app.get("/jobs/{job_id}")
def get_job(job_id: int, user_id: str = Depends(auth)):
    """Return a single ingested job by id."""
    row = get_conn().execute(
        "SELECT * FROM ingested_jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="job not found")
    return {"job": dict(row)}


@app.get("/matches")
def get_user_matches(limit: int = 50, user_id: str = Depends(rate_limit)):
    """Return the user's pre-computed match rankings (populated by the matching
    worker). Returns empty list if the worker hasn't run yet."""
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=422, detail="limit must be 1–200")
    return {"matches": db.list_matches(get_conn(), user_id, limit=limit)}


# ---------------------------------------------------------------------------
# Admin — job source registry
# ---------------------------------------------------------------------------

SOURCES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "job_sources.json")


class JobSourceIn(BaseModel):
    company: str
    ats: str = "greenhouse"
    token: str
    priority: int = Field(default=5, ge=1, le=10)
    category: Optional[str] = None
    region: Optional[str] = None
    active: bool = True


@app.get("/admin/job-sources")
def admin_list_sources(active_only: bool = False,
                       ats: Optional[str] = None,
                       user_id: str = Depends(auth)):
    """List all job source records."""
    conn = get_conn()
    db.seed_job_sources(conn, SOURCES_PATH)
    return {"sources": db.list_job_sources(conn, active_only=active_only, ats=ats)}


@app.post("/admin/job-sources", status_code=201)
def admin_add_source(body: JobSourceIn, user_id: str = Depends(auth)):
    """Add or update a job source (upsert on ats+token)."""
    conn = get_conn()
    source_id = db.upsert_job_source(
        conn, body.company, body.ats, body.token,
        body.priority, body.category, body.region, body.active)
    return {"id": source_id}


@app.patch("/admin/job-sources/{source_id}")
def admin_patch_source(source_id: int, body: JobSourceIn,
                       user_id: str = Depends(auth)):
    """Update a job source by id."""
    conn = get_conn()
    if not db.get_job_source(conn, source_id):
        raise HTTPException(status_code=404, detail="source not found")
    db.upsert_job_source(conn, body.company, body.ats, body.token,
                         body.priority, body.category, body.region, body.active)
    return {"ok": True}


@app.patch("/admin/job-sources/{source_id}/toggle")
def admin_toggle_source(source_id: int, active: bool,
                        user_id: str = Depends(auth)):
    """Enable or disable a job source."""
    if not db.set_job_source_active(get_conn(), source_id, active):
        raise HTTPException(status_code=404, detail="source not found")
    return {"ok": True, "active": active}


@app.post("/admin/job-sources/seed")
def admin_seed_sources(user_id: str = Depends(auth)):
    """Seed job_sources table from data/job_sources.json if empty."""
    conn = get_conn()
    inserted = db.seed_job_sources(conn, SOURCES_PATH)
    total = conn.execute("SELECT COUNT(*) AS n FROM job_sources").fetchone()["n"]
    return {"inserted": inserted, "total": total}


# ---------------------------------------------------------------------------
# Worker triggers — Render Cron Jobs can't mount the persistent disk that
# holds the SQLite file (a Render product limitation), so the scheduled
# workers run in-process here instead; render.yaml's cron services just curl
# these endpoints on schedule.
#
# Heavy workers (ingest, match, verify-employers) run in a BACKGROUND THREAD
# and the endpoint returns 202 immediately: Render's HTTP proxy hard-kills
# responses after ~100s, and a full match run (hundreds of jobs × Gemini
# calls) or daily ingest routinely exceeds that — a synchronous trigger
# reported false failures for runs that actually finished. The honest
# outcome record is the worker's own event row (JobIngestionRun /
# MatchingWorkerRun / VerificationWorkerRun in `events`) plus the service
# log; a cron "success" now means "trigger accepted". `?background=false`
# forces the old synchronous behavior for small runs and tests. Notify and
# backup finish in seconds and stay synchronous.
# ---------------------------------------------------------------------------

def _run_in_background(label: str, fn, *args, **kwargs):
    import threading

    def target():
        try:
            result = fn(*args, **kwargs)
            log.info("background %s finished: %s", label, result)
        except Exception:
            log.exception("background %s crashed", label)

    threading.Thread(target=target, name=f"worker-{label}", daemon=True).start()


@app.post("/admin/run/ingest", status_code=200)
def admin_run_ingest(response: Response, min_priority: int = 1,
                     background: bool = True,
                     _: None = Depends(admin_key_auth)):
    """Worker 1 — fetch jobs from Greenhouse/Lever/Ashby board APIs."""
    if background:
        _run_in_background("ingest", ingest_worker.run, DB_PATH,
                           min_priority=min_priority)
        response.status_code = 202
        return {"ok": True, "started": True, "background": True,
                "outcome": "see JobIngestionRun in events / service log"}
    result = ingest_worker.run(DB_PATH, min_priority=min_priority)
    if not result["ok"]:
        raise HTTPException(status_code=500, detail=result)
    return result


@app.post("/admin/run/match", status_code=200)
def admin_run_match(response: Response, background: bool = True,
                    _: None = Depends(admin_key_auth)):
    """Worker 3 — score fresh unmatched jobs against every completed Career Twin."""
    if background:
        _run_in_background("match", match_worker.run, DB_PATH,
                           model=app.state.model_factory())
        response.status_code = 202
        return {"ok": True, "started": True, "background": True,
                "outcome": "see MatchingWorkerRun in events / service log"}
    result = match_worker.run(DB_PATH, model=app.state.model_factory())
    if not result["ok"]:
        raise HTTPException(status_code=500, detail=result)
    return result


@app.post("/admin/run/verify-employers", status_code=200)
def admin_run_verify_employers(response: Response, background: bool = True,
                               _: None = Depends(admin_key_auth)):
    """Worker 2 — refresh stale employer trust records for direct company domains."""
    if background:
        _run_in_background("verify-employers", verify_worker.run, DB_PATH,
                           model=app.state.model_factory())
        response.status_code = 202
        return {"ok": True, "started": True, "background": True,
                "outcome": "see VerificationWorkerRun in events / service log"}
    result = verify_worker.run(DB_PATH, model=app.state.model_factory())
    if not result["ok"]:
        raise HTTPException(status_code=500, detail=result)
    return result


@app.post("/admin/run/notify")
def admin_run_notify(_: None = Depends(admin_key_auth)):
    """Worker 4 — send one digest email per user with unnotified matches."""
    result = notify_worker.run(DB_PATH, send_fn=notify_worker._get_send_fn())
    if not result["ok"]:
        raise HTTPException(status_code=500, detail=result)
    return result


@app.post("/admin/run/backup")
def admin_run_backup(_: None = Depends(admin_key_auth)):
    """Worker 5 — snapshot the SQLite file and upload it to Cloudflare R2."""
    result = backup_worker.run(DB_PATH)
    if not result["ok"]:
        raise HTTPException(status_code=500, detail=result)
    return result
