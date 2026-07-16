"""Worker 6 — expire pending interview invites whose expires_at has passed.

Nightly. Pending invites carry a 14-day expiry (set at creation); the
candidate-facing accept endpoint already refuses stale invites defensively,
but this worker is what moves them to 'expired' so employer role views and
candidate tabs stay honest without waiting for someone to click.

Run: python3 workers/expire_invites.py [--db PATH]
Scheduled via POST /admin/run/expire-invites (Render Cron curl trigger —
cron jobs can't mount the disk; see render.yaml).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db


def run(db_path: str) -> dict:
    conn = db.connect(db_path, check_same_thread=False)
    cur = conn.execute(
        "UPDATE interview_invites SET status = 'expired' "
        "WHERE status = 'pending' AND expires_at < datetime('now')")
    conn.commit()
    result = {"ok": True, "expired": cur.rowcount}
    db.log_event(conn, "ExpireInvitesRun", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=os.getenv("EMPLOI_DB_PATH", "emploi.sqlite3"))
    args = parser.parse_args()
    result = run(args.db)
    print(result)
    sys.exit(0 if result["ok"] else 1)
