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
    '```json\n{"name": "Ada Obi", "skills": "Python, SQL"}\n```')
r = client.post("/career-twin/extract", headers=AUTH, json={"cv_text": "x" * 60})
check("extract parses fenced JSON", r.json()["career_twin"]["name"] == "Ada Obi")
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
