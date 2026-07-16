"""Offline tests for the Employer Portal API (Phase 2) — candidate side.

Interview Invites: listing, counts, accept/decline, expiration semantics,
contact-unlock timing, recruiter-visibility opt-in, and NDPA erasure of
candidate-side rows. All offline: in-memory DB, patched trust probes,
fake models. check() style like every other suite.
"""
import os
import sys

os.environ["EMPLOI_API_KEY"] = "test-key"
os.environ["EMPLOI_DB_PATH"] = ":memory:"
os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("GROQ_API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

import api.main as m  # noqa: E402
import db as _db  # noqa: E402

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


HM = {"X-API-Key": "test-key", "X-User-Id": "boss-1"}
CAND = {"X-API-Key": "test-key", "X-User-Id": "cand-1"}
OTHER = {"X-API-Key": "test-key", "X-User-Id": "cand-other"}
client = TestClient(m.app)
conn = m.get_conn()

m.dns_fn = lambda d: True
m.mx_fn = lambda d: True
m.fetch_fn = lambda d, timeout=6: (200, "Acme Corp official website careers hiring")
m._verify_cache.clear()
m.app.state.model_factory = lambda: None

# ---------------- recruiter visibility (candidate opt-in) ----------------
check("visibility toggle without a twin -> 409",
      client.patch("/career-twin/recruiter-visibility", headers=CAND,
                   json={"enabled": True}).status_code == 409)
check("GET visibility before twin exists -> off + has_twin false",
      client.get("/career-twin/recruiter-visibility", headers=CAND).json()
      == {"recruiter_visibility": False, "has_twin": False})

client.patch("/career-twin", headers=CAND,
             json={"data": {"name": "Ada", "headline": "Data Analyst",
                            "skills": ["SQL"], "onboarding_complete": True}})
r = client.patch("/career-twin/recruiter-visibility", headers=CAND,
                 json={"enabled": True})
check("visibility opt-in flips on", r.status_code == 200
      and r.json()["recruiter_visibility"] is True)
check("GET visibility reflects the opt-in",
      client.get("/career-twin/recruiter-visibility", headers=CAND).json()
      == {"recruiter_visibility": True, "has_twin": True})
opt_in_events = conn.execute(
    "SELECT COUNT(*) FROM events WHERE type = 'UserOptedInToRecruiterVisibility' "
    "AND user_id = 'cand-1'").fetchone()[0]
check("opt-in event logged for cohort analytics", opt_in_events == 1)
client.patch("/career-twin/recruiter-visibility", headers=CAND,
             json={"enabled": True})
check("re-enabling doesn't double-log the opt-in event",
      conn.execute("SELECT COUNT(*) FROM events "
                   "WHERE type = 'UserOptedInToRecruiterVisibility' "
                   "AND user_id = 'cand-1'").fetchone()[0] == 1)

# ---------------- fixture: employer + free role + invites ----------------
r = client.post("/employer/onboarding", headers=HM,
                json={"company_name": "Acme Corp", "company_domain": "acmecorp.com"})
emp_id = r.json()["employer_id"]
_db.upsert_user(conn, "boss-1", "boss@acmecorp.com", "Boss")
_db.upsert_user(conn, "cand-1", "ada@example.com", "Ada")

m.app.state.model_factory = lambda: FakeModel(
    '[{"company": "Acme Corp", "title": "Data Analyst", '
    '"description": "SQL dashboards for fintech. Remote.", "contact": ""}]')
r = client.post("/employer/roles", headers=HM,
                json={"jd_text": "Data analyst role, SQL dashboards"})
role_id = r.json()["role_id"]

check("invites list starts empty",
      client.get("/invites", headers=CAND).json()["invites"] == [])
check("invites count starts zero",
      client.get("/invites/count", headers=CAND).json() == {"pending": 0, "all": 0})

r = client.post(f"/employer/roles/{role_id}/invites", headers=HM,
                json={"candidate_user_id": "cand-1",
                      "invite_note": "Your SQL work stood out"})
invite_id = r.json()["invite_id"]

# ---------------- candidate listing + shape ----------------
r = client.get("/invites", headers=CAND)
check("pending invite listed by default", len(r.json()["invites"]) == 1)
inv = r.json()["invites"][0]
check("invite shape: role preview (not full description)",
      inv["role"]["title"] == "Data Analyst"
      and len(inv["role"]["description_preview"]) <= 240
      and "description" not in inv["role"])
check("invite shape: employer trust block with verified bool",
      inv["employer"]["company_name"] == "Acme Corp"
      and inv["employer"]["verified"] is True
      and inv["employer"]["trust_level"] == "high")
check("invite shape: note + expiry present",
      inv["invite_note"] == "Your SQL work stood out" and inv["expires_at"])
check("invalid status filter -> 422",
      client.get("/invites?status=bogus", headers=CAND).status_code == 422)
check("count reflects the pending invite",
      client.get("/invites/count", headers=CAND).json() == {"pending": 1, "all": 1})
check("another user sees no invites",
      client.get("/invites", headers=OTHER).json()["invites"] == [])

# ---------------- detail ----------------
r = client.get(f"/invites/{invite_id}", headers=CAND)
check("invite detail includes the FULL role description",
      r.status_code == 200
      and "SQL dashboards for fintech" in r.json()["role"]["description"])
check("invite detail includes employer trust evidence list",
      isinstance(r.json()["employer"]["trust_evidence"], list))
check("someone else's invite -> 404",
      client.get(f"/invites/{invite_id}", headers=OTHER).status_code == 404)
check("unknown invite -> 404",
      client.get("/invites/99999", headers=CAND).status_code == 404)

# ---------------- contact-unlock timing (free role: ONLY on accept) --------
role_view = client.get(f"/employer/roles/{role_id}", headers=HM).json()
check("employer sees NO contact while invite is pending",
      role_view["invites"][0]["contact"] is None)

r = client.post(f"/invites/{invite_id}/accept", headers=CAND)
check("accept -> ok and hands the candidate the employer's email (agency)",
      r.status_code == 200 and r.json()["ok"] is True
      and r.json()["employer_contact_email"] == "boss@acmecorp.com")
check("accept is one-shot (409 after)",
      client.post(f"/invites/{invite_id}/accept", headers=CAND).status_code == 409)
check("decline after accept -> 409",
      client.post(f"/invites/{invite_id}/decline", headers=CAND,
                  json={}).status_code == 409)
check("accept on someone else's invite -> 404",
      client.post(f"/invites/{invite_id}/accept", headers=OTHER).status_code == 404)

role_view = client.get(f"/employer/roles/{role_id}", headers=HM).json()
accepted_view = role_view["invites"][0]
check("employer sees structured contact AFTER accept (email from users table)",
      accepted_view["contact"] is not None
      and accepted_view["contact"]["email"] == "ada@example.com")
check("status filter: accepted shows under status=accepted",
      client.get("/invites?status=accepted", headers=CAND).json()["invites"][0]["id"]
      == invite_id)
check("pending list now empty",
      client.get("/invites", headers=CAND).json()["invites"] == [])

# ---------------- decline flow ----------------
_db.save_career_twin(conn, "cand-2", {"name": "Bola", "headline": "PM"})
_db.set_recruiter_visibility(conn, "cand-2", True)
CAND2 = {"X-API-Key": "test-key", "X-User-Id": "cand-2"}
r = client.post(f"/employer/roles/{role_id}/invites", headers=HM,
                json={"candidate_user_id": "cand-2"})
invite2_id = r.json()["invite_id"]
r = client.post(f"/invites/{invite2_id}/decline", headers=CAND2,
                json={"reason": "not looking right now"})
check("decline with optional reason -> ok", r.status_code == 200)
check("decline recorded with reason",
      _db.get_invite(conn, invite2_id)["status"] == "declined"
      and _db.get_invite(conn, invite2_id)["decline_reason"] == "not looking right now")
role_view = client.get(f"/employer/roles/{role_id}", headers=HM).json()
declined_view = [i for i in role_view["invites"] if i["invite_id"] == invite2_id][0]
check("employer sees declined status + reason but NO contact",
      declined_view["status"] == "declined"
      and declined_view["decline_reason"] == "not looking right now"
      and declined_view["contact"] is None)

# ---------------- expiration semantics ----------------
_db.save_career_twin(conn, "cand-3", {"name": "Chidi"})
_db.set_recruiter_visibility(conn, "cand-3", True)
CAND3 = {"X-API-Key": "test-key", "X-User-Id": "cand-3"}
r = client.post(f"/employer/roles/{role_id}/invites", headers=HM,
                json={"candidate_user_id": "cand-3"})
invite3_id = r.json()["invite_id"]
conn.execute("UPDATE interview_invites SET expires_at = datetime('now', '-1 days') "
             "WHERE id = ?", (invite3_id,))
conn.commit()
check("accepting an expired invite -> 410",
      client.post(f"/invites/{invite3_id}/accept", headers=CAND3).status_code == 410)
check("expired invite marked expired",
      _db.get_invite(conn, invite3_id)["status"] == "expired")
check("expired invite not in the pending count",
      client.get("/invites/count", headers=CAND3).json()["pending"] == 0)

# ---------------- opt-out hides a candidate immediately -------------------
m.app.state.model_factory = lambda: FakeModel(
    '[{"index": 0, "fit_score": 80, "reason": "solid"}]')
client.get(f"/employer/roles/{role_id}/shortlist", headers=HM)  # warm cache
client.patch("/career-twin/recruiter-visibility", headers=CAND2,
             json={"enabled": False})
sl = client.get(f"/employer/roles/{role_id}/shortlist", headers=HM).json()
check("opting out hides the candidate from cached shortlists immediately",
      all(s["candidate_id"] != "cand-2" for s in sl["shortlist"]))

# ---------------- NDPA erasure: candidate-side rows ------------------------
r = client.delete("/user", headers=CAND)
check("DELETE /user (candidate) -> ok", r.status_code == 200)
check("candidate's invites erased",
      conn.execute("SELECT COUNT(*) FROM interview_invites "
                   "WHERE candidate_user_id = 'cand-1'").fetchone()[0] == 0)
check("candidate's shortlist rows erased",
      conn.execute("SELECT COUNT(*) FROM role_shortlists "
                   "WHERE candidate_user_id = 'cand-1'").fetchone()[0] == 0)
check("employer's role view no longer lists the erased candidate",
      all(i["candidate_user_id"] != "cand-1" for i in
          client.get(f"/employer/roles/{role_id}", headers=HM).json()["invites"]))
check("other candidates' invites untouched by the erasure",
      _db.get_invite(conn, invite2_id) is not None)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILURE(S)")
    sys.exit(1)
print("ALL TESTS PASSED ✅")
