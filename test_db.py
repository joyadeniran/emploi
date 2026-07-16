"""Offline tests for the persistence scaffold. Run: python3 test_db.py
Uses in-memory SQLite only — no files, no network."""

import sys

from db import (connect, save_career_twin, load_career_twin,
                add_application, list_applications,
                update_application_status, clear_user,
                list_applications_needing_outcome_nudge,
                upsert_job, list_jobs, count_jobs,
                upsert_trust_record, get_trust_record,
                upsert_match, list_matches, log_event,
                get_subscription, upsert_subscription,
                log_generation, count_generations_this_month,
                upsert_user, get_user, set_notifications_enabled)


def check(label, cond):
    print(("PASS" if cond else "FAIL"), "-", label)
    return cond


ok = True
conn = connect(":memory:")

# 1. Career Twin roundtrip
twin = {"name": "Ada", "skills": "Python, SQL", "goals": "remote data roles"}
save_career_twin(conn, "user-1", twin)
ok &= check("career twin roundtrip", load_career_twin(conn, "user-1") == twin)

# 2. Save is an upsert
save_career_twin(conn, "user-1", {"name": "Ada Obi"})
ok &= check("second save overwrites", load_career_twin(conn, "user-1") == {"name": "Ada Obi"})

# 3. Unknown user -> empty dict, never raises
ok &= check("unknown user -> {}", load_career_twin(conn, "nobody") == {})

# 4. Users are isolated
save_career_twin(conn, "user-2", {"name": "Bola"})
ok &= check("users isolated",
            load_career_twin(conn, "user-1") == {"name": "Ada Obi"}
            and load_career_twin(conn, "user-2") == {"name": "Bola"})

# 5. Applications: insert + list (newest first)
a1 = add_application(conn, "user-1", {"company": "Acme", "role": "Analyst",
                                      "status": "Generated", "fit_score": 78})
a2 = add_application(conn, "user-1", {"company": "Halo", "role": "VA",
                                      "status": "Sent", "notes": "via curator"})
apps = list_applications(conn, "user-1")
ok &= check("two applications listed, newest first",
            len(apps) == 2 and apps[0]["company"] == "Halo")
ok &= check("row ids returned and present", a1 != a2 and apps[1]["id"] == a1)
ok &= check("extra fields preserved (notes, fit_score)",
            apps[0]["notes"] == "via curator" and apps[1]["fit_score"] == 78)

# 6. Applications are per-user
ok &= check("other user sees no applications", list_applications(conn, "user-2") == [])

# 7. Status update + outcome notes + outcome_updated_at audit
update_application_status(conn, a1, "Interview")
apps = list_applications(conn, "user-1")
row1 = [a for a in apps if a["id"] == a1][0]
ok &= check("status update sticks", row1["status"] == "Interview")
ok &= check("outcome_updated_at set on transition off applied",
            row1["outcome_updated_at"] is not None)

update_application_status(conn, a2, "heard_back",
                          outcome_notes="recruiter reached out on LinkedIn")
apps = list_applications(conn, "user-1")
row2 = [a for a in apps if a["id"] == a2][0]
ok &= check("outcome_notes persist through update",
            row2["outcome_notes"] == "recruiter reached out on LinkedIn")

# 7b. Stale-applied nudge query
# Backdate one application to 20 days ago; it should surface in the nudge list.
conn.execute("UPDATE applications SET status='applied', outcome_updated_at=NULL, "
             "created_at=datetime('now', '-20 days') WHERE id=?", (a2,))
conn.commit()
nudges = list_applications_needing_outcome_nudge(conn, "user-1", days=14)
ok &= check("stale applied application surfaces in nudge query",
            any(n["id"] == a2 for n in nudges))
# a1 is Interview (not applied), even if old, must not be nudged.
conn.execute("UPDATE applications SET created_at=datetime('now', '-30 days') "
             "WHERE id=?", (a1,))
conn.commit()
nudges = list_applications_needing_outcome_nudge(conn, "user-1", days=14)
ok &= check("non-applied statuses are never nudged",
            all(n["id"] != a1 for n in nudges))
