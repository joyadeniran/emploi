"""Offline checks for the invite-expiry worker (Phase 2).

Pending invites past expires_at flip to 'expired'; every other status is
untouched; the run logs an ExpireInvitesRun event. In-memory-style temp DB,
no network. Clock control via UPDATE (anti-flake rule: never sleep for time
semantics)."""
import os
import tempfile

import db
from workers.expire_invites import run

fails = []


def check(label, cond):
    print(("PASS" if cond else "FAIL"), "-", label)
    if not cond:
        fails.append(label)


with tempfile.TemporaryDirectory() as d:
    path = os.path.join(d, "x.sqlite3")
    conn = db.connect(path)

    emp = db.create_employer(conn, "Acme", "acme.com", "hm-1")
    role = db.create_role(conn, emp, "hm-1", {"title": "Analyst",
                                              "description": "desc"})
    db.save_career_twin(conn, "c1", {"name": "Ada"})
    db.save_career_twin(conn, "c2", {"name": "Bola"})
    db.save_career_twin(conn, "c3", {"name": "Chidi"})
    db.save_career_twin(conn, "c4", {"name": "Dayo"})

    stale_pending = db.create_invite(conn, role["id"], "c1", "hm-1")
    fresh_pending = db.create_invite(conn, role["id"], "c2", "hm-1")
    accepted = db.create_invite(conn, role["id"], "c3", "hm-1")
    declined = db.create_invite(conn, role["id"], "c4", "hm-1")
    db.respond_invite(conn, accepted, accept=True)
    db.respond_invite(conn, declined, accept=False, decline_reason="nope")

    # Backdate: stale_pending expired yesterday; accepted's expiry ALSO passed
    # (must stay accepted — only pending rows expire).
    conn.execute("UPDATE interview_invites SET expires_at = datetime('now', '-1 days') "
                 "WHERE id IN (?, ?)", (stale_pending, accepted))
    conn.commit()

    result = run(path)
    check("run ok with expired count", result["ok"] and result["expired"] == 1)
    check("stale pending invite -> expired",
          db.get_invite(conn, stale_pending)["status"] == "expired")
    check("fresh pending invite untouched",
          db.get_invite(conn, fresh_pending)["status"] == "pending")
    check("accepted invite untouched even past expires_at",
          db.get_invite(conn, accepted)["status"] == "accepted")
    check("declined invite untouched",
          db.get_invite(conn, declined)["status"] == "declined")

    events = conn.execute(
        "SELECT COUNT(*) FROM events WHERE type = 'ExpireInvitesRun'").fetchone()[0]
    check("ExpireInvitesRun event logged", events == 1)

    second = run(path)
    check("second run expires nothing (idempotent)", second["expired"] == 0)

if fails:
    raise SystemExit(f"{len(fails)} failures")
print("ALL TESTS PASSED ✅")
