"""Worker 4 — one email digest per user for unnotified matches.

Production sender: Brevo transactional email API (api.brevo.com/v3/smtp/email).
Needs BREVO_API_KEY + BREVO_SENDER_EMAIL (verified sender in Brevo) set in the
cron's env. Missing config -> the worker still runs and logs but sends nothing,
same as the DB-backup worker's hard-fail-honest posture, except here a no-op
is safe: no send_fn means no email claims a delivery that didn't happen.
"""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db


def brevo_send_fn(api_key: str, sender_email: str, sender_name: str = "Emploi Career Twin"):
    """Return a send_fn(email, subject, body) that posts to Brevo's transactional API.
    Raises on non-2xx so the caller's try/except correctly skips marking as sent."""
    import requests

    def _send(to_email: str, subject: str, body: str):
        resp = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": api_key, "Content-Type": "application/json"},
            json={
                "sender": {"email": sender_email, "name": sender_name},
                "to": [{"email": to_email}],
                "subject": subject,
                "textContent": body,
            },
            timeout=10,
        )
        resp.raise_for_status()
    return _send


def _get_send_fn():
    api_key = os.getenv("BREVO_API_KEY", "")
    sender = os.getenv("BREVO_SENDER_EMAIL", "")
    if not api_key or not sender:
        return None
    return brevo_send_fn(api_key, sender)

def run(db_path, dry_run=False, send_fn=None):
    conn = db.connect(db_path, check_same_thread=False)
    rows = conn.execute("SELECT m.user_id, COUNT(*) n, MAX(m.fit_score) top, ct.data "
                        "FROM matches m JOIN career_twins ct ON ct.user_id=m.user_id "
                        "WHERE m.notified=0 GROUP BY m.user_id").fetchall()
    sent = 0
    for row in rows:
        try: twin = json.loads(row["data"])
        except Exception: twin = {}
        email = twin.get("email") if isinstance(twin, dict) else None
        if not email: continue
        subject = f"Your Career Twin found {row['n']} new jobs for you"
        body = f"Hi {twin.get('name') or 'there'},\n\nYour Career Twin found {row['n']} new matches. Best fit: {row['top']}/100.\n\nhttps://app.emploihq.com/matches"
        if not dry_run and send_fn:
            try: send_fn(email, subject, body)
            except Exception: continue
        elif not dry_run:
            continue
        if not dry_run:
            conn.execute("UPDATE matches SET notified=1, notified_at=datetime('now') WHERE user_id=? AND notified=0", (row["user_id"],)); conn.commit()
        sent += 1
    result = {"ok": True, "sent": sent, "dry_run": dry_run}
    if not dry_run: db.log_event(conn, "NotificationWorkerRun", result)
    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--db", default=os.getenv("EMPLOI_DB_PATH", "emploi.sqlite3")); parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = run(args.db, args.dry_run, send_fn=_get_send_fn())
    sys.exit(0 if result["ok"] else 1)