# Days threshold is respected: bump to 100 → nothing qualifies.
ok &= check("days threshold gates the nudge query",
            list_applications_needing_outcome_nudge(conn, "user-1", days=100) == [])
# Users are isolated.
ok &= check("nudges are per-user",
            list_applications_needing_outcome_nudge(conn, "user-2", days=14) == [])

# 8. Defensive: non-dict data rejected, DB untouched
try:
    save_career_twin(conn, "user-1", "not a dict")
    bad = False
except (TypeError, ValueError):
    bad = True
ok &= check("non-dict career twin raises, existing data intact",
            bad and load_career_twin(conn, "user-1") == {"name": "Ada Obi"})

# 8b. Users table (session-backed identity)
upsert_user(conn, "user-1", "ada@example.com", "Ada Obi", email_verified=True)
u1 = get_user(conn, "user-1")
ok &= check("upsert_user creates a row", u1 is not None and u1["email"] == "ada@example.com")
ok &= check("upsert_user preserves name", u1["name"] == "Ada Obi")
ok &= check("upsert_user email_verified round-trips as bool",
            u1["email_verified"] is True)
ok &= check("notifications_enabled defaults True",
            u1["notifications_enabled"] is True)

# Idempotent: second call updates last_seen_at without duplicating
import time as _t
_t.sleep(1.05)  # sqlite datetime('now') has second resolution
upsert_user(conn, "user-1", "ada.obi@example.com", None)  # None keeps existing name
u1b = get_user(conn, "user-1")
ok &= check("second upsert updates email", u1b["email"] == "ada.obi@example.com")
ok &= check("second upsert preserves name when None passed",
            u1b["name"] == "Ada Obi")
ok &= check("second upsert bumps last_seen_at",
            u1b["last_seen_at"] > u1["last_seen_at"])

# notifications_enabled toggle
ok &= check("set_notifications_enabled(False) returns True",
            set_notifications_enabled(conn, "user-1", False) is True)
ok &= check("notifications_enabled reflects new state",
            get_user(conn, "user-1")["notifications_enabled"] is False)
ok &= check("set_notifications_enabled on unknown user returns False",
            set_notifications_enabled(conn, "nobody", True) is False)

# Empty inputs are rejected — email is required (Google session always carries one)
try:
    upsert_user(conn, "", "x@y.com")
    raised = False
except ValueError:
    raised = True
ok &= check("upsert_user without user_id raises", raised)
try:
    upsert_user(conn, "u", "")
    raised = False
except ValueError:
    raised = True
ok &= check("upsert_user without email raises", raised)

# get_user returns None (never raises) for unknown user
ok &= check("get_user on unknown user -> None", get_user(conn, "unknown") is None)

# 9. clear_user wipes only that user (NDPA/GDPR right)
clear_user(conn, "user-1")
ok &= check("clear_user removes career twin and applications",
            load_career_twin(conn, "user-1") == {}
            and list_applications(conn, "user-1") == [])
ok &= check("clear_user wipes users row too (NDPA/GDPR)",
            get_user(conn, "user-1") is None)
ok &= check("clear_user leaves other users untouched",
            load_career_twin(conn, "user-2") == {"name": "Bola"})

# 10. Cross-thread use
import tempfile as _tf, os as _os2, threading
_dbfile = _tf.NamedTemporaryFile(suffix=".sqlite3", delete=False).name
tconn = connect(_dbfile, check_same_thread=False)
err = []
def _work():
    try:
        save_career_twin(tconn, "t-user", {"name": "Thread"})
    except Exception as e:
        err.append(e)
t = threading.Thread(target=_work); t.start(); t.join()
ok &= check("connection usable from another thread when check_same_thread=False",
            not err and load_career_twin(tconn, "t-user") == {"name": "Thread"})
tconn.close(); _os2.unlink(_dbfile)

# 11. Legacy profiles table migrated transparently on connect
import sqlite3
_dbfile2 = _tf.NamedTemporaryFile(suffix=".sqlite3", delete=False).name
_c = sqlite3.connect(_dbfile2)
_c.execute("CREATE TABLE profiles (user_id TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT (datetime('now')))")
_c.execute("INSERT INTO profiles VALUES ('migrated-user', '{\"name\":\"Legacy\"}', datetime('now'))")
_c.commit(); _c.close()
mconn = connect(_dbfile2)
ok &= check("legacy profiles table migrated to career_twins",
            load_career_twin(mconn, "migrated-user") == {"name": "Legacy"})
