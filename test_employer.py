"""Offline tests for the Employer Portal API (Phase 2) — employer side.

No network, no API key, no Gemini: trust probes are patched at the module
seam, the model factory is swapped for fakes, Paystack is mocked at the
billing seam, and the database is in-memory. Same check() style as the
other suites.

Billing model under test (locked with Joy 2026-07-16): role #1 free
(accept-gated contact, 10-invite cap); roles 2+ unlock-gated (1 credit =
₦1,000, packs of min 5, unlock reveals contact immediately).
"""
import os
import sys
import time as _time

os.environ["EMPLOI_API_KEY"] = "test-key"
os.environ["EMPLOI_DB_PATH"] = ":memory:"
os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("GROQ_API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

import api.main as m  # noqa: E402
import db as _db  # noqa: E402
import verify as _verify  # noqa: E402
import core as _core  # noqa: E402

FAILURES = []


def check(label, cond):
    print(("PASS" if cond else "FAIL"), "-", label)
    if not cond:
        FAILURES.append(label)


class FakeModel:
    def __init__(self, text):
        self._text = text

    def generate_content(self, prompt):
        class R:
            pass
        r = R()
        r.text = self._text
        return r


class CountingModel(FakeModel):
    calls = 0

    def generate_content(self, prompt):
        CountingModel.calls += 1
        return super().generate_content(prompt)


HM = {"X-API-Key": "test-key", "X-User-Id": "hm-1"}
HM2 = {"X-API-Key": "test-key", "X-User-Id": "hm-2"}
HM_BAD = {"X-API-Key": "test-key", "X-User-Id": "hm-bad"}
HM_DEAD = {"X-API-Key": "test-key", "X-User-Id": "hm-dead"}
ADMIN = {"X-API-Key": "test-key"}
client = TestClient(m.app)
conn = m.get_conn()

# Healthy trust probes by default.
m.dns_fn = lambda d: True
m.mx_fn = lambda d: True
m.fetch_fn = lambda d, timeout=6: (200, "Acme Corp official website careers hiring")
m.app.state.model_factory = lambda: None
m._verify_cache.clear()

# ---------------- onboarding ----------------
check("GET /employer without membership -> 404",
      client.get("/employer", headers=HM).status_code == 404)

r = client.post("/employer/onboarding", headers=HM,
                json={"company_name": "Acme Corp", "company_domain": "acmecorp.com"})
check("cold onboarding with healthy domain -> 201", r.status_code == 201)
# A healthy domain still SCORES well, but a cold signup has proven nothing
# about its relationship to that domain, so it can never be "high" (which is
# what renders a "Verified employer" badge to candidates). Capped at medium
# until domain control is proven or an admin vouches.
check("healthy domain still scores well on a cold signup",
      r.json()["trust_score"] >= 75)
check("cold onboarding is NEVER 'high' — domain control is unproven",
      r.json()["trust_level"] == "medium")
emp_id = r.json()["employer_id"]

check("duplicate onboarding -> 409",
      client.post("/employer/onboarding", headers=HM,
                  json={"company_name": "Acme Again"}).status_code == 409)

r = client.get("/employer", headers=HM)
check("GET /employer returns identity + billing snapshot",
      r.status_code == 200 and r.json()["employer"]["company_name"] == "Acme Corp"
      and r.json()["employer"]["free_role_used"] is False
      and r.json()["employer"]["credit_balance"] == 0)

# avoid tier (blacklisted domain) -> 403, and NO employer row is created
_verify._lists_cache[_verify.DEFAULT_LISTS_PATH] = {
    "blacklist": {"scamco.com"}, "whitelist": set()}
m._verify_cache.clear()
r = client.post("/employer/onboarding", headers=HM_BAD,
                json={"company_name": "Scam Co", "company_domain": "scamco.com"})
check("avoid-tier employer blocked with 403 + support contact",
      r.status_code == 403 and "hello@emploihq.com" in r.json()["detail"])
check("avoid-tier employer row never created",
      client.get("/employer", headers=HM_BAD).status_code == 404)
_verify._lists_cache[_verify.DEFAULT_LISTS_PATH] = {
    "blacklist": set(), "whitelist": set()}

# dead-DNS domain caps at low (never medium via the domain-contact bonus)
_orig_dns = m.dns_fn
m.dns_fn = lambda d: False
m._verify_cache.clear()
r = client.post("/employer/onboarding", headers=HM_DEAD,
                json={"company_name": "Ghost Ltd", "company_domain": "no-such-domain-xyz.com"})
check("dead-DNS domain onboards as LOW trust (badge, not blocked)",
      r.status_code == 201 and r.json()["trust_level"] == "low")
m.dns_fn = _orig_dns
m._verify_cache.clear()

# domain auto-derived when omitted
r = client.post("/employer/onboarding", headers=HM2,
                json={"company_name": "Fair Money Inc."})
check("onboarding derives company domain from name when omitted",
      r.status_code == 201
      and client.get("/employer", headers=HM2).json()["employer"]["company_domain"]
      == "fairmoney.com")
emp2_id = r.json()["employer_id"]

# PATCH re-verifies on domain change
m._verify_cache.clear()
r = client.patch("/employer", headers=HM2, json={"company_domain": "fairmoney.io"})
check("PATCH /employer with new domain re-runs trust check",
      r.status_code == 200 and r.json()["trust_level"] in ("high", "medium", "low"))

# ---------------- roles: creation paths ----------------
GH_SINGLE = {"id": 4000, "title": "Platform Engineer",
             "content": "<p>Build infra. Remote friendly.</p>",
             "location": {"name": "Remote"},
             "absolute_url": "https://boards.greenhouse.io/testco/jobs/4000",
             "departments": [{"name": "Infrastructure"}]}

import workers.ingest_jobs as _ij
_orig_fetch = _ij._fetch
_ij._fetch = lambda url: (GH_SINGLE if "greenhouse" in url else None)

# Stub the generic career-page connector so the endpoint never touches the
# network. `_GENERIC_PAGE_TEXT` controls what a non-ATS URL "reads" as:
# None = unreadable (JS shell / bot wall), a string = extractable JD text.
_orig_url_text = m.core.fetch_url_text
_GENERIC_PAGE_TEXT = {"v": None}
m.core.fetch_url_text = lambda url: _GENERIC_PAGE_TEXT["v"]

r = client.post("/employer/roles", headers=HM,
                json={"url": "https://boards.greenhouse.io/testco/jobs/4000"})
check("role from supported ATS URL -> 201, extracted_from url",
      r.status_code == 201 and r.json()["extracted_from"] == "url"
      and r.json()["title"] == "Platform Engineer")
check("employer's FIRST role is free", r.json()["is_free"] is True)
free_role_id = r.json()["role_id"]

check("GET /employer reports free_role_used after first role",
      client.get("/employer", headers=HM).json()["employer"]["free_role_used"] is True)

r = client.post("/employer/roles", headers=HM,
                json={"url": "https://www.linkedin.com/jobs/view/123"})
check("LinkedIn URL without jd_text -> 422 with guidance",
      r.status_code == 422 and "paste the JD text" in r.json()["detail"])

r = client.post("/employer/roles", headers=HM,
                json={"url": "https://careers.unknown-host.com/x"})
check("unreadable non-ATS URL (JS shell) without jd_text -> 422", r.status_code == 422)

check("no url and no jd_text -> 422",
      client.post("/employer/roles", headers=HM, json={}).status_code == 422)

# jd_text path needs a model
m.app.state.model_factory = lambda: None
r = client.post("/employer/roles", headers=HM, json={"jd_text": "We need a data analyst"})
check("jd_text without a configured model -> 503", r.status_code == 503)

m.app.state.model_factory = lambda: FakeModel(
    '[{"company": "Acme Corp", "title": "Data Analyst", '
    '"description": "SQL dashboards. Remote.", "contact": ""}]')
r = client.post("/employer/roles", headers=HM,
                json={"jd_text": "We need a data analyst for SQL dashboards",
                      "title_override": "Senior Data Analyst"})
check("role from pasted JD text -> 201 with title_override applied",
      r.status_code == 201 and r.json()["extracted_from"] == "text"
      and r.json()["title"] == "Senior Data Analyst")
check("SECOND role is NOT free (pay-per-unlock)", r.json()["is_free"] is False)
paid_role_id = r.json()["role_id"]

m.app.state.model_factory = lambda: FakeModel("not json at all")
check("unextractable jd_text -> 422",
      client.post("/employer/roles", headers=HM,
                  json={"jd_text": "gibberish"}).status_code == 422)

# fallback: URL fails but jd_text provided
m.app.state.model_factory = lambda: FakeModel(
    '[{"company": "X", "title": "Ops Lead", "description": "Run ops."}]')
r = client.post("/employer/roles", headers=HM2,
                json={"url": "https://careers.unknown-host.com/x",
                      "jd_text": "Ops lead role"})
check("failed URL extraction falls back to jd_text",
      r.status_code == 201 and r.json()["extracted_from"] == "text")
emp2_role_id = r.json()["role_id"]

# Generic career-page connector: a non-ATS URL (careers page / niche board /
# embed) that DOES read as text is extracted via Gemini — the paste-URL fix.
_GENERIC_PAGE_TEXT["v"] = ("Solar Installer wanted at GreenCo. Install rooftop "
                           "solar across Lagos. Remote coordination, field work.")
m.app.state.model_factory = lambda: FakeModel(
    '[{"company": "GreenCo", "title": "Solar Installer", '
    '"description": "Install rooftop solar across Lagos. Field work.", "contact": ""}]')
r = client.post("/employer/roles", headers=HM2,
                json={"url": "https://www.greenjobs.co.uk/job/123/solar-installer"})
check("non-ATS job URL is extracted via the generic connector (extracted_from url_generic)",
      r.status_code == 201 and r.json()["extracted_from"] == "url_generic"
      and r.json()["title"] == "Solar Installer")
_GENERIC_PAGE_TEXT["v"] = None
m.core.fetch_url_text = _orig_url_text
_ij._fetch = _orig_fetch

# ---------------- roles: listing, detail, ownership ----------------
r = client.get("/employer/roles", headers=HM)
check("GET /employer/roles lists both roles",
      r.status_code == 200 and len(r.json()["roles"]) == 2)
check("roles list status filter validates",
      client.get("/employer/roles?status=bogus", headers=HM).status_code == 422)

r = client.get(f"/employer/roles/{free_role_id}", headers=HM)
check("role detail returns full description + empty invites",
      r.status_code == 200 and r.json()["role"]["id"] == free_role_id
      and r.json()["invites"] == [])
check("another employer's role -> 404 (ownership enforced)",
      client.get(f"/employer/roles/{free_role_id}", headers=HM2).status_code == 404)
check("role endpoints require an employer account",
      client.get(f"/employer/roles/{free_role_id}", headers=HM_BAD).status_code == 404)

# ---------------- public job page + apply funnel ----------------
CANDP = {"X-API-Key": "test-key", "X-User-Id": "cand-pub"}
# Public view: no auth header at all.
r = client.get(f"/public/roles/{free_role_id}")
check("public role page is viewable with NO auth",
      r.status_code == 200 and r.json()["role"]["id"] == free_role_id
      and r.json()["role"]["company_name"] == "Acme Corp")
check("public role exposes only safe fields (no invites/shortlist/employer internals)",
      set(r.json()["role"].keys()) ==
      {"id", "title", "description", "location", "is_remote", "salary_text",
       "company_name", "created_at", "trust"})
check("public role trust is honest ('Company checked', not 'Verified employer')",
      r.json()["role"]["trust"]["verified"] is False
      and r.json()["role"]["trust"]["label"] == "Company checked")
check("unknown public role -> 404",
      client.get("/public/roles/999999").status_code == 404)

# Apply is auth-gated (the Google sign-in funnel).
check("applying without auth -> 401",
      client.post(f"/public/roles/{free_role_id}/apply").status_code == 401)
r = client.post(f"/public/roles/{free_role_id}/apply", headers=CANDP)
check("candidate applies to a public role -> 201",
      r.status_code == 201 and r.json()["already_applied"] is False)
r = client.post(f"/public/roles/{free_role_id}/apply", headers=CANDP)
check("re-applying is idempotent (already_applied=true, still 201)",
      r.status_code == 201 and r.json()["already_applied"] is True)
check("only one application row exists for that candidate+role",
      _db.has_applied(conn, free_role_id, "cand-pub")
      and len(_db.list_role_applicants(conn, free_role_id)) == 1)

# Employer sees inbound applicants with contact (consented — they applied).
r = client.get(f"/employer/roles/{free_role_id}/applicants", headers=HM)
check("employer sees inbound applicants with contact",
      r.status_code == 200 and r.json()["count"] == 1
      and r.json()["applicants"][0]["candidate_user_id"] == "cand-pub"
      and "email" in r.json()["applicants"][0]["contact"])
check("applicants list enforces role ownership",
      client.get(f"/employer/roles/{free_role_id}/applicants", headers=HM2).status_code == 404)

# A closed role stops accepting and 404s publicly (throwaway role so the
# shared free/paid roles stay open for later tests).
_emp1 = _db.get_employer_for_user(conn, "hm-1")
_tmp = _db.create_role(conn, _emp1["id"], "hm-1",
                       {"title": "Temp Role", "description": "temp", "is_remote": False})
check("public view of an open role works before close",
      client.get(f"/public/roles/{_tmp['id']}").status_code == 200)
_db.close_role(conn, _tmp["id"], "filled")
check("public view of a closed role -> 404",
      client.get(f"/public/roles/{_tmp['id']}").status_code == 404)
check("applying to a closed role -> 409",
      client.post(f"/public/roles/{_tmp['id']}/apply",
                  headers={"X-API-Key": "test-key", "X-User-Id": "cand-2"}).status_code == 409)

# PATCH: description change invalidates cached shortlist
_db.replace_shortlist(conn, free_role_id, [
    {"candidate_user_id": "cand-x", "fit_score": 50, "reason": "seed"}])
r = client.patch(f"/employer/roles/{free_role_id}", headers=HM,
                 json={"description": "A materially different description"})
check("PATCH role description clears the cached shortlist",
      r.status_code == 200
      and _db.shortlist_cache_age_seconds(conn, free_role_id) is None)

# ---------------- shortlist generation + caching ----------------
r = client.get(f"/employer/roles/{free_role_id}/shortlist", headers=HM)
check("shortlist with no opted-in candidates -> empty with honest note",
      r.status_code == 200 and r.json()["shortlist"] == []
      and "no opted-in candidates" in r.json().get("note", ""))

# Opt in two candidates (and one who stays hidden).
_db.save_career_twin(conn, "cand-1", {"name": "Ada", "headline": "Data Analyst",
                                      "skills": ["SQL", "Python"],
                                      "experience": [{"summary": "Analyst at Flutterwave"}],
                                      "location": "Lagos"})
_db.save_career_twin(conn, "cand-2", {"name": "Bola", "headline": "BI Developer",
                                      "skills": ["PowerBI"]})
_db.save_career_twin(conn, "cand-hidden", {"name": "Chidi", "headline": "PM"})
_db.set_recruiter_visibility(conn, "cand-1", True)
_db.set_recruiter_visibility(conn, "cand-2", True)
_db.upsert_user(conn, "cand-1", "ada@example.com", "Ada")

CountingModel.calls = 0
m.app.state.model_factory = lambda: CountingModel(
    '[{"index": 0, "fit_score": 88, "reason": "strong SQL"}, '
    '{"index": 1, "fit_score": 71, "reason": "BI adjacent"}]')
r = client.get(f"/employer/roles/{free_role_id}/shortlist", headers=HM)
check("empty cache generates shortlist synchronously",
      r.status_code == 200 and len(r.json()["shortlist"]) == 2)
check("shortlist ranked best first with twin fields",
      r.json()["shortlist"][0]["candidate_id"] == "cand-1"
      and r.json()["shortlist"][0]["fit_score"] == 88
      and r.json()["shortlist"][0]["headline"] == "Data Analyst")
check("opted-out candidate never appears in a shortlist",
      all(s["candidate_id"] != "cand-hidden" for s in r.json()["shortlist"]))
check("shortlist contact hidden before accept on the FREE role",
      all(s["contact"] is None for s in r.json()["shortlist"]))
calls_after_first = CountingModel.calls
client.get(f"/employer/roles/{free_role_id}/shortlist", headers=HM)
check("second shortlist view served from cache (no extra model call)",
      CountingModel.calls == calls_after_first)

# refresh regenerates in the background with the refinement note
r = client.post(f"/employer/roles/{free_role_id}/shortlist/refresh", headers=HM,
                json={"refinement_note": "need more startup experience"})
check("shortlist refresh -> 202 started", r.status_code == 202)
for _ in range(50):
    if _db.shortlist_cache_age_seconds(conn, free_role_id) is not None:
        break
    _time.sleep(0.05)
check("refresh repopulated the cache in the background",
      _db.shortlist_cache_age_seconds(conn, free_role_id) is not None)

# ---------------- invites: free role (accept-gated, 10 cap) ----------------
r = client.post(f"/employer/roles/{free_role_id}/invites", headers=HM,
                json={"candidate_user_id": "cand-1",
                      "invite_note": "Loved your fintech work"})
check("free-role invite -> 201 with expiry", r.status_code == 201
      and r.json()["invite_id"] > 0 and r.json()["expires_at"])
invite1_id = r.json()["invite_id"]
check("duplicate invite -> 409",
      client.post(f"/employer/roles/{free_role_id}/invites", headers=HM,
                  json={"candidate_user_id": "cand-1"}).status_code == 409)
check("invite to a non-opted-in candidate -> 404",
      client.post(f"/employer/roles/{free_role_id}/invites", headers=HM,
                  json={"candidate_user_id": "cand-hidden"}).status_code == 404)
check("invites_sent counter visible on the roles list",
      [x for x in client.get("/employer/roles", headers=HM).json()["roles"]
       if x["id"] == free_role_id][0]["invites_sent"] == 1)

# invite fit_score copied from the cached shortlist
inv_row = _db.get_invite(conn, invite1_id)
check("invite carries the shortlist fit_score", inv_row["fit_score"] == 88)

# free-role hard cap of 10
conn.execute("UPDATE employer_roles SET invites_sent = 10 WHERE id = ?",
             (free_role_id,))
conn.commit()
r = client.post(f"/employer/roles/{free_role_id}/invites", headers=HM,
                json={"candidate_user_id": "cand-2"})
check("free-role 11th invite -> 429 with reasonable-use message",
      r.status_code == 429 and "hello@emploihq.com" in r.json()["detail"])
conn.execute("UPDATE employer_roles SET invites_sent = 1 WHERE id = ?",
             (free_role_id,))
conn.commit()

# contact stays hidden until the candidate ACCEPTS (free role)
r = client.get(f"/employer/roles/{free_role_id}", headers=HM)
check("pending invite shows NO contact on the free role",
      r.json()["invites"][0]["contact"] is None)

_db.respond_invite(conn, invite1_id, accept=True)
r = client.get(f"/employer/roles/{free_role_id}", headers=HM)
inv_view = [i for i in r.json()["invites"] if i["invite_id"] == invite1_id][0]
check("accepted invite unlocks the structured contact view (free role)",
      inv_view["contact"] is not None
      and inv_view["contact"]["email"] == "ada@example.com"
      and inv_view["contact"]["name"] == "Ada")
check("contact view never leaks raw CV or history fields",
      set(inv_view["contact"].keys()) == {"name", "email", "phone", "headline",
                                          "location", "skills", "experience",
                                          "education", "career_goals"})

# accepted candidate no longer appears in the shortlist (already_invited)
r = client.get(f"/employer/roles/{free_role_id}/shortlist", headers=HM)
check("invited candidates are excluded from the shortlist view",
      all(s["candidate_id"] != "cand-1" for s in r.json()["shortlist"]))

# ---------------- unlocks + credits: paid role ----------------
r = client.post(f"/employer/roles/{paid_role_id}/invites", headers=HM,
                json={"candidate_user_id": "cand-2"})
check("paid-role invite without unlock -> 402 naming the price",
      r.status_code == 402 and "1,000" in r.json()["detail"])

r = client.post(f"/employer/roles/{paid_role_id}/unlocks", headers=HM,
                json={"candidate_user_id": "cand-2"})
check("unlock with zero credits -> 402 pointing at billing",
      r.status_code == 402 and "buy a pack" in r.json()["detail"])

check("unlock on the FREE role -> 422 (not needed)",
      client.post(f"/employer/roles/{free_role_id}/unlocks", headers=HM,
                  json={"candidate_user_id": "cand-2"}).status_code == 422)

# --- credit checkout (Paystack mocked at the billing seam) ---
check("billing status shows price + min pack",
      client.get("/employer/billing/status", headers=HM).json()
      == {"credit_balance": 0, "free_role_used": True,
          "unlock_price_ngn": 1000, "min_pack": 5})

m.PAYSTACK_SECRET_KEY = ""
check("credit checkout without Paystack config -> 503",
      client.post("/employer/billing/checkout", headers=HM,
                  json={"credits": 5}).status_code == 503)
m.PAYSTACK_SECRET_KEY = "sk_test_fake"

check("credit checkout below the 5-pack minimum -> 422",
      client.post("/employer/billing/checkout", headers=HM,
                  json={"credits": 2}).status_code == 422)

_db.upsert_user(conn, "hm-1", "hm@acmecorp.com", "Hiring Manager")
init_calls = []
m.billing.initialize_onetime_transaction = lambda *a, **k: (
    init_calls.append((a, k)) or
    {"authorization_url": "https://checkout.paystack.com/credits", "reference": "credref_1"})
r = client.post("/employer/billing/checkout", headers=HM, json={"credits": 5})
check("credit checkout returns Paystack URL and the right amount (5 × ₦1,000)",
      r.status_code == 200 and r.json()["amount_ngn"] == 5000
      and init_calls[0][0][2] == 5000)
check("checkout metadata carries kind/employer/credits",
      init_calls[0][1]["metadata"]["kind"] == "employer_credits"
      and init_calls[0][1]["metadata"]["credits"] == 5)

# webhook credits the ledger; replay is a no-op
import hmac as _hmac, hashlib as _hashlib, json as _json


def _signed(body_dict):
    raw = _json.dumps(body_dict).encode()
    sig = _hmac.new(m.PAYSTACK_SECRET_KEY.encode(), raw, _hashlib.sha512).hexdigest()
    return raw, sig


raw, sig = _signed({"event": "charge.success",
                    "data": {"reference": "credref_1",
                             "metadata": {"kind": "employer_credits",
                                          "employer_id": emp_id, "credits": 5}}})
client.post("/billing/webhook", content=raw, headers={"x-paystack-signature": sig})
check("webhook charge.success credits the ledger",
      client.get("/employer/billing/status", headers=HM).json()["credit_balance"] == 5)
client.post("/billing/webhook", content=raw, headers={"x-paystack-signature": sig})
check("webhook replay never double-credits",
      client.get("/employer/billing/status", headers=HM).json()["credit_balance"] == 5)

# verify path is also replay-safe against the same reference
m.billing.verify_transaction = lambda *a, **k: {
    "reference": "credref_1", "status": "success",
    "metadata": {"kind": "employer_credits", "employer_id": emp_id, "credits": 5}}
r = client.post("/employer/billing/verify", headers=HM, json={"reference": "credref_1"})
check("billing verify is replay-safe (balance unchanged)",
      r.status_code == 200 and r.json()["credit_balance"] == 5)
check("billing verify rejects another employer's transaction",
      client.post("/employer/billing/verify", headers=HM2,
                  json={"reference": "credref_1"}).status_code == 404)

# --- unlock now succeeds, reveals contact immediately, spends a credit ---
_db.upsert_user(conn, "cand-2", "bola@example.com", "Bola")
r = client.post(f"/employer/roles/{paid_role_id}/unlocks", headers=HM,
                json={"candidate_user_id": "cand-2"})
check("unlock succeeds with credits and reveals contact immediately",
      r.status_code == 201 and r.json()["contact"]["email"] == "bola@example.com"
      and r.json()["credit_balance"] == 4)
r2 = client.post(f"/employer/roles/{paid_role_id}/unlocks", headers=HM,
                 json={"candidate_user_id": "cand-2"})
check("re-unlock is idempotent (no second credit spent)",
      r2.status_code == 201 and r2.json()["already_unlocked"] is True
      and r2.json()["credit_balance"] == 4)

r = client.post(f"/employer/roles/{paid_role_id}/invites", headers=HM,
                json={"candidate_user_id": "cand-2", "invite_note": "Join us!"})
check("paid-role invite allowed after unlock", r.status_code == 201)
paid_invite_id = r.json()["invite_id"]

r = client.get(f"/employer/roles/{paid_role_id}", headers=HM)
inv_view = [i for i in r.json()["invites"] if i["invite_id"] == paid_invite_id][0]
check("paid-role contact visible while invite still pending (unlock = reveal)",
      inv_view["contact"] is not None
      and inv_view["contact"]["email"] == "bola@example.com")

# ---------------- hire flow ----------------
r = client.post(f"/employer/roles/{paid_role_id}/hire", headers=HM,
                json={"invite_id": paid_invite_id})
check("hire before candidate accepts -> 422", r.status_code == 422)
check("hire with unknown invite -> 404",
      client.post(f"/employer/roles/{paid_role_id}/hire", headers=HM,
                  json={"invite_id": 99999}).status_code == 404)

# second pending invite that must auto-expire on hire
_db.save_career_twin(conn, "cand-3", {"name": "Dayo", "headline": "Analyst"})
_db.set_recruiter_visibility(conn, "cand-3", True)
client.post(f"/employer/roles/{paid_role_id}/unlocks", headers=HM,
            json={"candidate_user_id": "cand-3"})
r = client.post(f"/employer/roles/{paid_role_id}/invites", headers=HM,
                json={"candidate_user_id": "cand-3"})
sibling_invite_id = r.json()["invite_id"]

_db.respond_invite(conn, paid_invite_id, accept=True)
r = client.post(f"/employer/roles/{paid_role_id}/hire", headers=HM,
                json={"invite_id": paid_invite_id})
check("hire on accepted invite -> ok with hired_at",
      r.status_code == 200 and r.json()["ok"] is True and r.json()["hired_at"])
check("sibling pending invites auto-expired on hire",
      r.json()["expired_other_invites"] == 1
      and _db.get_invite(conn, sibling_invite_id)["status"] == "expired")
check("role status is hired",
      _db.get_role(conn, paid_role_id)["status"] == "hired")
hire_event = conn.execute(
    "SELECT COUNT(*) FROM events WHERE type = 'HireCompleted'").fetchone()[0]
check("HireCompleted event emitted (revenue analytics)", hire_event == 1)
check("invite on a non-open role -> 409",
      client.post(f"/employer/roles/{paid_role_id}/invites", headers=HM,
                  json={"candidate_user_id": "cand-1"}).status_code == 409)

# ---------------- close flow ----------------
m.app.state.model_factory = lambda: FakeModel(
    '[{"company": "Acme", "title": "Temp Role", "description": "temp"}]')
r = client.post("/employer/roles", headers=HM, json={"jd_text": "temp role"})
temp_role_id = r.json()["role_id"]
r = client.post(f"/employer/roles/{temp_role_id}/close", headers=HM,
                json={"reason": "not hiring"})
check("close role -> ok, reason recorded (nudge, optional)",
      r.status_code == 200
      and _db.get_role(conn, temp_role_id)["close_reason"] == "not hiring")
r = client.post(f"/employer/roles/{temp_role_id}/close", headers=HM, json={})
check("close without a reason also fine (never forced)", r.status_code == 200)

# ---------------- avoid-tier via PATCH: posting + inviting blocked ----------
# Onboarding never creates an avoid row, but a domain change on PATCH can
# re-verify an existing employer into 'avoid'. That employer must not be able
# to post or invite (regression: the gate originally only existed at
# onboarding). A vouch overrides.
_db.set_employer_trust(conn, emp_id, 10, "avoid")
r = client.post("/employer/roles", headers=HM, json={"jd_text": "another role"})
check("avoid-tier employer blocked from posting (403)",
      r.status_code == 403 and "hello@emploihq.com" in r.json()["detail"])
r = client.post(f"/employer/roles/{free_role_id}/invites", headers=HM,
                json={"candidate_user_id": "cand-2"})
check("avoid-tier employer blocked from inviting (403)", r.status_code == 403)
_db.vouch_employer(conn, emp_id, "joy")
r = client.post(f"/employer/roles/{free_role_id}/invites", headers=HM,
                json={"candidate_user_id": "cand-2"})
check("vouch overrides the avoid-tier block", r.status_code == 201)
_db.update_employer(conn, emp_id, warm_intro_by=None)
_db.set_employer_trust(conn, emp_id, 80, "high")

# ---------------- admin: vouch + metrics ----------------
check("vouch requires the admin key",
      client.post(f"/admin/employers/{emp_id}/vouch").status_code == 401)
r = client.post(f"/admin/employers/{emp_id}/vouch", headers=ADMIN,
                json={"vouched_by": "joy"})
check("admin vouch sets warm_intro_by",
      r.status_code == 200
      and _db.get_employer(conn, emp_id)["warm_intro_by"] == "joy")
check("vouch unknown employer -> 404",
      client.post("/admin/employers/99999/vouch", headers=ADMIN,
                  json={}).status_code == 404)

# ---------------- admin: grant free credits ----------------
_bal0 = _db.credit_balance(conn, emp_id)
check("grant credits requires the admin key",
      client.post(f"/admin/employers/{emp_id}/credits",
                  json={"delta": 5}).status_code == 401)
r = client.post(f"/admin/employers/{emp_id}/credits", headers=ADMIN,
                json={"delta": 5, "reason": "partner_comp"})
check("admin grant adds credits and returns the new balance",
      r.status_code == 200 and r.json()["credit_balance"] == _bal0 + 5)
check("granted credits are spendable (balance reflects the grant)",
      _db.credit_balance(conn, emp_id) == _bal0 + 5)
check("admin grant is recorded with an admin: reason prefix (audit)",
      conn.execute("SELECT reason FROM employer_credit_ledger WHERE employer_id = ? "
                   "ORDER BY id DESC LIMIT 1", (emp_id,)).fetchone()[0] == "admin:partner_comp")
check("grant of zero is rejected",
      client.post(f"/admin/employers/{emp_id}/credits", headers=ADMIN,
                  json={"delta": 0}).status_code == 422)
check("grant to unknown employer -> 404",
      client.post("/admin/employers/99999/credits", headers=ADMIN,
                  json={"delta": 5}).status_code == 404)
check("clawback beyond balance is rejected (never goes negative)",
      client.post(f"/admin/employers/{emp_id}/credits", headers=ADMIN,
                  json={"delta": -9999}).status_code == 422)
check("out-of-bounds grant is rejected by the model (|delta| <= 500)",
      client.post(f"/admin/employers/{emp_id}/credits", headers=ADMIN,
                  json={"delta": 100000}).status_code == 422)
r = client.get("/admin/employers", headers=ADMIN)
check("admin employer list includes the employer with its live balance",
      r.status_code == 200
      and any(e["id"] == emp_id and e["credit_balance"] == _bal0 + 5
              for e in r.json()["employers"]))
check("admin employer list requires the admin key",
      client.get("/admin/employers").status_code == 401)

r = client.get("/admin/metrics", headers=ADMIN)
metrics = r.json()
check("admin metrics returns the MVP dashboard rollup",
      r.status_code == 200
      and set(metrics.keys()) >= {"career_twins", "twins_opted_in", "employers",
                                  "roles_open", "invites", "unlocks_total",
                                  "credits_purchased", "jobs_ingested_today",
                                  "applications", "generations_last_30d",
                                  "trust_alerts"})
check("metrics counts opted-in twins", metrics["twins_opted_in"] == 3)
check("metrics counts purchased credits", metrics["credits_purchased"] == 5)
check("trust alerts list low-trust unvouched employers",
      any(t["company_name"] == "Ghost Ltd" for t in metrics["trust_alerts"]))
check("metrics never contains candidate PII",
      "ada@example.com" not in _json.dumps(metrics))

# ---------------- clear_user coverage (employer side) ----------------
r = client.delete("/user", headers=HM2)
check("DELETE /user for an employer user -> ok", r.status_code == 200)
check("employer membership dropped after deletion",
      client.get("/employer", headers=HM2).status_code == 404)
check("their open roles were closed",
      _db.get_role(conn, emp2_role_id)["status"] == "closed")

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILURE(S)")
    sys.exit(1)
print("ALL TESTS PASSED ✅")
