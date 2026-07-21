"""Offline checks for the FastAPI service (api/main.py).

No network, no API key, no Gemini: DNS/MX/site probes are patched at the
module seam (api.main.dns_fn etc.), the model factory is swapped for a fake,
and the database is in-memory. Same check() style as the other suites.
"""
import os
import sys

os.environ["EMPLOI_API_KEY"] = "test-key"
os.environ["EMPLOI_DB_PATH"] = ":memory:"
os.environ.pop("GEMINI_API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

import api.main as m  # noqa: E402

FAILURES = []


def check(label, cond):
    status = "PASS" if cond else "FAIL"
    print(f"{status} - {label}")
    if not cond:
        FAILURES.append(label)


AUTH = {"X-API-Key": "test-key", "X-User-Id": "user-1"}
client = TestClient(m.app)

# ---------------- health & auth ----------------
r = client.get("/health")
check("health returns ok", r.status_code == 200 and r.json()["ok"] is True)
check("health reports ai unavailable without key", r.json()["ai"] is False)
check("health reports auth enabled", r.json()["auth"] is True)

check("missing api key -> 401",
      client.get("/career-twin", headers={"X-User-Id": "u"}).status_code == 401)
check("wrong api key -> 401",
      client.get("/career-twin", headers={"X-API-Key": "nope", "X-User-Id": "u"}).status_code == 401)
check("missing user id -> 401",
      client.get("/career-twin", headers={"X-API-Key": "test-key"}).status_code == 401)

# ---------------- career twin round-trip ----------------
check("empty career twin initially",
      client.get("/career-twin", headers=AUTH).json()["career_twin"] == {})

r = client.patch("/career-twin", headers=AUTH,
                 json={"data": {"name": "Ada", "skills": "Python"}})
check("career twin patch ok", r.status_code == 200)
check("career twin round-trip",
      client.get("/career-twin", headers=AUTH).json()["career_twin"]["name"] == "Ada")
check("career twin is per-user",
      client.get("/career-twin", headers={**AUTH, "X-User-Id": "user-2"}).json()["career_twin"] == {})

# patch merges, not replaces
r = client.patch("/career-twin", headers=AUTH, json={"data": {"headline": "PM"}})
ct = client.get("/career-twin", headers=AUTH).json()["career_twin"]
check("patch merges fields (name retained after headline patch)",
      ct["name"] == "Ada" and ct["headline"] == "PM")

# complete endpoint marks onboarding done
r = client.post("/career-twin/complete", headers=AUTH)
check("career twin complete ok", r.status_code == 200)
ct = client.get("/career-twin", headers=AUTH).json()["career_twin"]
check("onboarding_complete flag set", ct.get("onboarding_complete") is True)

# ---------------- AI endpoints degrade without a key ----------------
r = client.post("/career-twin/extract", headers=AUTH, json={"cv_text": "x" * 60})
check("extract without key -> 503 with clear message",
      r.status_code == 503 and "GEMINI_API_KEY" in r.json()["detail"])
r = client.post("/matches", headers=AUTH, json={"jobs": [{"title": "PM"}]})
check("matches without key -> 503", r.status_code == 503)


# ---------------- career-twin/extract with a fake model ----------------
class FakeModel:
    def __init__(self, text):
        self._text = text

    def generate_content(self, prompt):
        class R:
            pass
        r = R()
        r.text = self._text
        return r


m.app.state.model_factory = lambda: FakeModel(
    '```json\n{"name": "Ada Obi", "headline": "Data Analyst", '
    '"current_role": "Analyst at Flutterwave", "experience_years": 4, '
    '"skills": "Python, SQL", "location": "Abuja", "bio": "Data analyst."}\n```')
r = client.post("/career-twin/extract", headers=AUTH, json={"cv_text": "x" * 60})
tw = r.json()["career_twin"]
check("extract parses fenced JSON", tw["name"] == "Ada Obi")
check("extract returns wizard schema (headline)", tw["headline"] == "Data Analyst")
check("extract returns wizard schema (current_role)",
      tw["current_role"] == "Analyst at Flutterwave")
check("skills normalized: comma string -> list",
      tw["skills"] == ["Python", "SQL"])
check("experience_years normalized to wizard bucket",
      tw["experience_years"] == "4 years")
check("extracted data persisted",
      client.get("/career-twin", headers=AUTH).json()["career_twin"]["name"] == "Ada Obi")

m.app.state.model_factory = lambda: FakeModel("this is not json at all")
r = client.post("/career-twin/extract", headers=AUTH, json={"cv_text": "x" * 60})
check("garbage model output -> 422, never a crash", r.status_code == 422)

check("short cv text rejected by validation",
      client.post("/career-twin/extract", headers=AUTH,
                  json={"cv_text": "short"}).status_code == 422)

# legacy /resume/extract alias still works
m.app.state.model_factory = lambda: FakeModel(
    '```json\n{"name": "Legacy Ada"}\n```')
r = client.post("/resume/extract", headers=AUTH, json={"cv_text": "x" * 60})
check("legacy /resume/extract alias still responds 200", r.status_code == 200)


# ---------------- provider-failure and payload guards ----------------
class RaisingModel:
    def generate_content(self, prompt):
        raise RuntimeError("simulated Gemini outage / rate limit")


m.app.state.model_factory = lambda: RaisingModel()
r = client.post("/career-twin/extract", headers=AUTH, json={"cv_text": "x" * 60})
check("model exception -> clean 502, never a raw 500",
      r.status_code == 502 and "temporarily unavailable" in r.json()["detail"])
r = client.post("/matches", headers=AUTH, json={"jobs": [{"title": "PM"}]})
check("matches with failing model -> 502 (twin exists from earlier test)",
      r.status_code == 502)

r = client.patch("/career-twin", headers=AUTH,
                 json={"data": {"blob": "x" * 70_000}})
check("oversized career-twin PATCH -> 413", r.status_code == 413)

# upload cap: shrink the module bound so the test stays fast
_orig_max = m.MAX_UPLOAD_BYTES
m.MAX_UPLOAD_BYTES = 100
m.app.state.model_factory = lambda: FakeModel('{"name": "X"}')
r = client.post("/career-twin/upload", headers=AUTH,
                files={"file": ("cv.pdf", b"%PDF" + b"x" * 200, "application/pdf")})
check("oversized upload -> 413", r.status_code == 413)
m.MAX_UPLOAD_BYTES = _orig_max

# ---------------- deterministic trust verification ----------------
m.app.state.model_factory = lambda: None
m.dns_fn = lambda d: True
m.mx_fn = lambda d: True
m.fetch_fn = lambda d, timeout=6: (200, "Acme Corp official website careers")
m._verify_cache.clear()

r = client.post("/verify", headers=AUTH, json={
    "company": "Acme Corp", "contact": "jobs@acmecorp.com",
    "job_text": "Software engineer role, standard salary."})
good = r.json()
check("legit employer verifies", r.status_code == 200)
check("legit employer scores high", good["score"] >= 70)
check("evidence is named", isinstance(good["evidence"], list) and len(good["evidence"]) > 0)

r = client.post("/verify", headers=AUTH, json={
    "company": "Quick Cash Jobs", "contact": "quickcash@gmail.com",
    "job_text": "Pay a registration fee to start. No experience, high pay!"})
bad = r.json()
check("scam pattern capped at 35 (red-flag cap intact)", bad["score"] <= 35)
check("scam scores far below legit", bad["score"] < good["score"])

calls = {"n": 0}


def counting_dns(d):
    calls["n"] += 1
    return True


m.dns_fn = counting_dns
m._verify_cache.clear()
client.post("/verify", headers=AUTH,
            json={"company": "Acme", "contact": "a@acmecorp.com"})
client.post("/verify", headers=AUTH,
            json={"company": "Acme", "contact": "b@acmecorp.com"})
check("verification cached per domain (one probe)", calls["n"] == 1)

check("verify with no company/contact -> 422",
      client.post("/verify", headers=AUTH, json={}).status_code == 422)

# Isolate this probe-heavy guard from the checks above. The eleventh request
# from one user must fail cleanly instead of consuming unlimited DNS/HTTP work.
m._rate_counters.clear()
RATE_AUTH = {**AUTH, "X-User-Id": "rate-limit-user"}
for _ in range(10):
    client.post("/verify", headers=RATE_AUTH,
                json={"company": "Rate Test", "contact": "jobs@ratetest.com"})
r = client.post("/verify", headers=RATE_AUTH,
                json={"company": "Rate Test", "contact": "jobs@ratetest.com"})
check("verify rate limit returns 429 after 10 requests", r.status_code == 429)

# ---------------- applications CRUD ----------------
r = client.post("/applications", headers=AUTH, json={
    "company": "Paystack", "role": "Senior PM", "status": "applied",
    "extra": {"fit_score": 92}})
check("application created", r.status_code == 201)
app_id = r.json()["id"]

rows = client.get("/applications", headers=AUTH).json()["applications"]
check("application listed with extra fields",
      rows[0]["company"] == "Paystack" and rows[0]["fit_score"] == 92)

check("invalid status rejected",
      client.post("/applications", headers=AUTH,
                  json={"company": "X", "role": "Y",
                        "status": "not-a-real-status"}).status_code == 422)

# Outcome loop: `ghosted` and `heard_back` are first-class statuses now.
check("ghosted is a valid status (outcome loop)",
      client.post("/applications", headers=AUTH,
                  json={"company": "X", "role": "Y",
                        "status": "ghosted"}).status_code == 201)
check("heard_back is a valid status (outcome loop)",
      client.post("/applications", headers=AUTH,
                  json={"company": "Y", "role": "Z",
                        "status": "heard_back"}).status_code == 201)

r = client.patch(f"/applications/{app_id}", headers=AUTH,
                 json={"status": "interview"})
check("status transition applied -> interview", r.status_code == 200)
rows = client.get("/applications", headers=AUTH).json()["applications"]
# rows are newest-first; find the Paystack row explicitly.
paystack = [r for r in rows if r["id"] == app_id][0]
check("transition persisted", paystack["status"] == "interview")
check("outcome_updated_at set on status change",
      paystack.get("outcome_updated_at") is not None)

# PATCH now also accepts optional outcome_notes; old callers that only send
# status keep working unchanged.
r = client.patch(f"/applications/{app_id}", headers=AUTH,
                 json={"status": "offer",
                       "outcome_notes": "verbal, waiting on written"})
check("PATCH accepts optional outcome_notes", r.status_code == 200)
rows = client.get("/applications", headers=AUTH).json()["applications"]
paystack = [r for r in rows if r["id"] == app_id][0]
check("outcome_notes persist through PATCH",
      paystack.get("outcome_notes") == "verbal, waiting on written")

check("cannot patch another user's application",
      client.patch(f"/applications/{app_id}",
                   headers={**AUTH, "X-User-Id": "user-2"},
                   json={"status": "offer"}).status_code == 404)
check("invalid transition status rejected",
      client.patch(f"/applications/{app_id}", headers=AUTH,
                   json={"status": "nope"}).status_code == 422)

# ---------------- job sourcing: GET /jobs + GET /matches ----------------
# Seed a job directly via db so we can test the read endpoints without running the worker
import db as _db
_conn = m.get_conn()
_db.upsert_job(_conn, "greenhouse/test", "api-test-1",
               {"title": "API Test Engineer", "company_name": "TestCo",
                "is_remote": True, "category": "Engineering"})
_db.upsert_job(_conn, "lever/test", "api-test-2",
               {"title": "Designer", "company_name": "TestCo",
                "is_remote": False, "category": "Design"})

r = client.get("/jobs", headers=AUTH)
check("GET /jobs returns job list", r.status_code == 200 and "jobs" in r.json())
check("GET /jobs returns total count", r.json()["total"] >= 2)

r = client.get("/jobs?remote_only=true", headers=AUTH)
check("GET /jobs?remote_only filters", all(j["is_remote"] for j in r.json()["jobs"]))

r = client.get("/jobs?category=Engineering", headers=AUTH)
check("GET /jobs?category filters", all(j["category"] == "Engineering"
                                        for j in r.json()["jobs"]))

r = client.get("/jobs?q=designer", headers=AUTH)
check("GET /jobs?q= free-text search matches title case-insensitively",
      r.json()["total"] >= 1 and all("design" in (j["title"] or "").lower()
                                     or "design" in (j["company_name"] or "").lower()
                                     or "design" in (j["description"] or "").lower()
                                     for j in r.json()["jobs"]))
check("GET /jobs?q= no hits -> empty, not error",
      client.get("/jobs?q=zzz-no-such-job-zzz", headers=AUTH).json()["total"] == 0)
check("GET /jobs?q=%25 wildcard is escaped (no match-everything)",
      client.get("/jobs?q=%25", headers=AUTH).json()["total"] == 0)

job_id = r.json()["jobs"][0]["id"]
r = client.get(f"/jobs/{job_id}", headers=AUTH)
check("GET /jobs/{id} returns single job", r.status_code == 200
      and r.json()["job"]["id"] == job_id)
check("GET /jobs/99999 → 404", client.get("/jobs/99999", headers=AUTH).status_code == 404)

r = client.get("/jobs?limit=300", headers=AUTH)
check("GET /jobs limit > 200 → 422", r.status_code == 422)

# Matches: empty until worker populates; endpoint must still return 200
r = client.get("/matches", headers=AUTH)
check("GET /matches returns 200 + empty list for new user",
      r.status_code == 200 and r.json()["matches"] == [])

# Seed a match and verify it comes back
_db.upsert_match(_conn, AUTH["X-User-Id"], job_id, 88, "Strong fit")
r = client.get("/matches", headers=AUTH)
check("GET /matches returns seeded match",
      len(r.json()["matches"]) == 1 and r.json()["matches"][0]["fit_score"] == 88)

# ---------------- application generation (sync path, background=false) ----------------
m.app.state.model_factory = lambda: None
r = client.post("/applications/generate?background=false", headers=AUTH,
                json={"job": {"company_name": "TestCo", "description": "Build products"}})
check("generation without key -> 503", r.status_code == 503)

m.app.state.model_factory = lambda: FakeModel("Dear TestCo,\n\nFit Score: 85/100")
r = client.post("/applications/generate?background=false", headers=AUTH,
                json={"job": {"company_name": "TestCo", "description": "Build products"},
                      "include_review": False})
generated = r.json().get("generated", {})
check("generation (sync) returns application and fit score",
      r.status_code == 200 and generated.get("fit_score") == 85 and generated.get("result"))
check("generation rejects a job without description",
      client.post("/applications/generate", headers=AUTH, json={"job": {"company": "TestCo"}}).status_code == 422)
check("generation requires Career Twin",
      client.post("/applications/generate", headers={**AUTH, "X-User-Id": "no-twin"},
                  json={"job": {"description": "Build products"}}).status_code == 409)

# ---------------- application generation (async path, default) ----------------
import time as _time

m.app.state.model_factory = lambda: FakeModel("Dear TestCo,\n\nFit Score: 77/100")
r = client.post("/applications/generate", headers=AUTH,
                json={"job": {"company_name": "TestCo", "description": "Build products"},
                      "include_review": False})
check("generation (async) submit returns 202 with a job_id",
      r.status_code == 202 and r.json().get("status") == "pending" and r.json().get("job_id"))
gen_job_id = r.json()["job_id"]

for _ in range(50):
    poll = client.get(f"/applications/generate/{gen_job_id}", headers=AUTH)
    if poll.json().get("status") != "pending":
        break
    _time.sleep(0.05)
check("generation (async) job reaches done", poll.json().get("status") == "done")
check("generation (async) result matches sync contract",
      poll.json()["generated"]["fit_score"] == 77)

check("generation job lookup requires auth", client.get(f"/applications/generate/{gen_job_id}").status_code == 401)
check("generation job is per-user (404 for someone else)",
      client.get(f"/applications/generate/{gen_job_id}",
                headers={**AUTH, "X-User-Id": "someone-else"}).status_code == 404)
check("unknown generation job -> 404",
      client.get("/applications/generate/not-a-real-id", headers=AUTH).status_code == 404)

# A provider failure surfaces as a job error, never an unhandled exception
class _AlwaysFails:
    def generate_content(self, prompt):
        raise RuntimeError("simulated provider outage")

m.app.state.model_factory = lambda: _AlwaysFails()
r = client.post("/applications/generate", headers=AUTH,
                json={"job": {"company_name": "TestCo", "description": "Build products"}})
gen_job_id = r.json()["job_id"]
for _ in range(50):
    poll = client.get(f"/applications/generate/{gen_job_id}", headers=AUTH)
    if poll.json().get("status") != "pending":
        break
    _time.sleep(0.05)
check("generation (async) provider failure surfaces as a job error, not a crash",
      poll.json().get("status") == "error" and "unavailable" in poll.json().get("error", ""))

# ---------------- tailored CV generation ----------------
# The artifact users actually send, distinct from the draft's "CV bullets".
m.app.state.model_factory = lambda: None
check("cv generation without key -> 503",
      client.post("/applications/cv?background=false", headers=AUTH,
                  json={"job": {"description": "Build products"}}).status_code == 503)

_CV_MD = "# Ada Lovelace\n## Professional Summary\nBuilt payment rails.\n## Experience\n- Shipped X"
m.app.state.model_factory = lambda: FakeModel(_CV_MD)
r = client.post("/applications/cv?background=false", headers=AUTH,
                json={"job": {"company_name": "TestCo", "description": "Build products"}})
check("cv generation (sync) returns a complete CV",
      r.status_code == 200 and "Professional Summary" in r.json()["generated"]["cv"])
check("cv generation rejects a job without description",
      client.post("/applications/cv", headers=AUTH,
                  json={"job": {"company": "TestCo"}}).status_code == 422)
check("cv generation requires Career Twin",
      client.post("/applications/cv", headers={**AUTH, "X-User-Id": "no-twin"},
                  json={"job": {"description": "Build products"}}).status_code == 409)

r = client.post("/applications/cv", headers=AUTH,
                json={"job": {"company_name": "TestCo", "description": "Build products"}})
check("cv generation (async) submit returns 202 with a job_id",
      r.status_code == 202 and r.json().get("job_id"))
cv_job_id = r.json()["job_id"]
for _ in range(50):
    poll = client.get(f"/applications/generate/{cv_job_id}", headers=AUTH)
    if poll.json().get("status") != "pending":
        break
    _time.sleep(0.05)
check("cv job polls through the shared generation job endpoint",
      poll.json().get("status") == "done" and "Professional Summary" in poll.json()["generated"]["cv"])
check("cv job is per-user (404 for someone else)",
      client.get(f"/applications/generate/{cv_job_id}",
                 headers={**AUTH, "X-User-Id": "someone-else"}).status_code == 404)

# ---------------- document export (pdf / docx) ----------------
# Pure rendering: no model call, nothing persisted.
r = client.post("/applications/export", headers=AUTH,
                json={"text": "# Ada\n\nDear TestCo,\n\n- Shipped X", "format": "pdf",
                      "title": "Cover Letter — TestCo"})
check("export pdf returns a real PDF body",
      r.status_code == 200 and r.content[:4] == b"%PDF"
      and r.headers["content-type"] == "application/pdf")
check("export pdf sets a safe attachment filename",
      "attachment;" in r.headers["content-disposition"]
      and "cover-letter-testco.pdf" in r.headers["content-disposition"])

r = client.post("/applications/export", headers=AUTH,
                json={"text": "# Ada\n\n- Shipped X", "format": "docx", "title": "CV — TestCo"})
check("export docx returns a real DOCX body (zip magic)",
      r.status_code == 200 and r.content[:2] == b"PK"
      and "wordprocessingml" in r.headers["content-type"])

check("export rejects an unknown format",
      client.post("/applications/export", headers=AUTH,
                  json={"text": "hi", "format": "exe"}).status_code == 422)
check("export rejects empty text",
      client.post("/applications/export", headers=AUTH,
                  json={"text": "   ", "format": "pdf"}).status_code == 422)
check("export rejects an oversized document -> 413",
      client.post("/applications/export", headers=AUTH,
                  json={"text": "x" * (m.MAX_EXPORT_BYTES + 1), "format": "pdf"}).status_code == 413)
check("export requires auth",
      client.post("/applications/export", json={"text": "hi", "format": "pdf"}).status_code == 401)

# The evaluation is the candidate's own gap analysis. Stripping it is enforced
# SERVER-SIDE, not trusted to the caller — a client bug must not be able to put
# it in a file the candidate sends to an employer.
_BLOB = ("## Cover Letter\nDear TestCo, I ship payment rails.\n\n"
         "## CV Bullet Points\n- Shipped X, cutting latency 40%\n\n"
         "## Fit Evaluation\nBiggest gaps: no Kafka experience.\nFit Score: 88/100")
r = client.post("/applications/export", headers=AUTH,
                json={"text": _BLOB, "format": "pdf", "title": "Cover Letter"})
_pdf_text = m.core.pdf_to_text(r.content)
check("export strips the evaluation server-side even if a caller sends the whole blob",
      r.status_code == 200 and "Fit Score" not in _pdf_text
      and "Biggest gaps" not in _pdf_text)
check("export keeps the sendable content when stripping the evaluation",
      "Dear TestCo" in _pdf_text and "Shipped X" in _pdf_text)
check("export strips the '## Fit Score' header variant too",
      "60/100" not in m.core.pdf_to_text(
          client.post("/applications/export", headers=AUTH,
                      json={"text": "## Cover Letter\nHi.\n\n## Fit Score\nFit Score: 60/100",
                            "format": "pdf"}).content))
check("a body that is ONLY an evaluation exports nothing -> 422",
      client.post("/applications/export", headers=AUTH,
                  json={"text": "## Fit Evaluation\nFit Score: 88/100", "format": "pdf"}
                  ).status_code == 422)
# User text must never steer the Content-Disposition header.
r = client.post("/applications/export", headers=AUTH,
                json={"text": "hi", "format": "pdf", "title": '../../etc "evil"\n'})
_cd = r.headers["content-disposition"]
check("export slug strips path/quote/newline injection from the filename",
      r.status_code == 200 and 'filename="etc-evil.pdf"' in _cd
      and '"' not in _cd.split("filename=")[1][1:-1]
      and "/" not in _cd and "\n" not in _cd)
check("export slug falls back when a title has no usable characters",
      'filename="emploi-application.pdf"' in
      client.post("/applications/export", headers=AUTH,
                  json={"text": "hi", "format": "pdf", "title": "///"}
                  ).headers["content-disposition"])

# ---------------- Career Twin chat ----------------
m.app.state.model_factory = lambda: None
r = client.post("/chat", headers=AUTH, json={"message": "hi"})
check("chat without key -> 503", r.status_code == 503)

CHAT_JSON = ('{"reply": "Senior marketing roles suit your brand-building record.",'
             ' "profile_updates": {"goals": "Senior marketing roles", "skills": "Media Buying"}}')
m.app.state.model_factory = lambda: FakeModel(CHAT_JSON)
r = client.post("/chat", headers=AUTH,
                json={"message": "I want senior marketing roles",
                      "history": [{"role": "user", "content": "earlier"},
                                  {"role": "assistant", "content": "earlier reply"}]})
check("chat returns reply", r.status_code == 200 and "Senior marketing" in r.json()["reply"])
check("chat reports profile updates", "goals" in r.json()["profile_updates"])
tw = client.get("/career-twin", headers=AUTH).json()["career_twin"]
check("chat goal appended to career_goals list",
      isinstance(tw.get("career_goals"), list) and "Senior marketing roles" in tw["career_goals"])
check("chat skill merged into skills list",
      isinstance(tw.get("skills"), list) and "Media Buying" in tw["skills"])
check("chat requires a Career Twin",
      client.post("/chat", headers={**AUTH, "X-User-Id": "chat-no-twin"},
                  json={"message": "hi"}).status_code == 409)
check("chat rejects empty message",
      client.post("/chat", headers=AUTH, json={"message": ""}).status_code == 422)

# Plain-text fallback: model ignores the JSON contract -> raw reply, no updates
m.app.state.model_factory = lambda: FakeModel("plain text, no JSON here")
r = client.post("/chat", headers=AUTH, json={"message": "hello again"})
check("chat plain-text fallback returns raw reply",
      r.status_code == 200 and r.json()["reply"].startswith("plain text")
      and r.json()["profile_updates"] == {})

# ---------------- saved jobs ----------------
check("saved jobs starts empty",
      client.get("/saved-jobs", headers=AUTH).json()["saved"] == [])
r = client.put(f"/saved-jobs/{job_id}", headers=AUTH)
check("save a job -> ok", r.status_code == 200 and r.json()["saved"] is True)
check("save is idempotent",
      client.put(f"/saved-jobs/{job_id}", headers=AUTH).status_code == 200)
saved = client.get("/saved-jobs", headers=AUTH).json()["saved"]
check("saved list has the job with detail joined",
      len(saved) == 1 and saved[0]["id"] == job_id and saved[0]["title"])
check("saved jobs are per-user",
      client.get("/saved-jobs", headers={**AUTH, "X-User-Id": "user-2"}).json()["saved"] == [])
check("saving a nonexistent job -> 404 (no dangling bookmark)",
      client.put("/saved-jobs/999999", headers=AUTH).status_code == 404)
check("unsave removes it",
      client.delete(f"/saved-jobs/{job_id}", headers=AUTH).status_code == 200
      and client.get("/saved-jobs", headers=AUTH).json()["saved"] == [])
check("unsave twice -> 404",
      client.delete(f"/saved-jobs/{job_id}", headers=AUTH).status_code == 404)
# re-save so the later DELETE /user check can prove erasure covers saved_jobs
client.put(f"/saved-jobs/{job_id}", headers=AUTH)

# ---------------- billing (Paystack) — defaults & quota gating ----------------
check("billing status defaults to free",
      client.get("/billing/status", headers=AUTH).json()["tier"] == "free")
status = client.get("/billing/status", headers=AUTH).json()
check("free tier limit is 10", status["limit"] == 10)
# 2 application drafts + 2 tailored CVs. A CV is a model call and counts
# against the same allowance; exports are pure rendering and never count.
check("used_this_month counts drafts AND tailored CVs (2 + 2), not exports",
      status["used_this_month"] == 4)

check("checkout without PAYSTACK_SECRET_KEY -> 503",
      client.post("/billing/checkout", headers=AUTH, json={"tier": "pro"}).status_code == 503)

m.PAYSTACK_SECRET_KEY = "sk_test_fake"
m.PAYSTACK_PLAN_CODES = {"pro": "PLN_pro", "max": "PLN_max"}

check("checkout rejects an unknown tier",
      client.post("/billing/checkout", headers=AUTH, json={"tier": "enterprise"}).status_code == 422)
check("checkout requires an email on the Career Twin",
      client.post("/billing/checkout", headers=AUTH, json={"tier": "pro"}).status_code == 422)

client.patch("/career-twin", headers=AUTH, json={"data": {"email": "ada@example.com"}})

init_calls = []
m.billing.initialize_transaction = lambda *a, **k: (init_calls.append((a, k)) or {
    "authorization_url": "https://checkout.paystack.com/xyz", "reference": "ref_abc"})
r = client.post("/billing/checkout", headers=AUTH, json={"tier": "pro"})
check("checkout returns Paystack's authorization_url",
      r.status_code == 200 and r.json()["authorization_url"] == "https://checkout.paystack.com/xyz")
check("checkout passes the plan code and price for the requested tier",
      init_calls[0][0][2] == 3500 and init_calls[0][0][3] == "PLN_pro")

m.billing.verify_transaction = lambda *a, **k: {
    "status": "success", "metadata": {"user_id": "user-1", "tier": "pro"},
    "customer": {"customer_code": "CUS_1", "email": "ada@example.com"}}
r = client.post("/billing/verify", headers=AUTH, json={"reference": "ref_abc"})
check("verify activates the tier", r.status_code == 200 and r.json()["tier"] == "pro")
status_after_verify = client.get("/billing/status", headers=AUTH).json()
check("billing status now reflects Pro with the raised limit",
      status_after_verify["tier"] == "pro" and status_after_verify["limit"] == 50)

check("verify rejects a transaction for a different user's metadata",
      client.post("/billing/verify", headers={**AUTH, "X-User-Id": "someone-else"},
                  json={"reference": "ref_abc"}).status_code == 404)

check("cancel with no known Paystack subscription code -> 409",
      client.post("/billing/cancel", headers=AUTH).status_code == 409)

# ---- webhook: signature required, then drives subscription lifecycle ----
import hmac as _hmac, hashlib as _hashlib, json as _json_lib

def _signed(body_dict):
    raw = _json_lib.dumps(body_dict).encode()
    sig = _hmac.new(m.PAYSTACK_SECRET_KEY.encode(), raw, _hashlib.sha512).hexdigest()
    return raw, sig

raw, sig = _signed({"event": "charge.success", "data": {}})
check("webhook rejects a missing/invalid signature",
      client.post("/billing/webhook", content=raw, headers={"x-paystack-signature": "bad"}).status_code == 401)

raw, sig = _signed({"event": "subscription.create",
                    "data": {"subscription_code": "SUB_123", "customer": {"customer_code": "CUS_1"}}})
r = client.post("/billing/webhook", content=raw, headers={"x-paystack-signature": sig})
check("webhook accepts a validly signed event", r.status_code == 200)
row = _conn.execute("SELECT paystack_subscription_code FROM subscriptions WHERE user_id = 'user-1'").fetchone()
check("subscription.create webhook records the subscription code", row["paystack_subscription_code"] == "SUB_123")

# Now cancel can actually reach Paystack (mocked) and succeed
m.billing.fetch_subscription = lambda *a, **k: {"email_token": "tok_1"}
disable_called = []
m.billing.disable_subscription = lambda *a, **k: disable_called.append(a)
r = client.post("/billing/cancel", headers=AUTH)
check("cancel succeeds once a subscription code is on file", r.status_code == 200)
check("cancel marks status cancelled (tier stays until Paystack confirms via webhook)",
      client.get("/billing/status", headers=AUTH).json()["tier"] == "pro")

raw, sig = _signed({"event": "subscription.disable", "data": {"subscription_code": "SUB_123"}})
client.post("/billing/webhook", content=raw, headers={"x-paystack-signature": sig})
check("subscription.disable webhook downgrades the user to free",
      client.get("/billing/status", headers=AUTH).json()["tier"] == "free")

raw, sig = _signed({"event": "invoice.payment_failed",
                    "data": {"subscription": {"subscription_code": "SUB_123"}}})
client.post("/billing/webhook", content=raw, headers={"x-paystack-signature": sig})
row = _conn.execute("SELECT status FROM subscriptions WHERE user_id = 'user-1'").fetchone()
check("invoice.payment_failed webhook marks the subscription past_due", row["status"] == "past_due")

# ---- quota gate: /applications/generate 402s once the tier's monthly cap is hit ----
_db.upsert_subscription(_conn, "quota-user", tier="free")
for _ in range(10):
    _db.log_generation(_conn, "quota-user")
_db.save_career_twin(_conn, "quota-user", {"name": "Cap Reached"})
m.app.state.model_factory = lambda: FakeModel("Dear TestCo,\n\nFit Score: 90/100")
r = client.post("/applications/generate?background=false",
                headers={**AUTH, "X-User-Id": "quota-user"},
                json={"job": {"description": "Build products"}})
check("generation is blocked with 402 once the monthly cap is reached",
      r.status_code == 402 and "10" in r.json()["detail"])

# ---------------- model fallback (Gemini primary, Groq secondary) ----------------
class _Boom:
    calls = 0
    def generate_content(self, prompt):
        _Boom.calls += 1
        raise RuntimeError("429 quota exhausted")

fallback_calls = []
class _Backup:
    def generate_content(self, prompt):
        fallback_calls.append(prompt)
        class R: text = "backup answer"
        return R()

fb = m.FallbackModel(_Boom(), _Backup())
check("fallback model rescues a failing primary",
      fb.generate_content("hello").text == "backup answer" and len(fallback_calls) == 1)
fb2 = m.FallbackModel(FakeModel("primary answer"), _Backup())
check("fallback never called when primary works",
      fb2.generate_content("hi").text == "primary answer" and len(fallback_calls) == 1)

# ---------------- chat attachments (PDF -> classify -> act) ----------------
class SeqModel:
    """Returns queued responses in order — classify, then extract, etc."""
    def __init__(self, texts):
        self._texts = list(texts)
    def generate_content(self, prompt):
        class R: pass
        r = R()
        r.text = self._texts.pop(0) if self._texts else "{}"
        return r

import core as _core
cv_pdf = _core.make_pdf("Jane Doe\nMarketing Manager\n8 years experience in brand building at Acme.")

# CV path: classify -> "CV", extraction -> twin JSON
m.app.state.model_factory = lambda: SeqModel([
    "CV",
    '{"name":"Jane Doe","headline":"Marketing Manager","skills":["Brand Building"],'
    '"experience":[{"summary":"MM at Acme"}]}'])
r = client.post("/chat/attach", headers=AUTH, files={"file": ("cv.pdf", cv_pdf, "application/pdf")})
check("chat attach: CV classified and merged", r.status_code == 200 and r.json()["kind"] == "cv")
tw = client.get("/career-twin", headers=AUTH).json()["career_twin"]
check("chat attach: CV merged into stored twin", tw.get("headline") == "Marketing Manager")

# JOBS path: classify -> JOBS, extract -> array, match -> scores
jobs_pdf = _core.make_pdf("Hiring: Growth Marketer at Acme. Remote. Apply at jobs@acme.com")
m.app.state.model_factory = lambda: SeqModel([
    "JOBS",
    '[{"company":"Acme","title":"Growth Marketer","description":"remote growth role"}]',
    '[{"index":0,"fit_score":88,"reason":"strong growth background"}]'])
r = client.post("/chat/attach", headers=AUTH, files={"file": ("jobs.pdf", jobs_pdf, "application/pdf")})
check("chat attach: job listing scored against twin",
      r.status_code == 200 and r.json()["kind"] == "jobs"
      and "88/100" in r.json()["reply"])

# OTHER path: honest no-op
m.app.state.model_factory = lambda: SeqModel(["OTHER"])
r = client.post("/chat/attach", headers=AUTH, files={"file": ("x.pdf", cv_pdf, "application/pdf")})
check("chat attach: unclassifiable document changes nothing",
      r.status_code == 200 and r.json()["kind"] == "other")

# ---------------- worker triggers (Render Cron -> HTTP, no disk on cron) ----------------
# Render Cron Jobs can't mount the persistent disk the SQLite file lives on,
# so scheduled workers run in-process here instead of as their own cron
# services; render.yaml's crons just curl these endpoints. Monkeypatch the
# imported worker modules' run() so this stays fully offline — no real
# network, no real Gemini calls, no real R2 upload.
import workers.ingest_jobs as _ingest_mod
import workers.match_users as _match_mod
import workers.verify_employers as _verify_mod
import workers.notify_users as _notify_mod
import workers.backup_db as _backup_mod

_orig_ingest_run = _ingest_mod.run
_orig_match_run = _match_mod.run
_orig_verify_run = _verify_mod.run
_orig_notify_run = _notify_mod.run
_orig_backup_run = _backup_mod.run

check("admin run without api key -> 401",
      client.post("/admin/run/ingest").status_code == 401)

_ingest_mod.run = lambda db_path, min_priority=1: {"ok": True, "min_priority": min_priority}
r = client.post("/admin/run/ingest?min_priority=8&background=false",
                headers={"X-API-Key": "test-key"})
check("admin run ingest (sync) -> 200 with correct key",
      r.status_code == 200 and r.json()["min_priority"] == 8)

# Default is background=true: Render's proxy kills responses after ~100s, so
# heavy runs return 202 immediately and finish in a thread.
import threading as _threading
_ran = _threading.Event()
_ingest_mod.run = lambda db_path, min_priority=1: (_ran.set(), {"ok": True})[1]
r = client.post("/admin/run/ingest", headers={"X-API-Key": "test-key"})
check("admin run ingest (background default) -> 202 started",
      r.status_code == 202 and r.json()["started"] is True)
check("background ingest actually executed the worker", _ran.wait(timeout=5))

_match_mod.run = lambda db_path, model=None: {"ok": True, "total_matches": 3}
r = client.post("/admin/run/match?background=false", headers={"X-API-Key": "test-key"})
check("admin run match (sync) -> 200", r.status_code == 200 and r.json()["total_matches"] == 3)

_verify_mod.run = lambda db_path, model=None: {"ok": True, "verified": 2}
r = client.post("/admin/run/verify-employers?background=false", headers={"X-API-Key": "test-key"})
check("admin run verify-employers (sync) -> 200",
      r.status_code == 200 and r.json()["verified"] == 2)

_notify_mod.run = lambda db_path, send_fn=None: {"ok": True, "sent": 1}
r = client.post("/admin/run/notify", headers={"X-API-Key": "test-key"})
check("admin run notify -> 200", r.status_code == 200 and r.json()["sent"] == 1)

_backup_mod.run = lambda db_path: {"ok": True, "bytes": 4096}
r = client.post("/admin/run/backup", headers={"X-API-Key": "test-key"})
check("admin run backup -> 200", r.status_code == 200 and r.json()["bytes"] == 4096)

_backup_mod.run = lambda db_path: {"ok": False, "error": "R2 not configured"}
r = client.post("/admin/run/backup", headers={"X-API-Key": "test-key"})
check("admin run backup surfaces worker failure as 500, never a false 200",
      r.status_code == 500)

# Worker 6 — expire-invites trigger (Phase 2)
import workers.expire_invites as _expire_mod
_orig_expire_run = _expire_mod.run
_expire_mod.run = lambda db_path: {"ok": True, "expired": 3}
r = client.post("/admin/run/expire-invites", headers={"X-API-Key": "test-key"})
check("admin run expire-invites -> 200", r.status_code == 200 and r.json()["expired"] == 3)
check("admin run expire-invites requires the key",
      client.post("/admin/run/expire-invites").status_code == 401)
_expire_mod.run = _orig_expire_run

# Restore real worker functions for any later test / import in this process.
_ingest_mod.run = _orig_ingest_run
_match_mod.run = _orig_match_run
_verify_mod.run = _orig_verify_run
_notify_mod.run = _orig_notify_run
_backup_mod.run = _orig_backup_run

# ---------------- /admin/diagnostics ----------------
check("diagnostics without api key -> 401",
      client.get("/admin/diagnostics").status_code == 401)

r = client.get("/admin/diagnostics", headers={"X-API-Key": "test-key"})
check("diagnostics ok with api key", r.status_code == 200)
diag = r.json()
check("diagnostics reports ready_for_launch as a boolean",
      isinstance(diag["ready_for_launch"], bool))
check("diagnostics.open_items is a list",
      isinstance(diag["open_items"], list))
check("diagnostics.config has every launch-blocker section",
      set(diag["config"].keys()) >= {"emploi_api_key", "gemini", "groq",
                                     "brevo", "paystack", "r2_backup"})
# Test suite runs with EMPLOI_API_KEY=test-key so that flag must be true.
check("diagnostics reports emploi_api_key=True when set",
      diag["config"]["emploi_api_key"] is True)
# Every worker event type has a slot (may be null when nothing has run yet).
check("diagnostics.last_worker_runs has all six worker event types",
      set(diag["last_worker_runs"].keys()) == {
          "JobIngestionRun", "MatchingWorkerRun", "VerificationWorkerRun",
          "NotifyWorkerRun", "BackupWorkerRun", "ExpireInvitesRun"})
check("diagnostics.counts has every launch-facing scale metric",
      set(diag["counts"].keys()) >= {"career_twins", "applications",
                                     "ingested_jobs", "matches",
                                     "matches_unnotified",
                                     "subscriptions_paid",
                                     "job_sources_active",
                                     "job_sources_inactive",
                                     "generations_last_30d"})
# The diagnostics response must NEVER echo a secret value — it should
# only expose booleans for "configured". Prove it by checking that no
# response value equals the actual API key we set at test setup time.
def _walk(obj):
    if isinstance(obj, dict):
        for v in obj.values(): yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj: yield from _walk(v)
    else: yield obj
check("diagnostics NEVER echoes a secret value",
      "test-key" not in [x for x in _walk(diag) if isinstance(x, str)])

# ---------------- /user/session + /user/notifications ----------------
# The web tier calls POST /user/session on every authenticated render so the
# users table has the current email/name from the NextAuth session.
r = client.post("/user/session", headers=AUTH,
                json={"email": "ada@example.com", "name": "Ada",
                      "email_verified": True})
check("user/session accepts a valid session", r.status_code == 200)

# Notifications endpoint requires a session row (returns 409 otherwise).
r = client.patch("/user/notifications", headers=AUTH, json={"enabled": False})
check("user/notifications flips digest opt-in", r.status_code == 200
      and r.json()["notifications_enabled"] is False)

r = client.patch("/user/notifications",
                 headers={"X-API-Key": "test-key", "X-User-Id": "user-no-session"},
                 json={"enabled": True})
check("user/notifications without a session row -> 409",
      r.status_code == 409)

# Invalid email is rejected — 422, never PII in an error string.
r = client.post("/user/session", headers=AUTH,
                json={"email": "not-an-email"})
check("user/session rejects malformed email", r.status_code == 422)

# Missing api key -> 401 (same auth chain as every other user endpoint).
r = client.post("/user/session", json={"email": "x@y.com"})
check("user/session without api key -> 401", r.status_code == 401)

# ---------------- user deletion (NDPA/GDPR) ----------------
r = client.delete("/user", headers=AUTH)
check("delete user ok", r.status_code == 200)
check("career twin gone after deletion",
      client.get("/career-twin", headers=AUTH).json()["career_twin"] == {})
check("applications gone after deletion",
      client.get("/applications", headers=AUTH).json()["applications"] == [])
check("saved jobs gone after deletion (clear_user covers saved_jobs)",
      client.get("/saved-jobs", headers=AUTH).json()["saved"] == [])
billing_after_delete = client.get("/billing/status", headers=AUTH).json()
check("billing subscription reset to free after deletion (clear_user covers subscriptions)",
      billing_after_delete["tier"] == "free")
check("generation usage reset after deletion (clear_user covers generation_log)",
      billing_after_delete["used_this_month"] == 0)
# users row is wiped too — /user/notifications for the deleted user now 409s
r = client.patch("/user/notifications", headers=AUTH, json={"enabled": True})
check("users row wiped by DELETE /user (clear_user covers users)",
      r.status_code == 409)

# ---------------- admin job-sources are key-only (admin_key_auth) ----------
# The admin control panel calls these with the shared key and NO X-User-Id
# (admins have no NextAuth session), so they must not require a user id.
ADMIN_KEY = {"X-API-Key": "test-key"}
check("GET /admin/job-sources works with key only (no X-User-Id)",
      client.get("/admin/job-sources", headers=ADMIN_KEY).status_code == 200)
check("GET /admin/job-sources rejects a wrong key",
      client.get("/admin/job-sources", headers={"X-API-Key": "nope"}).status_code == 401)
r = client.post("/admin/job-sources", headers=ADMIN_KEY,
                json={"company": "", "ats": "jooble", "token": "Lagos:designer", "priority": 5, "active": True})
check("POST /admin/job-sources adds a source with key only",
      r.status_code == 201 and r.json().get("id"))
_sid = r.json()["id"]
check("PATCH /admin/job-sources/{id}/toggle works with key only",
      client.patch(f"/admin/job-sources/{_sid}/toggle?active=false",
                   headers=ADMIN_KEY).status_code == 200)
_edited = client.patch(f"/admin/job-sources/{_sid}", headers=ADMIN_KEY,
                       json={"company": "Design jobs", "ats": "jooble",
                             "token": "Lagos:product-designer", "priority": 8,
                             "category": "design", "region": "Nigeria", "active": True})
check("PATCH /admin/job-sources/{id} updates that source in place",
      _edited.status_code == 200 and any(
          s["id"] == _sid and s["company"] == "Design jobs" and s["priority"] == 8
          for s in client.get("/admin/job-sources", headers=ADMIN_KEY).json()["sources"]))
check("DELETE /admin/job-sources/{id} removes a source with key only",
      client.delete(f"/admin/job-sources/{_sid}", headers=ADMIN_KEY).status_code == 204 and not any(
          s["id"] == _sid for s in client.get("/admin/job-sources", headers=ADMIN_KEY).json()["sources"]))
check("POST /admin/job-sources/seed?sync=true works with key only",
      client.post("/admin/job-sources/seed?sync=true", headers=ADMIN_KEY).status_code == 200)

# ---------------- internal scheduler timing (_worker_due) ----------------
from datetime import datetime as _dt

# hourly: due at boot (last None) and once an hour has elapsed; not before.
check("scheduler hourly: due when never run", m._worker_due(("hourly",), _dt(2026, 7, 18, 14, 0), None))
check("scheduler hourly: not due 30min after last run",
      not m._worker_due(("hourly",), _dt(2026, 7, 18, 14, 30), _dt(2026, 7, 18, 14, 0)))
check("scheduler hourly: due 60min after last run",
      m._worker_due(("hourly",), _dt(2026, 7, 18, 15, 0), _dt(2026, 7, 18, 14, 0)))

# daily at 02:00 UTC.
check("scheduler daily: NOT due before target time (no retro-fire)",
      not m._worker_due(("daily", 2, 0), _dt(2026, 7, 18, 1, 30), None))
check("scheduler daily: due after target when not yet run today",
      m._worker_due(("daily", 2, 0), _dt(2026, 7, 18, 2, 0), _dt(2026, 7, 17, 2, 0)))
check("scheduler daily: NOT due again once it ran today",
      not m._worker_due(("daily", 2, 0), _dt(2026, 7, 18, 14, 0), _dt(2026, 7, 18, 2, 0)))
check("scheduler daily: seeded last_run=now on a mid-day deploy does NOT fire today",
      not m._worker_due(("daily", 2, 0), _dt(2026, 7, 18, 14, 0), _dt(2026, 7, 18, 14, 0)))
check("scheduler daily: fires next day at target after a mid-day-deploy seed",
      m._worker_due(("daily", 2, 0), _dt(2026, 7, 19, 2, 0), _dt(2026, 7, 18, 14, 0)))

# It is opt-in: importing the module (as this test does) must NOT have started
# a scheduler thread, since INTERNAL_SCHEDULER is unset here.
check("scheduler is OFF unless INTERNAL_SCHEDULER=true (no thread on import)",
      m._scheduler_started is False
      and not any(t.name == "internal-scheduler" for t in __import__("threading").enumerate()))
check("scheduler mirrors the 7 render.yaml cron jobs", len(m._scheduler_jobs()) == 7)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILURE(S)")
    sys.exit(1)
print("ALL TESTS PASSED ✅")
