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
import re
import secrets
import sys
import logging
import threading
import uuid
from collections import defaultdict
from time import time
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, UploadFile, File, Request, Response
from pydantic import BaseModel, Field

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core  # noqa: E402
import db  # noqa: E402
import verify  # noqa: E402
import billing  # noqa: E402
import workers.ingest_jobs as ingest_worker  # noqa: E402
import workers.match_users as match_worker  # noqa: E402
import workers.verify_employers as verify_worker  # noqa: E402
import workers.notify_users as notify_worker  # noqa: E402
import workers.backup_db as backup_worker  # noqa: E402
import workers.expire_invites as expire_invites_worker  # noqa: E402

log = logging.getLogger("emploi.api")
logging.basicConfig(level=logging.INFO)

API_KEY = os.getenv("EMPLOI_API_KEY", "")
DB_PATH = os.getenv("EMPLOI_DB_PATH", "emploi.sqlite3")

# Billing — Paystack. Plan codes are created once in the Paystack dashboard
# (Products > Plans) and referenced by code, never by amount; TIER_PRICES_NGN
# in core.py is display-only. Unset PAYSTACK_SECRET_KEY = billing endpoints
# 503, same degradation posture as GEMINI_API_KEY.
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY", "")
PAYSTACK_PLAN_CODES = {
    "pro": os.getenv("PAYSTACK_PRO_PLAN_CODE", ""),
    "max": os.getenv("PAYSTACK_MAX_PLAN_CODE", ""),
}
WEB_APP_URL = os.getenv("WEB_APP_URL", "https://app.emploihq.com")

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
    "/applications/cv": (10, 3600),
    # Export is pure rendering (no model call), but it is CPU work on
    # user-supplied text — keep a ceiling on it anyway.
    "/applications/export": (30, 3600),
    "/chat": (20, 60),
    "/chat/attach": (5, 300),
    # Employer Portal (Phase 2). Numeric path segments are normalized to
    # {id} before lookup so per-role paths share one bucket per user.
    "/employer/roles": (20, 3600),
    "/employer/roles/{id}/shortlist": (30, 60),
    "/employer/roles/{id}/shortlist/refresh": (3, 3600),
    "/employer/roles/{id}/invites": (30, 60),
    "/employer/roles/{id}/unlocks": (30, 60),
    "/invites/count": (60, 60),
}

_NUMERIC_SEGMENT_RE = re.compile(r"/\d+")


def get_conn():
    """One connection per process; sqlite serializes writes internally."""
    if not hasattr(get_conn, "_conn"):
        get_conn._conn = db.connect(DB_PATH, check_same_thread=False)
    return get_conn._conn


GENERATE_CALL_TIMEOUT_S = 25  # per-provider-call bound; see FallbackModel/GroqModel


class GroqModel:
    """Duck-typed .generate_content over Groq's OpenAI-compatible API.
    Fallback provider: Gemini free tier exhausts fast (observed in prod on
    launch day), and every AI feature dying with the primary provider is
    not acceptable. Same contract as GenerativeModel: returns an object
    with .text; raises on failure so FallbackModel/run_extraction see it."""

    def __init__(self, api_key: str, model_name: str):
        self._key = api_key
        self._model = model_name

    def generate_content(self, prompt: str):
        import requests
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {self._key}",
                     "Content-Type": "application/json"},
            json={"model": self._model,
                  "messages": [{"role": "user", "content": prompt}]},
            # Bounded so a stuck call fails fast rather than stalling a
            # generation job indefinitely (see GENERATE_CALL_TIMEOUT_S).
            timeout=GENERATE_CALL_TIMEOUT_S)
        resp.raise_for_status()

        class R:
            pass
        result = R()
        result.text = resp.json()["choices"][0]["message"]["content"]
        return result


class FallbackModel:
    """Tries the primary model; on ANY provider failure (quota, 5xx,
    network) transparently retries the same prompt on the fallback. Both
    are duck-typed, so every core function works unchanged."""

    def __init__(self, primary, fallback):
        self._primary = primary
        self._fallback = fallback

    def generate_content(self, prompt: str):
        try:
            return self._primary.generate_content(prompt)
        except Exception as exc:
            log.warning("primary model failed (%s: %s) — using fallback",
                        type(exc).__name__, str(exc)[:200])
            return self._fallback.generate_content(prompt)


class TimeoutGeminiModel:
    """Wraps a genai.GenerativeModel so every call carries the same bounded
    timeout as GroqModel — without this, a slow/stuck Gemini call can hang
    well past both our own client timeouts and Render's ~100s proxy limit,
    with nothing surfacing why (the original bug behind the "spins forever
    then fails" report)."""

    def __init__(self, inner):
        self._inner = inner

    def generate_content(self, prompt: str):
        return self._inner.generate_content(
            prompt, request_options={"timeout": GENERATE_CALL_TIMEOUT_S})