mconn.close(); _os2.unlink(_dbfile2)

# ---------------------------------------------------------------------------
# New tables: ingested_jobs, employer_trust_records, matches, events
# ---------------------------------------------------------------------------
jconn = connect(":memory:")

# 12. upsert_job roundtrip + dedup
fields1 = {"title": "Backend Engineer", "company_name": "Acme", "description": "Build APIs",
            "location": "Remote", "is_remote": True, "apply_url": "https://acme.co/jobs/1"}
id1 = upsert_job(jconn, "greenhouse/acme", "gh-101", fields1)
ok &= check("upsert_job returns a row id", id1 > 0)
jobs = list_jobs(jconn)
ok &= check("one job in the pool", len(jobs) == 1)
ok &= check("job fields round-trip", jobs[0]["title"] == "Backend Engineer"
            and jobs[0]["is_remote"] == 1)

# Re-upsert same key → updates, not duplicates
fields1b = {**fields1, "title": "Senior Backend Engineer"}
id1b = upsert_job(jconn, "greenhouse/acme", "gh-101", fields1b)
ok &= check("re-upsert same source+id updates in place (no duplicate)",
            len(list_jobs(jconn)) == 1 and list_jobs(jconn)[0]["title"] == "Senior Backend Engineer")

# 13. Filtering
upsert_job(jconn, "lever/stripe", "lv-001",
           {"title": "PM", "company_name": "Stripe", "is_remote": False,
            "category": "Product"})
upsert_job(jconn, "lever/stripe", "lv-002",
           {"title": "Designer", "company_name": "Stripe", "is_remote": True,
            "category": "Design"})
ok &= check("list_jobs remote_only filters correctly",
            all(j["is_remote"] for j in list_jobs(jconn, remote_only=True)))
ok &= check("list_jobs category filter works",
            [j["title"] for j in list_jobs(jconn, category="Product")] == ["PM"])
ok &= check("count_jobs total", count_jobs(jconn) == 3)
ok &= check("count_jobs remote_only", count_jobs(jconn, remote_only=True) == 2)

# 14. clear_user also wipes matches (and events)
upsert_match(jconn, "u1", id1, 85, "Strong match on backend skills")
upsert_match(jconn, "u1", id1b, 72, "Good match")
log_event(jconn, "TestEvent", {"x": 1}, user_id="u1")
ok &= check("matches listed for user", len(list_matches(jconn, "u1")) >= 1)
clear_user(jconn, "u1")
ok &= check("clear_user wipes matches", list_matches(jconn, "u1") == [])

# 15. upsert_match: ON CONFLICT updates score
upsert_match(jconn, "u2", id1, 60, "ok fit")
upsert_match(jconn, "u2", id1, 90, "revised fit")  # same user+job
ok &= check("upsert_match deduplicates on user+job",
            len(list_matches(jconn, "u2")) == 1
            and list_matches(jconn, "u2")[0]["fit_score"] == 90)

# 16. billing: subscription defaults + upsert + generation quota counting
ok &= check("get_subscription defaults to free for a never-billed user",
            get_subscription(jconn, "never-billed")["tier"] == "free")
upsert_subscription(jconn, "u3", tier="pro", status="active",
                    paystack_customer_code="CUS_1")
sub = get_subscription(jconn, "u3")
ok &= check("upsert_subscription creates a row", sub["tier"] == "pro" and sub["status"] == "active")
upsert_subscription(jconn, "u3", status="cancelled")
ok &= check("upsert_subscription updates only the given fields (tier untouched)",
            get_subscription(jconn, "u3")["tier"] == "pro"
            and get_subscription(jconn, "u3")["status"] == "cancelled")
upsert_subscription(jconn, "u3", tier="max", nonsense="x")  # unknown field must be dropped, not error
ok &= check("upsert_subscription ignores unknown fields (no SQL injection surface)",
            get_subscription(jconn, "u3")["tier"] == "max"
            and "nonsense" not in get_subscription(jconn, "u3"))

