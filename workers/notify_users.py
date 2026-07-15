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
        if not resp.ok:
            # Brevo's error body names the real cause (invalid key, IP not
            # whitelisted, unverified sender, ...) — raise_for_status()
            # alone discards it, leaving only a generic "401 Unauthorized"
            # that's useless for diagnosing which of those it actually is.
            raise RuntimeError(f"Brevo {resp.status_code}: {resp.text[:300]}")
    return _send


def _get_send_fn():
    api_key = os.getenv("BREVO_API_KEY", "")
    sender = os.getenv("BREVO_SENDER_EMAIL", "")
    if not api_key or not sender:
        return None
    return brevo_send_fn(api_key, sender)

def run(db_path, dry_run=False, send_fn=None):
    conn = db.connect(db_path, check_same_thread=False)
    # LEFT JOIN the new `users` table (source of truth for email + digest
    # opt-in) with the legacy career_twins.data.email fallback. This keeps
    # pre-users-table twins receiving digests for one release while the web
    # tier's POST /user/session backfills them.
    rows = conn.execute(
        "SELECT m.user_id, COUNT(*) n, MAX(m.fit_score) top, ct.data, "
        "u.email AS user_email, u.name AS user_name, "
        "COALESCE(u.notifications_enabled, 1) AS notifications_enabled "
        "FROM matches m "
        "JOIN career_twins ct ON ct.user_id = m.user_id "
        "LEFT JOIN users u ON u.id = m.user_id "
        "WHERE m.notified = 0 GROUP BY m.user_id").fetchall()
    # `sent: 0` alone is ambiguous (no users? no emails? no sender?) — count
    # every skip reason so a quiet run is diagnosable from the summary alone.
    sent, skipped_no_email, skipped_opted_out, send_failures = 0, 0, 0, []
    for row in rows:
        # Respect the user's opt-out even before we look at email — an
        # opted-out user with no email should still count as opted-out,
        # not "missing email" (avoids re-nudging Joy to fix a backfill
        # that isn't the real issue).
        if not int(row["notifications_enabled"]):
            skipped_opted_out += 1
            continue
        try: twin = json.loads(row["data"])
        except Exception: twin = {}
        # users.email wins; career_twins.data.email is the legacy fallback.
        email = row["user_email"] or (twin.get("email") if isinstance(twin, dict) else None)
        if not email:
            skipped_no_email += 1
            continue
        name = row["user_name"] or (twin.get("name") if isinstance(twin, dict) else None)
        subject = f"Your Career Twin found {row['n']} new jobs for you"
        body_parts = [
            f"Hi {name or 'there'},",
            "",
            f"Your Career Twin found {row['n']} new matches. "
            f"Best fit: {row['top']}/100.",
            "",
            "https://app.emploihq.com/matches",
        ]
        # Outcome-tracking nudge: applications still `applied` 14+ days ago
        # with no user update get a "how did it go?" prompt appended. Capped
        # at 5 (default in db.list_applications_needing_outcome_nudge) so the
        # email doesn't feel like homework.
        stale = db.list_applications_needing_outcome_nudge(conn, row["user_id"])
        if stale:
            body_parts += ["", "How did these go?"]
            for app_ in stale:
                role = (app_.get("role") or "").strip()
                company = (app_.get("company") or "").strip()
                if role and company:
                    label = role + " at " + company
                elif role:
                    label = role
                elif company:
                    label = company
                else:
                    label = "Application #" + str(app_["id"])
                body_parts.append("- " + label)
            body_parts += ["",
                           "Update the status here: https://app.emploihq.com/applications"]
        body = "\n".join(body_parts)
        if not dry_run and send_fn:
            try: send_fn(email, subject, body)
            except Exception as exc:
                send_failures.append(str(exc)[:200])
                continue
        elif not dry_run:
            continue
        if not dry_run:
            conn.execute("UPDATE matches SET notified=1, notified_at=datetime('now') WHERE user_id=? AND notified=0", (row["user_id"],)); conn.commit()
        sent += 1
    result = {"ok": True, "sent": sent, "users_with_unnotified": len(rows),
              "skipped_no_email": skipped_no_email,
              "skipped_opted_out": skipped_opted_out,
              "sender_configured": send_fn is not None,
              "send_failures": send_failures, "dry_run": dry_run}
    if not dry_run: db.log_event(conn, "NotificationWorkerRun", result)
    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--db", default=os.getenv("EMPLOI_DB_PATH", "emploi.sqlite3")); parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = run(args.db, args.dry_run, send_fn=_get_send_fn())
    sys.exit(0 if result["ok"] else 1)
