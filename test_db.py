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

print("\n" + ("ALL TESTS PASSED ✅" if ok else "SOME TESTS FAILED ❌"))
sys.exit(0 if ok else 1)