ok &= check("count_generations_this_month starts at 0", count_generations_this_month(jconn, "u4") == 0)
log_generation(jconn, "u4")
log_generation(jconn, "u4")
ok &= check("log_generation increments the monthly count", count_generations_this_month(jconn, "u4") == 2)
ok &= check("generation count is per-user", count_generations_this_month(jconn, "u3") == 0)

clear_user(jconn, "u4")
ok &= check("clear_user wipes generation_log", count_generations_this_month(jconn, "u4") == 0)
clear_user(jconn, "u3")
ok &= check("clear_user resets billing to free", get_subscription(jconn, "u3")["tier"] == "free")

# 16. employer_trust_records roundtrip
fake_result = {"score": 78, "level": "High trust",
               "signals": {"dns": True, "mx": True}, "evidence": ["✅ domain resolves"]}
upsert_trust_record(jconn, "acme.co", "Acme Corp", fake_result)
record = get_trust_record(jconn, "acme.co")
ok &= check("trust record round-trips domain+score",
            record is not None and record["trust_score"] == 78)
ok &= check("trust record signals decoded", record["signals"]["dns"] is True)
ok &= check("unknown domain -> None", get_trust_record(jconn, "unknowndomain.io") is None)

# 17. log_event never raises (even on bad payload)
log_event(jconn, "CrashTest", {"x": object()}, user_id="u3")  # non-serialisable
ok &= check("log_event swallows serialisation errors (never raises)", True)

# ===========================================================================
# Phase 2 — Employer Portal tables
# ===========================================================================
from db import (create_employer, get_employer, get_employer_for_user,
                update_employer, set_employer_trust, vouch_employer,
                get_employer_owner_email,
                create_role, get_role, list_roles, update_role,
                touch_role_viewed, close_role, hire_candidate,
                replace_shortlist, list_shortlist, count_shortlist,
                clear_shortlist, shortlist_cache_age_seconds,
                create_invite, get_invite, get_invite_detail,
                list_candidate_invites, count_candidate_invites,
                list_role_invites, respond_invite,
                add_credits, credit_balance, create_unlock, is_unlocked,
                set_recruiter_visibility, get_recruiter_visibility,
                list_visible_twins)

econn = connect(":memory:")

# 18. recruiter_visibility: default OFF, toggle, no-twin case
save_career_twin(econn, "cand-1", {"name": "Ada", "headline": "Data Analyst",
                                   "skills": ["Python"], "onboarding_complete": True})
ok &= check("recruiter_visibility defaults to OFF (locked product decision)",
            get_recruiter_visibility(econn, "cand-1") is False)
ok &= check("set_recruiter_visibility flips opt-in on",
            set_recruiter_visibility(econn, "cand-1", True) is True
            and get_recruiter_visibility(econn, "cand-1") is True)
ok &= check("set_recruiter_visibility without a twin returns False",
            set_recruiter_visibility(econn, "no-twin-user", True) is False)
ok &= check("list_visible_twins returns only opted-in candidates",
            [t["user_id"] for t in list_visible_twins(econn)] == ["cand-1"])
save_career_twin(econn, "cand-2", {"name": "Bola", "headline": "PM"})
ok &= check("save_career_twin preserves recruiter_visibility on upsert",
            get_recruiter_visibility(econn, "cand-1") is True)
ok &= check("non-opted-in candidate stays invisible",
            all(t["user_id"] != "cand-2" for t in list_visible_twins(econn)))

# 19. employers + employer_users CRUD
emp_id = create_employer(econn, "Acme Corp", "acmecorp.com", "hm-1",
                         trust_score=80, trust_level="high")
ok &= check("create_employer returns id", emp_id > 0)
emp = get_employer(econn, emp_id)
ok &= check("employer fields round-trip",
            emp["company_name"] == "Acme Corp" and emp["trust_level"] == "high")
ok &= check("verified_at set when trust provided", emp["verified_at"] is not None)
ok &= check("get_employer_for_user finds membership",
            get_employer_for_user(econn, "hm-1")["id"] == emp_id)
