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
                        "status": "ghosted"}).status_code == 422)

r = client.patch(f"/applications/{app_id}", headers=AUTH,
                 json={"status": "interview"})
check("status transition applied -> interview", r.status_code == 200)
rows = client.get("/applications", headers=AUTH).json()["applications"]
check("transition persisted", rows[0]["status"] == "interview")

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

# ---------------- application generation ----------------
m.app.state.model_factory = lambda: None
r = client.post("/applications/generate", headers=AUTH,
                json={"job": {"company_name": "TestCo", "description": "Build products"}})
check("generation without key -> 503", r.status_code == 503)

m.app.state.model_factory = lambda: FakeModel("Dear TestCo,\n\nFit Score: 85/100")
r = client.post("/applications/generate", headers=AUTH,
                json={"job": {"company_name": "TestCo", "description": "Build products"},
                      "include_review": False})
generated = r.json().get("generated", {})
check("generation returns application and fit score",
      r.status_code == 200 and generated.get("fit_score") == 85 and generated.get("result"))
check("generation rejects a job without description",
      client.post("/applications/generate", headers=AUTH, json={"job": {"company": "TestCo"}}).status_code == 422)
check("generation requires Career Twin",
      client.post("/applications/generate", headers={**AUTH, "X-User-Id": "no-twin"},
                  json={"job": {"description": "Build products"}}).status_code == 409)

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
r = client.post("/admin/run/ingest?min_priority=8", headers={"X-API-Key": "test-key"})
check("admin run ingest -> 200 with correct key",
      r.status_code == 200 and r.json()["min_priority"] == 8)

_match_mod.run = lambda db_path, model=None: {"ok": True, "total_matches": 3}
r = client.post("/admin/run/match", headers={"X-API-Key": "test-key"})
check("admin run match -> 200", r.status_code == 200 and r.json()["total_matches"] == 3)

_verify_mod.run = lambda db_path, model=None: {"ok": True, "verified": 2}
r = client.post("/admin/run/verify-employers", headers={"X-API-Key": "test-key"})
check("admin run verify-employers -> 200", r.status_code == 200 and r.json()["verified"] == 2)

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

# Restore real worker functions for any later test / import in this process.
_ingest_mod.run = _orig_ingest_run
_match_mod.run = _orig_match_run
_verify_mod.run = _orig_verify_run
_notify_mod.run = _orig_notify_run
_backup_mod.run = _orig_backup_run

# ---------------- user deletion (NDPA/GDPR) ----------------
r = client.delete("/user", headers=AUTH)
check("delete user ok", r.status_code == 200)
check("career twin gone after deletion",
      client.get("/career-twin", headers=AUTH).json()["career_twin"] == {})
check("applications gone after deletion",
      client.get("/applications", headers=AUTH).json()["applications"] == [])

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILURE(S)")
    sys.exit(1)
print("ALL TESTS PASSED ✅")
