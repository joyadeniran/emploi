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
import os
import sys
import logging

from fastapi import Depends, FastAPI, Header, HTTPException
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
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="invalid API key")
    if not x_user_id:
        raise HTTPException(status_code=401, detail="missing X-User-Id")
    return x_user_id


app = FastAPI(title="Emploi API", version="1.0.0")
app.state.model_factory = get_model


# ---------------- schemas ----------------
class ProfileIn(BaseModel):
    profile: dict


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


@app.get("/profile")
def get_profile(user_id: str = Depends(auth)):
    return {"profile": db.load_profile(get_conn(), user_id)}


@app.put("/profile")
def put_profile(body: ProfileIn, user_id: str = Depends(auth)):
    db.save_profile(get_conn(), user_id, body.profile)
    return {"ok": True}


@app.post("/resume/extract")
def resume_extract(body: ResumeIn, user_id: str = Depends(auth)):
    """CV text -> structured profile (Gemini), persisted for the user."""
    model = require_model()
    profile = core.extract_profile(model, body.cv_text)
    if not profile:
        raise HTTPException(status_code=422,
                            detail="could not extract a profile from that text")
    db.save_profile(get_conn(), user_id, profile)
    return {"profile": profile}


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
    profile = db.load_profile(get_conn(), user_id)
    if not profile:
        raise HTTPException(status_code=409,
                            detail="no profile yet — upload a CV first")
    if not body.jobs:
        raise HTTPException(status_code=422, detail="no jobs provided")
    return {"matches": core.match_jobs(model, profile, body.jobs)}


@app.delete("/user")
def delete_user(user_id: str = Depends(auth)):
    """NDPA/GDPR deletion right — removes everything stored for the user."""
    db.clear_user(get_conn(), user_id)
    return {"ok": True}