ok &= check("get_employer_for_user None for stranger",
            get_employer_for_user(econn, "someone-else") is None)
update_employer(econn, emp_id, company_domain="acme.io", nonsense="dropped")
ok &= check("update_employer updates allowed fields, drops unknown",
            get_employer(econn, emp_id)["company_domain"] == "acme.io")
set_employer_trust(econn, emp_id, 42, "medium")
ok &= check("set_employer_trust updates score+level",
            get_employer(econn, emp_id)["trust_score"] == 42
            and get_employer(econn, emp_id)["trust_level"] == "medium")
ok &= check("vouch_employer sets warm_intro_by",
            vouch_employer(econn, emp_id, "joy") is True
            and get_employer(econn, emp_id)["warm_intro_by"] == "joy")
ok &= check("vouch_employer on unknown id returns False",
            vouch_employer(econn, 99999, "joy") is False)
upsert_user(econn, "hm-1", "hm@acmecorp.com", "Hiring Manager")
ok &= check("get_employer_owner_email resolves via users table",
            get_employer_owner_email(econn, emp_id) == "hm@acmecorp.com")

# 20. roles: first role is free, later roles are not
r1 = create_role(econn, emp_id, "hm-1", {"title": "Data Analyst",
                                         "description": "Analyse data",
                                         "location": "Lagos", "is_remote": True})
ok &= check("first role is marked free", r1["is_free"] is True)
r2 = create_role(econn, emp_id, "hm-1", {"title": "Backend Engineer",
                                         "description": "Build APIs"})
ok &= check("second role is NOT free (pay-per-unlock)", r2["is_free"] is False)
role1 = get_role(econn, r1["id"])
ok &= check("role fields round-trip", role1["title"] == "Data Analyst"
            and role1["is_remote"] == 1 and role1["status"] == "open")
ok &= check("get_role with wrong employer_id returns None (ownership)",
            get_role(econn, r1["id"], employer_id=99999) is None)
update_role(econn, r1["id"], title="Senior Data Analyst", status="hacked")
ok &= check("update_role updates allowed fields only",
            get_role(econn, r1["id"])["title"] == "Senior Data Analyst"
            and get_role(econn, r1["id"])["status"] == "open")

# 21. invites: create, dedup, counters, state machine
inv1 = create_invite(econn, r1["id"], "cand-1", "hm-1", fit_score=88,
                     invite_note="Loved your profile")
ok &= check("create_invite returns id", inv1 is not None and inv1 > 0)
ok &= check("duplicate invite for same (role, candidate) returns None",
            create_invite(econn, r1["id"], "cand-1", "hm-1") is None)
ok &= check("invites_sent counter bumped once",
            get_role(econn, r1["id"])["invites_sent"] == 1)
inv = get_invite(econn, inv1)
ok &= check("invite defaults pending with 14-day expiry",
            inv["status"] == "pending" and inv["expires_at"] > inv["created_at"])
detail = get_invite_detail(econn, inv1)
ok &= check("invite detail joins role + employer",
            detail["role_title"] == "Senior Data Analyst"
            and detail["company_name"] == "Acme Corp")
counts = count_candidate_invites(econn, "cand-1")
ok &= check("count_candidate_invites pending=1 all=1",
            counts == {"pending": 1, "all": 1})
ok &= check("candidate invite listing joined",
            list_candidate_invites(econn, "cand-1")[0]["company_name"] == "Acme Corp")
ok &= check("invites are per-candidate",
            list_candidate_invites(econn, "cand-2") == [])

# accept flow
ok &= check("respond_invite accept -> ok", respond_invite(econn, inv1, True) == "ok")
ok &= check("accepted invite recorded",
            get_invite(econn, inv1)["status"] == "accepted"
            and get_invite(econn, inv1)["responded_at"] is not None)
ok &= check("accepting a non-pending invite -> not_pending",
            respond_invite(econn, inv1, True) == "not_pending")

# decline flow (fresh candidate)
save_career_twin(econn, "cand-3", {"name": "Chidi"})
set_recruiter_visibility(econn, "cand-3", True)
inv2 = create_invite(econn, r1["id"], "cand-3", "hm-1")
ok &= check("respond_invite decline records reason",
            respond_invite(econn, inv2, False, "role not a fit") == "ok"
            and get_invite(econn, inv2)["decline_reason"] == "role not a fit")

