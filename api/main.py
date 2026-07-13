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

from fastapi import Depends, FastAPI, Header, HTTPException, UploadFile, File
from pydantic import BaseModel, Field

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core  # noqa: E402
import db  # noqa: E402
import verify  # noqa: E402

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
def career_twin_extract(body: ResumeIn, user_id: str = Depends(auth)):
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
    user_id: str = Depends(auth),
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
def verify_endpoint(body: VerifyIn, user_id: str = Depends(auth)):
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
def matches_endpoint(body: MatchIn, user_id: str = Depends(auth)):
    """Rank jobs against the stored profile (Gemini)."""
    model = require_model()
    profile = db.load_career_twin(get_conn(), user_id)
    if not profile:
        raise HTTPException(status_code=409,
                            detail="no Career Twin yet — complete setup first")
    if not body.jobs:
        raise HTTPException(status_code=422, detail="no jobs provided")
    return {"matches": run_extraction(core.match_jobs, model, profile, body.jobs)}


@app.delete("/user")
def delete_user(user_id: str = Depends(auth)):
    """NDPA/GDPR deletion right — removes everything stored for the user."""
    db.clear_user(get_conn(), user_id)
    return {"ok": True}