def get_model():
    """Duck-typed model: Gemini primary, Groq fallback when GROQ_API_KEY is
    set, or None when neither provider is configured."""
    gemini = None
    key = os.getenv("GEMINI_API_KEY", "")
    if key:
        import google.generativeai as genai
        genai.configure(api_key=key)
        gemini = TimeoutGeminiModel(
            genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.5-flash")))
    groq_key = os.getenv("GROQ_API_KEY", "")
    groq = GroqModel(groq_key, os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")) if groq_key else None
    if gemini and groq:
        return FallbackModel(gemini, groq)
    return gemini or groq


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
    path = _NUMERIC_SEGMENT_RE.sub("/{id}", request.url.path)
    limit, window = RATE_LIMITS.get(path, RATE_LIMITS["default"])
    now = time()
    key = f"{user_id}:{path}"
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
# A cover letter or 2-page CV is a few KB; this is a generous ceiling that
# still stops a direct caller handing the renderers an unbounded blob.
MAX_EXPORT_BYTES = 256 * 1024

_EXPORT_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _export_slug(title: str) -> str:
    """Filename-safe slug. Never let user text steer the Content-Disposition
    header (quotes, newlines, path separators)."""
    slug = _EXPORT_SLUG_RE.sub("-", (title or "").lower()).strip("-")
    return slug[:80] or "emploi-application"


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
    outcome_notes: Optional[str] = Field(default=None, max_length=1000)

    def validated(self) -> str:
        # Outcome loop: `heard_back` and `ghosted` are first-class alongside
        # the older set. Order is loose (real-life isn't linear) — the UI is
        # a dropdown, not a stepper. `ghosted` is explicit because most
        # applications actually end there and pretending otherwise is
        # dishonest.
        allowed = {"applied", "heard_back", "interview", "offer",
                   "rejected", "withdrawn", "ghosted"}
        if self.status not in allowed:
            raise HTTPException(status_code=422,
                                detail=f"status must be one of {sorted(allowed)}")
        return self.status


class MatchIn(BaseModel):
    jobs: list[dict]


class GenerateIn(BaseModel):
    job: dict
    include_review: bool = True


class CvIn(BaseModel):
    job: dict


class ExportIn(BaseModel):
    """Render already-generated text to a real document.

    The text round-trips from the client because generations are not persisted
    (v1, by design) — it is the user's own draft over an authenticated channel.
    Callers must send ONLY exportable sections (cover letter / CV); the fit
    evaluation is screen-only. See core.split_application.
    """
    text: str
    format: str = "pdf"  # "pdf" | "docx"
    title: str = "Application"


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


# ---------------------------------------------------------------------------
# Application generation — asynchronous. A reviewed draft is TWO sequential
# Gemini calls; a slow/exhausted provider can push that past both our own
# client timeouts and Render's ~100s proxy limit, and a single blocking
# request has no way to say anything while it waits ("spins forever then
# fails" — the real bug, not a broken feature). Submit returns immediately;
# the client polls GET /applications/generate/{job_id} for status. Jobs live
# in-process (single-server deployment, same posture as _rate_counters) and
# expire after _JOB_TTL_S so a crashed poll doesn't leak memory forever.
# ---------------------------------------------------------------------------

_generation_jobs: dict = {}
_generation_jobs_lock = threading.Lock()
_JOB_TTL_S = 15 * 60


def _set_job(job_id: str, **fields) -> None:
    with _generation_jobs_lock:
        current = _generation_jobs.get(job_id, {})
        _generation_jobs[job_id] = {**current, **fields, "updated_at": time()}


def _get_job(job_id: str):
    with _generation_jobs_lock:
        job = _generation_jobs.get(job_id)
        return dict(job) if job else None


def _prune_generation_jobs() -> None:
    cutoff = time() - _JOB_TTL_S
    with _generation_jobs_lock:
        for stale_id in [jid for jid, j in _generation_jobs.items()
                         if j.get("updated_at", 0) < cutoff]:
            _generation_jobs.pop(stale_id, None)


@app.post("/applications/generate", status_code=202)
def generate_application_endpoint(body: GenerateIn, response: Response,
                                  background: bool = True,
                                  user_id: str = Depends(rate_limit)):
    """Generate an honest tailored draft from a stored Career Twin.

    Reviewer mode costs one additional model call; the web UI must disclose
    that before invoking this endpoint. Runs asynchronously by default —
    poll GET /applications/generate/{job_id} for the result.
    `?background=false` runs synchronously (used by tests and any caller
    that genuinely wants to block).
    """
    model = require_model()
    conn = get_conn()
    profile = db.load_career_twin(conn, user_id)
    if not profile:
        raise HTTPException(status_code=409,
                            detail="complete Career Twin setup first")
    job = body.job if isinstance(body.job, dict) else {}
    job_text = str(job.get("description") or job.get("job_text") or "").strip()
    if not job_text:
        raise HTTPException(status_code=422, detail="job description is required")
    company = str(job.get("company") or job.get("company_name") or "")

    sub = db.get_subscription(conn, user_id)
    limit = core.monthly_generation_limit(sub["tier"])
    used = db.count_generations_this_month(conn, user_id)
    if used >= limit:
        raise HTTPException(
            status_code=402,
            detail=f"You've used all {limit} tailored drafts on the {sub['tier'].title()} "
                   f"plan this month. Upgrade for more, or skip the draft and apply directly.")

    if not background:
        response.status_code = 200
        result = run_extraction(core.generate_application, model, profile, job_text,
                                company, body.include_review)
        db.log_generation(conn, user_id)
        return {"generated": result}

    job_id = uuid.uuid4().hex
    _set_job(job_id, status="pending", user_id=user_id)

    def task():
        try:
            result = core.generate_application(model, profile, job_text, company,
                                               body.include_review)
            db.log_generation(get_conn(), user_id)
            _set_job(job_id, status="done", result=result)
        except Exception as exc:
            log.exception("generation job %s failed", job_id)
            _set_job(job_id, status="error",
                     error="The AI service is temporarily unavailable — try again in a moment.",
                     detail=str(exc)[:200])

    threading.Thread(target=task, name=f"generate-{job_id}", daemon=True).start()
    _prune_generation_jobs()
    return {"job_id": job_id, "status": "pending"}


@app.post("/applications/cv", status_code=202)
def generate_cv_endpoint(body: CvIn, response: Response, background: bool = True,
                         user_id: str = Depends(rate_limit)):
    """Generate a COMPLETE tailored CV (core.generate_cv + skills/cv_template).

    This is the artifact users actually send — distinct from the cover-letter
    draft's "CV Bullet Points", which are fragments. One model call. Counts
    against the same monthly generation allowance; the UI must disclose that.
    Async by default (same rationale as /applications/generate); poll
    GET /applications/generate/{job_id}.
    """
    model = require_model()
    conn = get_conn()
    profile = db.load_career_twin(conn, user_id)
    if not profile:
        raise HTTPException(status_code=409,
                            detail="complete Career Twin setup first")
    job = body.job if isinstance(body.job, dict) else {}
    job_text = str(job.get("description") or job.get("job_text") or "").strip()
    if not job_text:
        raise HTTPException(status_code=422, detail="job description is required")
    company = str(job.get("company") or job.get("company_name") or "")

    sub = db.get_subscription(conn, user_id)
    limit = core.monthly_generation_limit(sub["tier"])
    used = db.count_generations_this_month(conn, user_id)
    if used >= limit:
        raise HTTPException(
            status_code=402,
            detail=f"You've used all {limit} tailored drafts on the {sub['tier'].title()} "
                   f"plan this month. Upgrade for more, or export the CV you already have.")

    if not background:
        response.status_code = 200
        cv = run_extraction(core.generate_cv, model, profile, job_text, company)
        db.log_generation(conn, user_id)
        return {"generated": {"cv": cv, "company": company}}

    job_id = uuid.uuid4().hex
    _set_job(job_id, status="pending", user_id=user_id)

    def task():
        try:
            cv = core.generate_cv(model, profile, job_text, company)
            db.log_generation(get_conn(), user_id)
            _set_job(job_id, status="done", result={"cv": cv, "company": company})
        except Exception as exc:
            log.exception("cv job %s failed", job_id)
            _set_job(job_id, status="error",
                     error="The AI service is temporarily unavailable — try again in a moment.",
                     detail=str(exc)[:200])

    threading.Thread(target=task, name=f"cv-{job_id}", daemon=True).start()
    _prune_generation_jobs()
    return {"job_id": job_id, "status": "pending"}


@app.post("/applications/export")
def export_application(body: ExportIn, user_id: str = Depends(rate_limit)):
    """Render generated text into a real .pdf / .docx the user can send.

    No model call and nothing persisted — pure rendering of text the caller
    already holds.

    The fit evaluation is screen-only (it is the candidate's own gap analysis),
    so it is stripped HERE rather than trusted to the caller: a comment saying
    "don't send the evaluation" is not a guard. Any caller — web, a future
    client, or a direct API user — gets an evaluation-free document.
    """
    fmt = (body.format or "").strip().lower()
    if fmt not in ("pdf", "docx"):
        raise HTTPException(status_code=422, detail="format must be 'pdf' or 'docx'")
    # Bound what we accept at all, before doing any work on it.
    raw = body.text or ""
    if len(raw.encode("utf-8")) > MAX_EXPORT_BYTES:
        raise HTTPException(status_code=413, detail="document too large to export")
    # Server-side backstop, applied before the emptiness check so a body that is
    # ONLY an evaluation is rejected as "nothing to export" rather than shipped.
    text = core.strip_evaluation(raw).strip()
    if not text:
        raise HTTPException(status_code=422, detail="nothing to export")

    title = (body.title or "Application").strip()[:120] or "Application"
    try:
        if fmt == "pdf":
            payload = core.make_pdf(text)
            media = "application/pdf"
        else:
            payload = core.make_docx(text, title=title)
            media = ("application/vnd.openxmlformats-officedocument"
                     ".wordprocessingml.document")
    except Exception:
        # Renderer choked on this text (fpdf2 is fussy about layout). Fail
        # cleanly — the user still has the draft on screen to copy.
        log.exception("export failed for user %s (%s)", user_id, fmt)
        raise HTTPException(status_code=422,
                            detail="We couldn't build that document. You can still copy the text.")

    filename = f"{_export_slug(title)}.{fmt}"
    return Response(
        content=payload,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/applications/generate/{job_id}")
def get_generation_job(job_id: str, user_id: str = Depends(auth)):
    """Poll a generation job started above. 404 for an unknown id or one
    that belongs to a different user — never leak that a job id exists."""
    job = _get_job(job_id)
    if not job or job.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="generation job not found")
    payload = {"status": job["status"]}
    if job["status"] == "done":
        payload["generated"] = job["result"]
    elif job["status"] == "error":
        payload["error"] = job["error"]
    return payload


# ---------------------------------------------------------------------------
# Billing — Paystack. Paystack's subscription lifecycle is authoritative;
# our `subscriptions` table is a cache kept in sync by the webhook below
# (the durable path) and /billing/verify (instant feedback right after
# checkout, since the webhook can lag a few seconds behind the redirect).
# ---------------------------------------------------------------------------

class CheckoutIn(BaseModel):
    tier: str  # "pro" | "max"


class VerifyIn(BaseModel):
    reference: str


def require_paystack() -> None:
    if not PAYSTACK_SECRET_KEY:
        raise HTTPException(status_code=503,
                            detail="Billing is not configured on this server.")


@app.get("/billing/status")
def billing_status(user_id: str = Depends(auth)):
    conn = get_conn()
    sub = db.get_subscription(conn, user_id)
    tier = sub["tier"]
    return {
        "tier": tier,
        "status": sub["status"],
        "current_period_end": sub.get("current_period_end"),
        "used_this_month": db.count_generations_this_month(conn, user_id),
        "limit": core.monthly_generation_limit(tier),
        "prices_ngn": core.TIER_PRICES_NGN,
    }


@app.post("/billing/checkout")
def billing_checkout(body: CheckoutIn, user_id: str = Depends(auth)):
    require_paystack()
    if body.tier not in ("pro", "max"):
        raise HTTPException(status_code=422, detail="tier must be 'pro' or 'max'")
    plan_code = PAYSTACK_PLAN_CODES.get(body.tier, "")
    if not plan_code:
        raise HTTPException(status_code=503,
                            detail=f"The {body.tier} plan isn't configured yet — try again shortly.")
    conn = get_conn()
    twin = db.load_career_twin(conn, user_id)
    email = (twin or {}).get("email") or ""
    if not email:
        raise HTTPException(status_code=422,
                            detail="We need your email on file before checkout — "
                                   "complete your Career Twin first.")
    try:
        data = billing.initialize_transaction(
            PAYSTACK_SECRET_KEY, email, core.TIER_PRICES_NGN[body.tier], plan_code,
            callback_url=f"{WEB_APP_URL}/settings?billing=return",
            metadata={"user_id": user_id, "tier": body.tier})
    except Exception:
        log.exception("Paystack checkout init failed for user %s", user_id[-8:])
        raise HTTPException(status_code=502,
                            detail="Couldn't start checkout — try again in a moment.")
    return {"authorization_url": data["authorization_url"], "reference": data["reference"]}


@app.post("/billing/verify")
def billing_verify(body: VerifyIn, user_id: str = Depends(auth)):
    """Called by the settings page right after the Paystack redirect, for
    instant UI feedback. The webhook below is still what's authoritative —
    this just avoids a user staring at 'Free' for the few seconds before it
    arrives."""
    require_paystack()
    try:
        data = billing.verify_transaction(PAYSTACK_SECRET_KEY, body.reference)
    except Exception:
        raise HTTPException(status_code=502, detail="Couldn't verify that payment yet — try refreshing shortly.")
    metadata = data.get("metadata") or {}
    tier = metadata.get("tier")
    if metadata.get("user_id") != user_id or tier not in ("pro", "max"):
        raise HTTPException(status_code=404, detail="transaction not found for this account")
    conn = get_conn()
    # paystack_subscription_code isn't in the verify response — Paystack
    # creates the subscription async after the charge and reports its code
    # via the subscription.create webhook, handled below.
    db.upsert_subscription(
        conn, user_id, tier=tier, status="active",
        paystack_customer_code=(data.get("customer") or {}).get("customer_code"),
        paystack_email=(data.get("customer") or {}).get("email"))
    return {"tier": tier, "status": "active"}


@app.post("/billing/cancel")
def billing_cancel(user_id: str = Depends(auth)):
    require_paystack()
    conn = get_conn()
    sub = db.get_subscription(conn, user_id)
    if sub["tier"] == "free" or not sub.get("paystack_subscription_code"):
        raise HTTPException(status_code=409, detail="no active paid subscription to cancel")
    try:
        details = billing.fetch_subscription(PAYSTACK_SECRET_KEY, sub["paystack_subscription_code"])
        billing.disable_subscription(PAYSTACK_SECRET_KEY, sub["paystack_subscription_code"],
                                     details.get("email_token", ""))
    except Exception:
        log.exception("Paystack cancel failed for user %s", user_id[-8:])
        raise HTTPException(status_code=502, detail="Couldn't cancel with Paystack — try again shortly.")
    db.upsert_subscription(conn, user_id, status="cancelled")
    return {"ok": True}


@app.post("/billing/webhook")
async def billing_webhook(request: Request):
    """Paystack's authoritative event stream. No X-API-Key/X-User-Id here —
    Paystack authenticates itself via the HMAC signature on the raw body,
    not our normal service-to-service headers."""
    require_paystack()
    raw = await request.body()
    signature = request.headers.get("x-paystack-signature", "")
    if not billing.verify_webhook_signature(PAYSTACK_SECRET_KEY, raw, signature):
        raise HTTPException(status_code=401, detail="invalid signature")

    event = billing.parse_webhook_event(raw)
    kind = event.get("event", "")
    data = event.get("data", {})
    conn = get_conn()

    if kind == "charge.success":
        metadata = data.get("metadata") or {}
        # Employer unlock-credit packs (one-time payments). The ledger's
        # UNIQUE paystack_reference makes webhook replays a no-op — never
        # double-credit.
        if metadata.get("kind") == "employer_credits":
            try:
                employer_id = int(metadata.get("employer_id"))
                credits = int(metadata.get("credits"))
            except (TypeError, ValueError):
                return {"received": True}
            if credits > 0 and data.get("reference"):
                db.add_credits(conn, employer_id, credits, "purchase",
                               paystack_reference=data["reference"])
                db.log_event(conn, "CreditPurchase",
                             {"employer_id": employer_id, "credits": credits})
            return {"received": True}
        user_id = metadata.get("user_id")
        tier = metadata.get("tier")
        if user_id and tier in ("pro", "max"):
            db.upsert_subscription(
                conn, user_id, tier=tier, status="active",
                paystack_customer_code=(data.get("customer") or {}).get("customer_code"),
                paystack_email=(data.get("customer") or {}).get("email"))
    elif kind == "subscription.create":
        # Paystack creates the subscription asynchronously after the first
        # successful charge; this is the only reliable place we learn its
        # code, which /billing/cancel later needs to disable it.
        customer_code = (data.get("customer") or {}).get("customer_code")
        sub_code = data.get("subscription_code", "")
        if customer_code and sub_code:
            conn.execute(
                "UPDATE subscriptions SET paystack_subscription_code = ?, "
                "updated_at = datetime('now') WHERE paystack_customer_code = ?",
                (sub_code, customer_code))
            conn.commit()
    elif kind in ("subscription.disable", "subscription.not_renew"):
        code = data.get("subscription_code", "")
        if code:
            conn.execute(
                "UPDATE subscriptions SET tier = 'free', status = 'cancelled', "
                "updated_at = datetime('now') WHERE paystack_subscription_code = ?", (code,))
            conn.commit()
    elif kind == "invoice.payment_failed":
        code = (data.get("subscription") or {}).get("subscription_code", "")
        if code:
            conn.execute(
                "UPDATE subscriptions SET status = 'past_due', updated_at = datetime('now') "
                "WHERE paystack_subscription_code = ?", (code,))
            conn.commit()
    return {"received": True}


@app.patch("/applications/{app_id}")
def set_app_status(app_id: int, body: StatusIn, user_id: str = Depends(auth)):
    status = body.validated()
    conn = get_conn()
    owned = conn.execute(
        "SELECT 1 FROM applications WHERE id = ? AND user_id = ?",
        (app_id, user_id)).fetchone()
    if not owned:
        raise HTTPException(status_code=404, detail="application not found")
    db.update_application_status(conn, app_id, status, body.outcome_notes)
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


@app.post("/chat/attach")
async def chat_attach(file: UploadFile = File(...),
                      user_id: str = Depends(rate_limit)):
    """Handle a PDF dropped into the Career Twin chat. The document is
    classified first (core.classify_document — the same guard that keeps
    job-listing PDFs out of the CV parser): a CV refreshes the stored twin,
    a job listing gets extracted and scored against the twin, anything else
    gets an honest 'couldn't use this' reply."""
    model = require_model()
    conn = get_conn()
    twin = db.load_career_twin(conn, user_id)
    if not twin:
        raise HTTPException(status_code=409,
                            detail="no Career Twin yet — complete setup first")
    pdf_bytes = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(pdf_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="PDF too large (max 15 MB)")
    try:
        text = core.pdf_to_text(pdf_bytes)
    except Exception:
        raise HTTPException(status_code=422, detail="could not read that PDF")
    if len(text.strip()) < 50:
        raise HTTPException(status_code=422,
                            detail="that PDF looks image-only or empty — try a text-based file")

    kind = run_extraction(core.classify_document, model, text)
    if kind == "cv":
        extracted = run_extraction(core.extract_career_twin, model, text)
        if not extracted:
            raise HTTPException(status_code=422,
                                detail="couldn't extract a profile from that CV")
        merged = {k: v for k, v in extracted.items()
                  if v not in ("", [], None)}
        twin.update(merged)
        db.save_career_twin(conn, user_id, twin)
        updated = ", ".join(sorted(merged.keys()))
        return {"kind": "cv",
                "reply": f"I read your CV and refreshed your Career Twin ({updated}). "
                         "Your preferences and goals are untouched — check the "
                         "Career Twin page to review."}
    if kind == "jobs":
        jobs = run_extraction(core.extract_jobs, model, text)
        if not jobs:
            raise HTTPException(status_code=422,
                                detail="I saw job listings but couldn't extract them cleanly")
        ranked = run_extraction(core.match_jobs, model, twin, jobs[:20])
        top = [r for r in ranked if r.get("fit_score") is not None][:5]
        lines = [f"- {r.get('title') or r.get('company', 'Role')} at "
                 f"{r.get('company', 'unknown')}: {r['fit_score']}/100 — {r.get('reason', '')}"
                 for r in top]
        return {"kind": "jobs", "matches": ranked,
                "reply": ("I found " + str(len(jobs)) + " job(s) in that document. "
                          "Scored against your profile:\n" + "\n".join(lines)
                          + "\n\nUse Import a Job if you want a tailored application for one.")}
    return {"kind": "other",
            "reply": "I read that document but it doesn't look like a CV or a "
                     "job listing, so I haven't changed anything. You can tell "
                     "me what it is and what you'd like me to do."}


# ---------------------------------------------------------------------------
# User session — the web tier's (app)/layout.tsx calls POST /user/session on
# every authenticated render so the users table has the current email/name
# from the NextAuth session. The users table is the source of truth for
# email + notifications_enabled (superseding the legacy career_twins.data.email
# blob field, which stays read-only for one release for backfill).
# ---------------------------------------------------------------------------

class UserSessionIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    name: Optional[str] = Field(default=None, max_length=200)
    email_verified: bool = False


class NotificationsIn(BaseModel):
    enabled: bool


@app.post("/user/session")
def user_session(body: UserSessionIn, user_id: str = Depends(auth)):
    """Idempotent upsert of the signed-in user's identity. Never logs the
    email as PII in an error/trace — validation errors surface as 422 with
    generic messages."""
    if "@" not in body.email:
        raise HTTPException(status_code=422, detail="invalid email")
    db.upsert_user(get_conn(), user_id, body.email, body.name,
                   body.email_verified)
    return {"ok": True}


@app.patch("/user/notifications")
def user_notifications(body: NotificationsIn, user_id: str = Depends(auth)):
    """Toggle email-digest opt-in. 409 if the user has never called
    POST /user/session (should be impossible from the web tier, but a direct
    API caller could hit it before establishing their session row)."""
    if not db.set_notifications_enabled(get_conn(), user_id, body.enabled):
        raise HTTPException(status_code=409,
                            detail="user session not established; POST /user/session first")
    return {"ok": True, "notifications_enabled": body.enabled}


@app.delete("/user")
def delete_user(user_id: str = Depends(auth)):
    """NDPA/GDPR deletion right — removes everything stored for the user."""
    db.clear_user(get_conn(), user_id)
    return {"ok": True}


# ===========================================================================
# Employer Portal (Phase 2) — Interview Marketplace + pay-per-unlock billing
#
# Decisions locked with Joy 2026-07-16 (PHASE_2_EMPLOYER_PORTAL.md addendum):
# role #1 free (contact on candidate ACCEPT, 10-invite cap); roles 2+ free to
# post, but inviting requires unlocking the candidate (1 credit = ₦1,000,
# packs of min 5) and unlock reveals contact immediately. Trust gating per
# verify.employer_portal_level; 'avoid' employers are never created. Every
# endpoint here is dispatch only — rules live in core.py / verify.py / db.py.
# ===========================================================================

class EmployerOnboardIn(BaseModel):
    company_name: str = Field(min_length=2, max_length=200)
    company_domain: Optional[str] = Field(default=None, max_length=200)


class EmployerPatchIn(BaseModel):
    company_name: Optional[str] = Field(default=None, min_length=2, max_length=200)
    company_domain: Optional[str] = Field(default=None, max_length=200)


class RoleCreateIn(BaseModel):
    url: Optional[str] = Field(default=None, max_length=1000)
    jd_text: Optional[str] = Field(default=None, max_length=30000)
    title_override: Optional[str] = Field(default=None, max_length=200)


class RolePatchIn(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = Field(default=None, max_length=30000)
    location: Optional[str] = Field(default=None, max_length=200)
    is_remote: Optional[bool] = None
    salary_text: Optional[str] = Field(default=None, max_length=200)


class RoleCloseIn(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=200)  # nudge, never forced


class HireIn(BaseModel):
    invite_id: int


class ShortlistRefreshIn(BaseModel):
    refinement_note: Optional[str] = Field(default=None, max_length=1000)


class InviteCreateIn(BaseModel):
    candidate_user_id: str = Field(min_length=1, max_length=200)
    invite_note: Optional[str] = Field(default=None, max_length=500)


class UnlockIn(BaseModel):
    candidate_user_id: str = Field(min_length=1, max_length=200)


class CreditCheckoutIn(BaseModel):
    credits: int = Field(ge=1, le=1000)


class DeclineIn(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=500)


class VisibilityIn(BaseModel):
    enabled: bool


def require_employer(user_id: str) -> dict:
    employer = db.get_employer_for_user(get_conn(), user_id)
    if not employer:
        raise HTTPException(status_code=404,
                            detail="no employer account — complete employer onboarding first")
    return employer


def require_owned_role(role_id: int, employer: dict) -> dict:
    role = db.get_role(get_conn(), role_id, employer_id=employer["id"])
    if not role:
        raise HTTPException(status_code=404, detail="role not found")
    return role


def block_avoid_tier(employer: dict) -> None:
    """Avoid-tier employers can't be CREATED via onboarding, but a domain
    change through PATCH /employer can re-verify an existing row into
    'avoid'. Posting and inviting are blocked for them (vouch overrides)."""
    if employer.get("trust_level") == "avoid" and not employer.get("warm_intro_by"):
        raise HTTPException(status_code=403,
                            detail="We couldn't verify this employer, so posting "
                                   "and inviting are paused. Contact "
                                   "hello@emploihq.com and we'll review it with you.")


def _employer_trust_check(company_name: str, domain: str, conn) -> tuple:
    """Run the deterministic trust engine on a cold employer signup.
    Returns (score, portal_level). Verifies the company domain the same way
    workers/verify_employers does. (Session-email free-mail capping from the
    original spec was dropped with Joy 2026-07-16: all signups are Google
    auth — frequently personal gmail — and it would flatten every cold
    signup to 'low'.)"""
    result = verify.verify_employer(
        company_name, domain or "", model=app.state.model_factory(),
        dns_fn=dns_fn, mx_fn=mx_fn, fetch_fn=fetch_fn, cache=_verify_cache)
    level = verify.employer_portal_level(
        result.get("score"), (result.get("signals") or {}).get("red_flags"),
        result.get("signals"))
    if domain:
        db.upsert_trust_record(conn, domain, company_name, result)
    return result.get("score"), level


def _free_role_used(conn, employer_id: int) -> bool:
    return conn.execute("SELECT COUNT(*) FROM employer_roles WHERE employer_id = ?",
                        (employer_id,)).fetchone()[0] > 0


def _contact_visible(role: dict, invite_status: Optional[str],
                     unlocked: bool) -> bool:
    """The contact-reveal rule (locked with Joy): free role -> candidate must
    have ACCEPTED; paid role -> the employer must have unlocked (paid)."""
    if role.get("is_free"):
        return invite_status in ("accepted", "hired")
    return unlocked


def _candidate_contact_view(conn, candidate_user_id: str) -> dict:
    twin = db.load_career_twin(conn, candidate_user_id)
    user = db.get_user(conn, candidate_user_id)
    merged = dict(twin)
    if user and user.get("email"):
        merged["email"] = user["email"]
        merged.setdefault("name", user.get("name") or "")
    return core.format_employer_contact_view(merged)


def _generate_shortlist(role_id: int, refinement_note: str = "") -> int:
    """Rank all opted-in twins against a role and cache the result. One
    model call. Returns rows written. Raises on provider failure."""
    conn = get_conn()
    role = db.get_role(conn, role_id)
    if not role:
        return 0
    candidates = db.list_visible_twins(conn)
    if not candidates:
        return 0
    model = app.state.model_factory()
    if model is None:
        return 0
    ranked = core.rank_candidates_for_role(model, role, candidates,
                                           refinement_note or "")
    return db.replace_shortlist(conn, role_id, ranked)


# ---- employer onboarding / identity ----

@app.post("/employer/onboarding", status_code=201)
def employer_onboarding(body: EmployerOnboardIn, user_id: str = Depends(auth)):
    conn = get_conn()
    if db.get_employer_for_user(conn, user_id):
        raise HTTPException(status_code=409, detail="you already have an employer account")
    domain = (body.company_domain or "").strip().lower() or \
        ingest_worker._derive_company_domain(body.company_name)
    score, level = _employer_trust_check(body.company_name, domain, conn)
    if level == "avoid":
        # Never create the row — an avoid-tier employer must not exist.
        raise HTTPException(status_code=403,
                            detail="We couldn't verify this employer, so we can't "
                                   "open an account automatically. Contact "
                                   "hello@emploihq.com and we'll review it with you.")
    employer_id = db.create_employer(conn, body.company_name.strip(), domain,
                                     user_id, trust_score=score, trust_level=level)
    db.log_event(conn, "EmployerOnboarded",
                 {"employer_id": employer_id, "trust_level": level}, user_id=user_id)
    return {"employer_id": employer_id, "trust_score": score,
            "trust_level": level, "warm_intro_by": None}


@app.get("/employer")
def get_employer_endpoint(user_id: str = Depends(auth)):
    employer = require_employer(user_id)
    conn = get_conn()
    return {"employer": {
        "id": employer["id"],
        "company_name": employer["company_name"],
        "company_domain": employer["company_domain"],
        "trust_score": employer["trust_score"],
        "trust_level": employer["trust_level"],
        "warm_intro_by": employer["warm_intro_by"],
        "verified_at": employer["verified_at"],
        "free_role_used": _free_role_used(conn, employer["id"]),
        "credit_balance": db.credit_balance(conn, employer["id"]),
    }}


@app.patch("/employer")
def patch_employer(body: EmployerPatchIn, user_id: str = Depends(auth)):
    employer = require_employer(user_id)
    conn = get_conn()
    fields = {}
    if body.company_name:
        fields["company_name"] = body.company_name.strip()
    score, level = employer["trust_score"], employer["trust_level"]
    if body.company_domain and body.company_domain.strip().lower() != (employer["company_domain"] or ""):
        fields["company_domain"] = body.company_domain.strip().lower()
        score, level = _employer_trust_check(
            fields.get("company_name", employer["company_name"]),
            fields["company_domain"], conn)
        fields["trust_score"], fields["trust_level"] = score, level
        fields["verified_at"] = None  # set by set_employer_trust below
    if fields:
        db.update_employer(conn, employer["id"], **{k: v for k, v in fields.items()
                                                    if k != "verified_at"})
        if "trust_score" in fields:
            db.set_employer_trust(conn, employer["id"], score, level)
    return {"ok": True, "trust_score": score, "trust_level": level}


# ---- roles ----

@app.post("/employer/roles", status_code=201)
def create_role_endpoint(body: RoleCreateIn, user_id: str = Depends(rate_limit)):
    employer = require_employer(user_id)
    block_avoid_tier(employer)
    conn = get_conn()
    fields = None
    extracted_from = None
    if body.url:
        extracted = core.extract_job_from_url(body.url)
        if isinstance(extracted, dict) and extracted.get("error") == "unsupported_host":
            if not body.jd_text:
                raise HTTPException(status_code=422, detail=extracted["detail"])
        elif extracted:
            fields = extracted
            extracted_from = "url"
        else:
            # Not one of the 5 ATS APIs — try the generic career-page connector:
            # fetch the page HTML, reduce to text, let Gemini extract the role.
            # This is what makes "paste any job URL" work (careers pages, niche
            # boards, Greenhouse embeds), not just the ATS JSON hosts.
            page_text = core.fetch_url_text(body.url)
            if page_text:
                model = require_model()
                generic = run_extraction(core.extract_single_job, model, page_text)
                if generic and (generic.get("title") or "").strip():
                    fields = generic
                    fields["source_url"] = body.url
                    fields["source_ats"] = "web"
                    extracted_from = "url_generic"
            if fields is None and not body.jd_text:
                raise HTTPException(status_code=422,
                                    detail="we couldn't read that page — it may need a "
                                           "login or use heavy scripting. Paste the JD "
                                           "text directly and we'll take it from there.")
    if fields is None:
        if not (body.jd_text or "").strip():
            raise HTTPException(status_code=422,
                                detail="provide a supported job URL or paste the JD text")
        model = require_model()
        fields = run_extraction(core.extract_single_job, model, body.jd_text)
        if not fields:
            raise HTTPException(status_code=422,
                                detail="we couldn't extract a role from that text — "
                                       "check it's a job description")
        extracted_from = "text"
    if body.title_override:
        fields["title"] = body.title_override.strip()
    if not (fields.get("title") or "").strip():
        raise HTTPException(status_code=422, detail="couldn't determine the role title")
    fields.setdefault("source_url", body.url)
    created = db.create_role(conn, employer["id"], user_id, fields)
    db.log_event(conn, "EmployerRoleCreated",
                 {"role_id": created["id"], "is_free": created["is_free"],
                  "extracted_from": extracted_from}, user_id=user_id)
    # Kick off shortlist generation in the background — non-fatal if the
    # provider is down; GET /shortlist regenerates synchronously on demand.
    _run_in_background(f"shortlist-{created['id']}", _generate_shortlist, created["id"])
    return {"role_id": created["id"], "title": fields.get("title"),
            "location": fields.get("location"),
            "is_remote": bool(fields.get("is_remote")),
            "is_free": created["is_free"], "extracted_from": extracted_from}


@app.get("/employer/roles")
def list_roles_endpoint(status: Optional[str] = None, user_id: str = Depends(auth)):
    employer = require_employer(user_id)
    if status and status not in ("open", "closed", "hired"):
        raise HTTPException(status_code=422, detail="status must be open|closed|hired")
    roles = db.list_roles(get_conn(), employer["id"], status=status)
    return {"roles": [{
        "id": r["id"], "title": r["title"], "status": r["status"],
        "is_free": bool(r["is_free"]), "invites_sent": r["invites_sent"],
        "accepted_count": r["accepted_count"],
        "unread_responses": r["unread_responses"],
        "created_at": r["created_at"],
    } for r in roles]}


@app.get("/employer/roles/{role_id}")
def get_role_endpoint(role_id: int, user_id: str = Depends(auth)):
    employer = require_employer(user_id)
    role = require_owned_role(role_id, employer)
    conn = get_conn()
    invites = []
    for inv in db.list_role_invites(conn, role_id):
        unlocked = db.is_unlocked(conn, role_id, inv["candidate_user_id"])
        item = {
            "invite_id": inv["id"],
            "candidate_user_id": inv["candidate_user_id"],
            "candidate_name": (inv["twin"].get("name") or ""),
            "candidate_headline": (inv["twin"].get("headline")
                                   or inv["twin"].get("title") or ""),
            "fit_score": inv["fit_score"], "status": inv["status"],
            "invited_at": inv["created_at"], "expires_at": inv["expires_at"],
            "responded_at": inv["responded_at"],
            "decline_reason": inv["decline_reason"],
            "contact": None,
        }
        if _contact_visible(role, inv["status"], unlocked):
            item["contact"] = _candidate_contact_view(conn, inv["candidate_user_id"])
        invites.append(item)
    db.touch_role_viewed(conn, role_id)
    return {"role": {k: role[k] for k in (
        "id", "title", "description", "location", "is_remote", "salary_text",
        "source_url", "source_ats", "status", "is_free", "invites_sent",
        "close_reason", "created_at", "closed_at", "hired_at")},
        "invites": invites}


# ---------------------------------------------------------------------------
# Public job pages — UNAUTHENTICATED. A role's public link
# (app.emploihq.com/jobs/{id}) is shareable anywhere (LinkedIn, WhatsApp); the
# page is a customer-acquisition surface. Viewing needs no account; APPLYING
# requires Google sign-in (the funnel). Public-safe fields ONLY — never the
# shortlist, applicant list, or employer internals.
# ---------------------------------------------------------------------------

def _public_trust(role: dict) -> dict:
    """Candidate-facing provenance for a public role. Honest about what we
    checked (the company domain / legitimacy) — never claims we confirmed the
    poster IS the employer. `verified` stays reserved for a vouch/high signal."""
    verified = bool(role.get("warm_intro_by")) or role.get("trust_level") == "high"
    level = role.get("trust_level") or "unverified"
    if verified:
        label = "Verified employer"
    elif level in ("medium", "low"):
        label = "Company checked"
    else:
        label = "Unverified — never pay a fee to apply"
    return {"verified": verified, "trust_level": level, "label": label}


@app.get("/public/roles/{role_id}")
def public_role_endpoint(role_id: int):
    conn = get_conn()
    role = db.get_public_role(conn, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="job not found or no longer open")
    return {"role": {
        "id": role["id"], "title": role["title"], "description": role["description"],
        "location": role["location"], "is_remote": bool(role["is_remote"]),
        "salary_text": role["salary_text"], "company_name": role["company_name"],
        "created_at": role["created_at"], "trust": _public_trust(role)}}


@app.post("/public/roles/{role_id}/apply", status_code=201)
def public_apply_endpoint(role_id: int, user_id: str = Depends(auth)):
    """Apply to a public role. Auth-gated: this is the Google sign-in funnel.
    Idempotent — re-applying is a no-op, never an error."""
    conn = get_conn()
    result = db.create_role_application(conn, role_id, user_id)
    if result == "closed":
        raise HTTPException(status_code=409, detail="this job is no longer accepting applications")
    if result == "ok":
        db.log_event(conn, "PublicRoleApplied", {"role_id": role_id}, user_id=user_id)
    return {"ok": True, "status": "applied", "already_applied": result == "exists"}


@app.get("/employer/roles/{role_id}/applicants")
def role_applicants_endpoint(role_id: int, user_id: str = Depends(auth)):
    """Inbound applicants who applied via the role's public link. Their contact
    is shown immediately — they self-submitted, so it's consented (no unlock
    needed, unlike the curated shortlist)."""
    employer = require_employer(user_id)
    require_owned_role(role_id, employer)
    conn = get_conn()
    out = []
    for a in db.list_role_applicants(conn, role_id):
        twin = db.load_career_twin(conn, a["candidate_user_id"]) or {}
        contact = core.format_employer_contact_view(twin)
        # The application always carries a reachable email/name from the Google
        # account, even if the applicant hasn't built a full Career Twin yet.
        contact["email"] = contact.get("email") or a.get("email") or ""
        contact["name"] = contact.get("name") or a.get("name") or ""
        out.append({"candidate_user_id": a["candidate_user_id"],
                    "status": a["status"], "applied_at": a["created_at"],
                    "contact": contact})
    return {"applicants": out, "count": len(out)}


@app.patch("/employer/roles/{role_id}")
def patch_role_endpoint(role_id: int, body: RolePatchIn, user_id: str = Depends(auth)):
    employer = require_employer(user_id)
    role = require_owned_role(role_id, employer)
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    conn = get_conn()
    if fields:
        db.update_role(conn, role_id, **fields)
        # A materially different description invalidates the cached shortlist.
        if "description" in fields and fields["description"] != role["description"]:
            db.clear_shortlist(conn, role_id)
    return {"ok": True}


@app.post("/employer/roles/{role_id}/close")
def close_role_endpoint(role_id: int, body: RoleCloseIn = None,
                        user_id: str = Depends(auth)):
    employer = require_employer(user_id)
    require_owned_role(role_id, employer)
    expired = db.close_role(get_conn(), role_id,
                            reason=(body.reason if body else None))
    return {"ok": True, "expired_invites": expired}


@app.post("/employer/roles/{role_id}/hire")
def hire_endpoint(role_id: int, body: HireIn, user_id: str = Depends(auth)):
    employer = require_employer(user_id)
    role = require_owned_role(role_id, employer)
    conn = get_conn()
    result = db.hire_candidate(conn, role_id, body.invite_id)
    if result["error"] == "not_found":
        raise HTTPException(status_code=404, detail="invite not found for this role")
    if result["error"] == "not_accepted":
        raise HTTPException(status_code=422,
                            detail="only an accepted invite can be marked hired")
    db.log_event(conn, "HireCompleted",
                 {"role_id": role_id, "employer_id": employer["id"],
                  "was_free_role": bool(role["is_free"])}, user_id=user_id)
    return {"ok": True, "hired_at": db.get_role(conn, role_id)["hired_at"],
            "expired_other_invites": result["expired_others"]}


# ---- shortlist ----

@app.get("/employer/roles/{role_id}/shortlist")
def get_shortlist_endpoint(role_id: int, limit: int = 20, offset: int = 0,
                           user_id: str = Depends(rate_limit)):
    employer = require_employer(user_id)
    require_owned_role(role_id, employer)
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail="limit must be 1–100")
    conn = get_conn()
    if db.shortlist_cache_age_seconds(conn, role_id) is None:
        # Empty cache: generate synchronously (one model call).
        if not db.list_visible_twins(conn, limit=1):
            return {"shortlist": [], "total": 0, "cache_age": None,
                    "note": "no opted-in candidates yet"}
        require_model()
        run_extraction(_generate_shortlist, role_id)
    rows = db.list_shortlist(conn, role_id, limit=limit, offset=offset)
    role = db.get_role(conn, role_id)
    shortlist = []
    for r in rows:
        if r["already_invited"]:
            continue  # invited candidates live on the role's invites rail
        twin = r["twin"]
        shortlist.append({
            "candidate_id": r["candidate_user_id"],
            "fit_score": r["fit_score"], "reason": r["reason"],
            "headline": twin.get("headline") or twin.get("title") or "",
            "skills": twin.get("skills") if isinstance(twin.get("skills"), list)
                      else core.normalize_skills(twin.get("skills")),
            "experience_summary": core._entries_or_text(twin.get("experience"),
                                                        twin.get("bio")),
            "location": twin.get("location") or "",
            "already_invited": False,
            "unlocked": r["unlocked"],
            "contact": (_candidate_contact_view(conn, r["candidate_user_id"])
                        if _contact_visible(role, None, r["unlocked"]) else None),
        })
    return {"shortlist": shortlist, "total": db.count_shortlist(conn, role_id),
            "cache_age": db.shortlist_cache_age_seconds(conn, role_id)}


@app.post("/employer/roles/{role_id}/shortlist/refresh", status_code=202)
def refresh_shortlist_endpoint(role_id: int, body: ShortlistRefreshIn = None,
                               user_id: str = Depends(rate_limit)):
    employer = require_employer(user_id)
    require_owned_role(role_id, employer)
    require_model()
    conn = get_conn()
    db.clear_shortlist(conn, role_id)
    note = (body.refinement_note if body else "") or ""
    _run_in_background(f"shortlist-refresh-{role_id}", _generate_shortlist,
                       role_id, note)
    return {"started": True}


# ---- invites (employer side) ----

@app.post("/employer/roles/{role_id}/invites", status_code=201)
def create_invite_endpoint(role_id: int, body: InviteCreateIn,
                           user_id: str = Depends(rate_limit)):
    employer = require_employer(user_id)
    block_avoid_tier(employer)
    role = require_owned_role(role_id, employer)
    if role["status"] != "open":
        raise HTTPException(status_code=409, detail="this role is not open")
    conn = get_conn()
    if not db.get_recruiter_visibility(conn, body.candidate_user_id):
        raise HTTPException(status_code=404, detail="candidate not found or not opted in")
    unlocked = db.is_unlocked(conn, role_id, body.candidate_user_id)
    allowed, reason = core.invite_gate(bool(role["is_free"]),
                                       role["invites_sent"], unlocked)
    if not allowed:
        # Free-role cap -> 429 (abuse guard); missing unlock -> 402 (payment)
        raise HTTPException(status_code=429 if role["is_free"] else 402,
                            detail=reason)
    fit = conn.execute(
        "SELECT fit_score FROM role_shortlists WHERE employer_role_id = ? "
        "AND candidate_user_id = ?", (role_id, body.candidate_user_id)).fetchone()
    invite_id = db.create_invite(conn, role_id, body.candidate_user_id, user_id,
                                 fit_score=fit["fit_score"] if fit else None,
                                 invite_note=body.invite_note)
    if invite_id is None:
        raise HTTPException(status_code=409, detail="candidate already invited to this role")
    invite = db.get_invite(conn, invite_id)
    db.log_event(conn, "InterviewInviteSent",
                 {"invite_id": invite_id, "role_id": role_id}, user_id=user_id)
    # Email notification rides the nightly notify worker digest; the
    # dashboard badge (GET /invites/count) is immediate.
    return {"invite_id": invite_id, "expires_at": invite["expires_at"]}


# ---- unlocks + credit billing (employer side) ----

@app.post("/employer/roles/{role_id}/unlocks", status_code=201)
def unlock_candidate_endpoint(role_id: int, body: UnlockIn,
                              user_id: str = Depends(rate_limit)):
    employer = require_employer(user_id)
    role = require_owned_role(role_id, employer)
    if role["is_free"]:
        raise HTTPException(status_code=422,
                            detail="your free role doesn't need unlocks — invite "
                                   "directly; contact is shared when the candidate accepts")
    conn = get_conn()
    if not db.get_recruiter_visibility(conn, body.candidate_user_id):
        raise HTTPException(status_code=404, detail="candidate not found or not opted in")
    result = db.create_unlock(conn, role_id, employer["id"],
                              body.candidate_user_id, user_id)
    if result == "no_credits":
        raise HTTPException(status_code=402,
                            detail=f"you have no unlock credits — buy a pack "
                                   f"(min {core.MIN_UNLOCK_PACK} × "
                                   f"₦{core.UNLOCK_PRICE_NGN:,}) at "
                                   "/employer/billing")
    if result == "ok":
        db.log_event(conn, "CandidateUnlocked",
                     {"role_id": role_id, "employer_id": employer["id"]},
                     user_id=user_id)
    # 'exists' falls through — idempotent, contact returned either way.
    return {"ok": True, "already_unlocked": result == "exists",
            "credit_balance": db.credit_balance(conn, employer["id"]),
            "contact": _candidate_contact_view(conn, body.candidate_user_id)}


@app.get("/employer/billing/status")
def employer_billing_status(user_id: str = Depends(auth)):
    employer = require_employer(user_id)
    conn = get_conn()
    return {"credit_balance": db.credit_balance(conn, employer["id"]),
            "free_role_used": _free_role_used(conn, employer["id"]),
            "unlock_price_ngn": core.UNLOCK_PRICE_NGN,
            "min_pack": core.MIN_UNLOCK_PACK}


@app.post("/employer/billing/checkout")
def employer_credit_checkout(body: CreditCheckoutIn, user_id: str = Depends(auth)):
    require_paystack()
    employer = require_employer(user_id)
    if body.credits < core.MIN_UNLOCK_PACK:
        raise HTTPException(status_code=422,
                            detail=f"minimum pack is {core.MIN_UNLOCK_PACK} unlocks")
    conn = get_conn()
    user = db.get_user(conn, user_id)
    email = (user or {}).get("email") or ""
    if not email:
        raise HTTPException(status_code=422,
                            detail="we need your email on file before checkout — "
                                   "sign in again to refresh your session")
    amount = body.credits * core.UNLOCK_PRICE_NGN
    try:
        data = billing.initialize_onetime_transaction(
            PAYSTACK_SECRET_KEY, email, amount,
            callback_url=f"{WEB_APP_URL}/employer/billing?return=1",
            metadata={"kind": "employer_credits", "employer_id": employer["id"],
                      "credits": body.credits, "user_id": user_id})
    except Exception:
        log.exception("Paystack credit checkout init failed for employer %s",
                      employer["id"])
        raise HTTPException(status_code=502,
                            detail="Couldn't start checkout — try again in a moment.")
    return {"authorization_url": data["authorization_url"],
            "reference": data["reference"], "amount_ngn": amount}


@app.post("/employer/billing/verify")
def employer_credit_verify(body: VerifyIn, user_id: str = Depends(auth)):
    """Instant post-redirect feedback; the webhook stays authoritative. The
    ledger's UNIQUE reference makes calling both paths safe."""
    require_paystack()
    employer = require_employer(user_id)
    try:
        data = billing.verify_transaction(PAYSTACK_SECRET_KEY, body.reference)
    except Exception:
        raise HTTPException(status_code=502,
                            detail="Couldn't verify that payment yet — try refreshing shortly.")
    metadata = data.get("metadata") or {}
    if (metadata.get("kind") != "employer_credits"
            or str(metadata.get("employer_id")) != str(employer["id"])):
        raise HTTPException(status_code=404, detail="transaction not found for this employer")
    try:
        credits = int(metadata.get("credits"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=404, detail="transaction not found for this employer")
    conn = get_conn()
    if credits > 0 and data.get("reference"):
        db.add_credits(conn, employer["id"], credits, "purchase",
                       paystack_reference=data["reference"])
    return {"ok": True, "credit_balance": db.credit_balance(conn, employer["id"])}


# ---- candidate side: interview invites ----

_INVITE_STATUSES = {"pending", "accepted", "declined", "expired", "hired", "all"}


def _shape_candidate_invite(inv: dict, full: bool = False) -> dict:
    desc = inv.get("role_description") or ""
    shaped = {
        "id": inv["id"],
        "role": {
            "title": inv["role_title"],
            "description_preview": desc[:240],
            "location": inv["role_location"],
            "is_remote": bool(inv["role_is_remote"]),
            "salary_text": inv["role_salary_text"],
        },
        "employer": {
            "company_name": inv["company_name"],
            "trust_score": inv["trust_score"],
            "trust_level": inv["trust_level"],
            "verified": bool(inv["warm_intro_by"]) or inv["trust_level"] == "high",
        },
        "fit_score": inv["fit_score"],
        "invite_note": inv["invite_note"],
        "status": inv["status"],
        "expires_at": inv["expires_at"],
        "created_at": inv["created_at"],
        "responded_at": inv["responded_at"],
    }
    if full:
        shaped["role"]["description"] = desc
    return shaped


@app.get("/invites")
def list_invites_endpoint(status: str = "pending", user_id: str = Depends(auth)):
    if status not in _INVITE_STATUSES:
        raise HTTPException(status_code=422,
                            detail=f"status must be one of {sorted(_INVITE_STATUSES)}")
    invites = db.list_candidate_invites(get_conn(), user_id,
                                        status=None if status == "all" else status)
    return {"invites": [_shape_candidate_invite(i) for i in invites]}


@app.get("/invites/count")
def invites_count_endpoint(user_id: str = Depends(rate_limit)):
    return db.count_candidate_invites(get_conn(), user_id)


@app.get("/invites/{invite_id}")
def get_invite_endpoint(invite_id: int, user_id: str = Depends(auth)):
    inv = db.get_invite_detail(get_conn(), invite_id)
    if not inv or inv["candidate_user_id"] != user_id:
        raise HTTPException(status_code=404, detail="invite not found")
    shaped = _shape_candidate_invite(inv, full=True)
    # Employer trust evidence for the candidate's decision.
    record = db.get_trust_record(get_conn(), inv.get("company_domain") or "")
    shaped["employer"]["trust_evidence"] = (record or {}).get("evidence", [])
    return shaped


@app.post("/invites/{invite_id}/accept")
def accept_invite_endpoint(invite_id: int, user_id: str = Depends(auth)):
    conn = get_conn()
    inv = db.get_invite_detail(conn, invite_id)
    if not inv or inv["candidate_user_id"] != user_id:
        raise HTTPException(status_code=404, detail="invite not found")
    result = db.respond_invite(conn, invite_id, accept=True)
    if result == "expired":
        raise HTTPException(status_code=410, detail="this invite has expired")
    if result != "ok":
        raise HTTPException(status_code=409, detail="this invite is no longer pending")
    db.log_event(conn, "InterviewInviteAccepted", {"invite_id": invite_id},
                 user_id=user_id)
    # Keep agency with the candidate: hand them the employer's email so they
    # can reach out first if they want to (decision #9, confirmed).
    return {"ok": True,
            "employer_contact_email": db.get_employer_owner_email(
                conn, inv["employer_id"]) or ""}


@app.post("/invites/{invite_id}/decline")
def decline_invite_endpoint(invite_id: int, body: DeclineIn = None,
                            user_id: str = Depends(auth)):
    conn = get_conn()
    inv = db.get_invite(conn, invite_id)
    if not inv or inv["candidate_user_id"] != user_id:
        raise HTTPException(status_code=404, detail="invite not found")
    result = db.respond_invite(conn, invite_id, accept=False,
                               decline_reason=(body.reason if body else None))
    if result == "expired":
        raise HTTPException(status_code=410, detail="this invite has expired")
    if result != "ok":
        raise HTTPException(status_code=409, detail="this invite is no longer pending")
    return {"ok": True}


@app.get("/career-twin/recruiter-visibility")
def get_recruiter_visibility_endpoint(user_id: str = Depends(auth)):
    conn = get_conn()
    return {"recruiter_visibility": db.get_recruiter_visibility(conn, user_id),
            "has_twin": bool(db.load_career_twin(conn, user_id))}


@app.patch("/career-twin/recruiter-visibility")
def recruiter_visibility_endpoint(body: VisibilityIn, user_id: str = Depends(auth)):
    conn = get_conn()
    was_on = db.get_recruiter_visibility(conn, user_id)
    if not db.set_recruiter_visibility(conn, user_id, body.enabled):
        raise HTTPException(status_code=409,
                            detail="complete your Career Twin first")
    if body.enabled and not was_on:
        db.log_event(conn, "UserOptedInToRecruiterVisibility", {}, user_id=user_id)
    return {"ok": True, "recruiter_visibility": body.enabled}


# ---- admin: vouch + MVP metrics dashboard ----

class VouchIn(BaseModel):
    vouched_by: str = Field(default="joy", max_length=100)


class GrantCreditsIn(BaseModel):
    # Positive = grant; negative = claw back an erroneous grant. Bounded so a
    # fat-fingered admin can't mint a fortune. Zero is rejected as a no-op.
    delta: int = Field(ge=-500, le=500)
    reason: str = Field(default="admin_grant", min_length=1, max_length=100)


@app.post("/admin/employers/{employer_id}/vouch")
def admin_vouch_employer(employer_id: int, body: VouchIn = None,
                         _: None = Depends(admin_key_auth)):
    """Joy's post-signup warm-intro override: marks the employer personally
    vouched, clearing trust-badge restrictions. The recorded trust score
    stays for honesty."""
    conn = get_conn()
    if not db.vouch_employer(conn, employer_id,
                             (body.vouched_by if body else "joy")):
        raise HTTPException(status_code=404, detail="employer not found")
    db.log_event(conn, "EmployerVouched", {"employer_id": employer_id})
    return {"ok": True}


@app.get("/admin/employers")
def admin_list_employers(_: None = Depends(admin_key_auth)):
    """Every employer with its live credit balance, for the admin dashboard's
    credit-grant tool. No candidate PII."""
    return {"employers": db.list_employers(get_conn())}


@app.post("/admin/employers/{employer_id}/credits")
def admin_grant_credits(employer_id: int, body: GrantCreditsIn,
                        _: None = Depends(admin_key_auth)):
    """Grant (or claw back) unlock credits for an employer — e.g. comping a
    partner or fixing a billing mishap. Distinct from Paystack purchases:
    admin grants carry no paystack_reference, so they never collide with the
    webhook's replay-dedup. Trust gating is unaffected — credits don't verify."""
    if body.delta == 0:
        raise HTTPException(status_code=422, detail="delta must be non-zero")
    conn = get_conn()
    employer = db.get_employer(conn, employer_id)
    if not employer:
        raise HTTPException(status_code=404, detail="employer not found")
    # A clawback must never drive the balance negative (that would let the next
    # purchase silently backfill a debt the employer never incurred).
    balance = db.credit_balance(conn, employer_id)
    if balance + body.delta < 0:
        raise HTTPException(status_code=422,
                            detail=f"clawback exceeds balance ({balance} available)")
    db.add_credits(conn, employer_id, body.delta, f"admin:{body.reason}")
    new_balance = db.credit_balance(conn, employer_id)
    db.log_event(conn, "AdminGrantedCredits",
                 {"employer_id": employer_id, "delta": body.delta,
                  "reason": body.reason, "new_balance": new_balance})
    return {"ok": True, "credit_balance": new_balance}


@app.get("/admin/metrics")
def admin_metrics(_: None = Depends(admin_key_auth)):
    """MVP admin dashboard rollup (Next.js /admin). Counts only — no PII."""
    conn = get_conn()

    def _scalar(sql: str, *params) -> int:
        try:
            return int(conn.execute(sql, params).fetchone()[0])
        except Exception:
            return 0

    invites_by_status = {}
    for row in conn.execute(
            "SELECT status, COUNT(*) n FROM interview_invites GROUP BY status"):
        invites_by_status[row["status"]] = row["n"]
    trust_alerts = [dict(r) for r in conn.execute(
        "SELECT id, company_name, company_domain, trust_score, trust_level "
        "FROM employers WHERE trust_level = 'low' AND warm_intro_by IS NULL "
        "ORDER BY id DESC LIMIT 20")]
    return {
        "career_twins": _scalar("SELECT COUNT(*) FROM career_twins"),
        "twins_opted_in": _scalar(
            "SELECT COUNT(*) FROM career_twins WHERE recruiter_visibility = 1"),
        "employers": _scalar("SELECT COUNT(*) FROM employers"),
        "employers_vouched": _scalar(
            "SELECT COUNT(*) FROM employers WHERE warm_intro_by IS NOT NULL"),
        "roles_open": _scalar(
            "SELECT COUNT(*) FROM employer_roles WHERE status = 'open'"),
        "roles_hired": _scalar(
            "SELECT COUNT(*) FROM employer_roles WHERE status = 'hired'"),
        "invites": invites_by_status,
        "unlocks_total": _scalar("SELECT COUNT(*) FROM candidate_unlocks"),
        "credits_purchased": _scalar(
            "SELECT COALESCE(SUM(delta), 0) FROM employer_credit_ledger "
            "WHERE reason = 'purchase'"),
        "jobs_ingested_today": _scalar(
            "SELECT COUNT(*) FROM ingested_jobs "
            "WHERE fetched_at >= datetime('now', '-1 days')"),
        "applications": _scalar("SELECT COUNT(*) FROM applications"),
        "generations_last_30d": _scalar(
            "SELECT COUNT(*) FROM generation_log "
            "WHERE created_at >= datetime('now', '-30 days')"),
        "trust_alerts": trust_alerts,
    }


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


@app.get("/saved-jobs")
def list_saved(user_id: str = Depends(auth)):
    """The user's bookmarked jobs, newest first, with job detail."""
    return {"saved": db.list_saved_jobs(get_conn(), user_id)}


@app.put("/saved-jobs/{job_id}")
def save_job_endpoint(job_id: int, user_id: str = Depends(auth)):
    """Bookmark an ingested job. Idempotent; 404 for a job that doesn't exist."""
    if not db.save_job(get_conn(), user_id, job_id):
        raise HTTPException(status_code=404, detail="job not found")
    return {"ok": True, "saved": True}


@app.delete("/saved-jobs/{job_id}")
def unsave_job_endpoint(job_id: int, user_id: str = Depends(auth)):
    """Remove a bookmark. 404 when it wasn't saved."""
    if not db.unsave_job(get_conn(), user_id, job_id):
        raise HTTPException(status_code=404, detail="not saved")
    return {"ok": True, "saved": False}


@app.get("/matches")
def get_user_matches(limit: int = 20, offset: int = 0, user_id: str = Depends(rate_limit)):
    """Return the user's pre-computed match rankings (populated by the matching
    worker). Returns empty list if the worker hasn't run yet."""
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=422, detail="limit must be 1–200")
    conn = get_conn()
    return {
        "matches": db.list_matches(conn, user_id, limit=limit, offset=offset),
        "total": db.count_matches(conn, user_id),
        "limit": limit,
        "offset": offset,
    }


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
def admin_seed_sources(sync: bool = False, user_id: str = Depends(auth)):
    """Seed job_sources from data/job_sources.json.

    `?sync=true` adds any new file-declared sources to an already-seeded DB
    (INSERT OR IGNORE — existing rows, including manual toggles, untouched).
    This is how new sources committed to the repo reach prod without a DB reset.
    """
    conn = get_conn()
    inserted = db.seed_job_sources(conn, SOURCES_PATH, sync=sync)
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


@app.post("/admin/run/expire-invites")
def admin_run_expire_invites(_: None = Depends(admin_key_auth)):
    """Worker 6 — flip pending interview invites past their expiry to
    'expired'. Fast single UPDATE; stays synchronous."""
    result = expire_invites_worker.run(DB_PATH)
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


# ---------------------------------------------------------------------------
# Diagnostics — one call that reports whether every ops-critical piece of
# configuration is present in the running process and shows the most recent
# activity from every worker. Purpose: verify the launch-blocker checklist
# from a terminal without ssh'ing into Render (`curl -H X-API-Key: … …/admin/
# diagnostics | jq`). Never returns a secret value — only booleans for
# "configured", so it's safe to pipe into a status page.
# ---------------------------------------------------------------------------

_WORKER_EVENT_TYPES = (
    "JobIngestionRun", "MatchingWorkerRun", "VerificationWorkerRun",
    "NotifyWorkerRun", "BackupWorkerRun", "ExpireInvitesRun",
)


@app.get("/admin/diagnostics")
def admin_diagnostics(_: None = Depends(admin_key_auth)):
    """Return the state of every launch-blocker piece of configuration plus a
    snapshot of recent activity. Does NOT emit any secret values (only booleans
    for "configured") so this response is safe to log or forward to a status
    page."""
    conn = get_conn()

    # --- configuration presence (env-var booleans only, never the value) ----
    config = {
        "emploi_api_key": bool(API_KEY),
        "gemini": {
            "api_key": bool(os.getenv("GEMINI_API_KEY", "")),
            "model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        },
        "groq": {
            "api_key": bool(os.getenv("GROQ_API_KEY", "")),
            "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        },
        "brevo": {
            "api_key": bool(os.getenv("BREVO_API_KEY", "")),
            "sender_email": bool(os.getenv("BREVO_SENDER_EMAIL", "")),
        },
        "paystack": {
            "secret_key": bool(PAYSTACK_SECRET_KEY),
            "pro_plan_code": bool(PAYSTACK_PLAN_CODES.get("pro")),
            "max_plan_code": bool(PAYSTACK_PLAN_CODES.get("max")),
        },
        "r2_backup": {
            "endpoint": bool(os.getenv("R2_ENDPOINT", "")),
            "access_key": bool(os.getenv("R2_ACCESS_KEY", "")),
            "secret_key": bool(os.getenv("R2_SECRET_KEY", "")),
            "bucket": bool(os.getenv("R2_BUCKET", "")),
        },
        "web_app_url": WEB_APP_URL,
    }

    # --- launch-blocker rollup — a flat list of what's still open -----------
    open_items: list[str] = []
    if not config["emploi_api_key"]:
        open_items.append("EMPLOI_API_KEY unset — API is in OPEN DEV MODE (any X-User-Id impersonates any user)")
    if not config["gemini"]["api_key"]:
        open_items.append("GEMINI_API_KEY unset — AI features return 503")
    if not config["groq"]["api_key"]:
        open_items.append("GROQ_API_KEY unset — no provider fallback; every Gemini hiccup is user-visible")
    if not config["brevo"]["api_key"] or not config["brevo"]["sender_email"]:
        open_items.append("BREVO_API_KEY / BREVO_SENDER_EMAIL incomplete — digest emails will not send")
    paystack_ok = all(config["paystack"].values())
    if not paystack_ok:
        open_items.append("Paystack config incomplete — upgrade buttons will fail")
    r2_ok = all(config["r2_backup"].values())
    if not r2_ok:
        open_items.append("R2 backup env vars incomplete — nightly backup will not upload; disk incident = data loss")

    # --- last-run-per-worker from the events table --------------------------
    last_runs: dict = {}
    for event_type in _WORKER_EVENT_TYPES:
        row = conn.execute(
            "SELECT created_at, payload FROM events WHERE type = ? "
            "ORDER BY id DESC LIMIT 1", (event_type,)).fetchone()
        if not row:
            last_runs[event_type] = None
            continue
        try:
            payload = json.loads(row["payload"] or "{}")
        except Exception:
            payload = {}
        # Keep the summary compact — only ok/error-ish fields, no huge lists
        summary = {k: v for k, v in payload.items()
                   if k in ("ok", "fetched", "written", "total_matches",
                            "verified", "candidates", "sent", "errors",
                            "sender_configured", "send_failures", "sources_processed",
                            "backed_up", "dry_run")}
        last_runs[event_type] = {"at": row["created_at"], "summary": summary}

    # --- DB scale snapshot ---------------------------------------------------
    def _scalar(sql: str) -> int:
        try:
            return int(conn.execute(sql).fetchone()[0])
        except Exception:
            return 0

    counts = {
        "career_twins": _scalar("SELECT COUNT(*) FROM career_twins"),
        "applications": _scalar("SELECT COUNT(*) FROM applications"),
        "ingested_jobs": _scalar("SELECT COUNT(*) FROM ingested_jobs"),
        "matches": _scalar("SELECT COUNT(*) FROM matches"),
        "matches_unnotified": _scalar("SELECT COUNT(*) FROM matches WHERE notified = 0"),
        "subscriptions_paid": _scalar("SELECT COUNT(*) FROM subscriptions WHERE tier IN ('pro','max')"),
        "job_sources_active": _scalar("SELECT COUNT(*) FROM job_sources WHERE active = 1"),
        "job_sources_inactive": _scalar("SELECT COUNT(*) FROM job_sources WHERE active = 0"),
        "generations_last_30d": _scalar(
            "SELECT COUNT(*) FROM generation_log "
            "WHERE created_at >= datetime('now', '-30 days')"),
    }

    ready = (config["emploi_api_key"] and config["gemini"]["api_key"]
             and paystack_ok and r2_ok
             and config["brevo"]["api_key"] and config["brevo"]["sender_email"])

    return {
        "ready_for_launch": ready,
        "open_items": open_items,
        "config": config,
        "last_worker_runs": last_runs,
        "counts": counts,
    }