# expired-at-accept flow
save_career_twin(econn, "cand-4", {"name": "Dayo"})
inv3 = create_invite(econn, r1["id"], "cand-4", "hm-1")
econn.execute("UPDATE interview_invites SET expires_at = datetime('now', '-1 days') "
              "WHERE id = ?", (inv3,))
econn.commit()
ok &= check("accepting past expires_at -> expired (and marked so)",
            respond_invite(econn, inv3, True) == "expired"
            and get_invite(econn, inv3)["status"] == "expired")
ok &= check("expired invite not counted as pending",
            count_candidate_invites(econn, "cand-4")["pending"] == 0)

# 22. hire: only accepted invites; siblings auto-expire
save_career_twin(econn, "cand-5", {"name": "Efe"})
inv4 = create_invite(econn, r1["id"], "cand-5", "hm-1")  # stays pending
res = hire_candidate(econn, r1["id"], inv2)  # declined invite
ok &= check("hire on a declined invite refused", res["error"] == "not_accepted")
res = hire_candidate(econn, r1["id"], 99999)
ok &= check("hire on unknown invite refused", res["error"] == "not_found")
res = hire_candidate(econn, r1["id"], inv1)  # accepted earlier
ok &= check("hire on accepted invite succeeds", res["ok"] is True)
role1 = get_role(econn, r1["id"])
ok &= check("role marked hired with candidate recorded",
            role1["status"] == "hired"
            and role1["hired_candidate_user_id"] == "cand-1"
            and role1["hired_at"] is not None)
ok &= check("hired invite terminal state", get_invite(econn, inv1)["status"] == "hired")
ok &= check("sibling pending invites auto-expired on hire",
            res["expired_others"] == 1
            and get_invite(econn, inv4)["status"] == "expired")

# 23. close_role expires pending invites, records nudge reason
r3 = create_role(econn, emp_id, "hm-1", {"title": "Ops", "description": "Ops role"})
inv5 = create_invite(econn, r3["id"], "cand-3", "hm-1")
expired = close_role(econn, r3["id"], reason="not hiring")
role3 = get_role(econn, r3["id"])
ok &= check("close_role sets status/closed_at/reason and expires pending",
            role3["status"] == "closed" and role3["closed_at"] is not None
            and role3["close_reason"] == "not hiring"
            and expired == 1 and get_invite(econn, inv5)["status"] == "expired")

# 24. list_roles counts + unread tracking
roles = list_roles(econn, emp_id)
ok &= check("list_roles returns all roles newest first",
            [r["id"] for r in roles] == sorted([r["id"] for r in roles], reverse=True))
r1row = [r for r in roles if r["id"] == r1["id"]][0]
ok &= check("accepted_count includes hired invite", r1row["accepted_count"] == 1)
ok &= check("unread_responses counts responses never viewed",
            r1row["unread_responses"] >= 1)
touch_role_viewed(econn, r1["id"])
import time as _t2
_t2.sleep(1.05)  # sqlite datetime second resolution
r1row = [r for r in list_roles(econn, emp_id) if r["id"] == r1["id"]][0]
ok &= check("unread_responses drops to 0 after touch_role_viewed",
            r1row["unread_responses"] == 0)
ok &= check("list_roles status filter",
            all(r["status"] == "closed" for r in list_roles(econn, emp_id, status="closed")))

# 25. shortlist cache
rows = [{"candidate_user_id": "cand-1", "fit_score": 88, "reason": "strong"},
        {"candidate_user_id": "cand-2", "fit_score": 70, "reason": "ok"},
        {"candidate_user_id": "cand-3", "fit_score": 60, "reason": "meh"}]
written = replace_shortlist(econn, r2["id"], rows)
ok &= check("replace_shortlist writes rows", written == 3)
sl = list_shortlist(econn, r2["id"])
ok &= check("shortlist hides candidates who are NOT opted in (cand-2)",
            [s["candidate_user_id"] for s in sl] == ["cand-1", "cand-3"])
ok &= check("shortlist joined with twin data",
            sl[0]["twin"].get("name") == "Ada")
ok &= check("shortlist best fit first", sl[0]["fit_score"] == 88)
ok &= check("count_shortlist respects visibility", count_shortlist(econn, r2["id"]) == 2)
ok &= check("cache age is a small non-negative integer",
            0 <= (shortlist_cache_age_seconds(econn, r2["id"]) or 0) < 60)
inv6 = create_invite(econn, r2["id"], "cand-3", "hm-1")
sl = list_shortlist(econn, r2["id"])
c3 = [s for s in sl if s["candidate_user_id"] == "cand-3"][0]
ok &= check("already_invited flag set after invite", c3["already_invited"] is True)
clear_shortlist(econn, r2["id"])
ok &= check("clear_shortlist empties cache + age None",
            list_shortlist(econn, r2["id"]) == []
            and shortlist_cache_age_seconds(econn, r2["id"]) is None)

# 26. credits: purchase, replay protection, balance, unlock spend
ok &= check("balance starts at 0", credit_balance(econn, emp_id) == 0)
ok &= check("add_credits purchase", add_credits(econn, emp_id, 5, "purchase", "ref_1") is True)
ok &= check("balance reflects purchase", credit_balance(econn, emp_id) == 5)
ok &= check("webhook replay (same reference) never double-credits",
            add_credits(econn, emp_id, 5, "purchase", "ref_1") is False
            and credit_balance(econn, emp_id) == 5)
ok &= check("unlock spends one credit",
            create_unlock(econn, r2["id"], emp_id, "cand-1", "hm-1") == "ok"
            and credit_balance(econn, emp_id) == 4
            and is_unlocked(econn, r2["id"], "cand-1") is True)
ok &= check("unlock is idempotent per (role, candidate) — no double spend",
            create_unlock(econn, r2["id"], emp_id, "cand-1", "hm-1") == "exists"
            and credit_balance(econn, emp_id) == 4)
econn.execute("INSERT INTO employer_credit_ledger (employer_id, delta, reason) "
              "VALUES (?, -4, 'admin_grant')", (emp_id,))
econn.commit()
ok &= check("unlock with zero balance refused",
            create_unlock(econn, r2["id"], emp_id, "cand-3", "hm-1") == "no_credits"
            and is_unlocked(econn, r2["id"], "cand-3") is False)

# 27. clear_user: candidate side wipes invites/shortlists/unlocks
replace_shortlist(econn, r2["id"], [{"candidate_user_id": "cand-1", "fit_score": 88,
                                     "reason": "strong"}])
clear_user(econn, "cand-1")
ok &= check("clear_user wipes candidate's invites",
            list_candidate_invites(econn, "cand-1") == []
            and econn.execute("SELECT COUNT(*) FROM interview_invites "
                              "WHERE candidate_user_id='cand-1'").fetchone()[0] == 0)
ok &= check("clear_user wipes candidate's shortlist rows",
            econn.execute("SELECT COUNT(*) FROM role_shortlists "
                          "WHERE candidate_user_id='cand-1'").fetchone()[0] == 0)
ok &= check("clear_user wipes candidate's unlock rows",
            is_unlocked(econn, r2["id"], "cand-1") is False)
ok &= check("clear_user leaves other candidates' invites intact",
            get_invite(econn, inv6) is not None)

# 28. clear_user: employer side closes open roles, drops membership, keeps employers row
emp2 = create_employer(econn, "Halo Ltd", "halo.com", "hm-2")
r4 = create_role(econn, emp2, "hm-2", {"title": "VA", "description": "Assist"})
clear_user(econn, "hm-2")
ok &= check("clear_user closes the employer's open roles",
            get_role(econn, r4["id"])["status"] == "closed")
ok &= check("clear_user drops employer_users membership",
            get_employer_for_user(econn, "hm-2") is None)
ok &= check("employers row survives for audit",
            get_employer(econn, emp2) is not None)

print("\n" + ("ALL TESTS PASSED ✅" if ok else "SOME TESTS FAILED ❌"))
sys.exit(0 if ok else 1)
