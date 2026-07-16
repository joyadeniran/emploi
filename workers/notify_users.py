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

def _pending_invites(conn, user_id):
    """Un-notified pending interview invites for one candidate (Phase 2).
    The `notified` flag is the dedup — an invite rides exactly one digest,
    then the dashboard badge takes over. Same pattern as matches.notified."""
    return conn.execute(
        "SELECT ii.id, ii.invite_note, ii.fit_score, ii.expires_at, "
        "       er.title AS role_title, er.location AS role_location, er.is_remote, "
        "       e.company_name, e.trust_score, e.trust_level "
        "FROM interview_invites ii "
        "JOIN employer_roles er ON er.id = ii.employer_role_id "
        "JOIN employers e ON e.id = er.employer_id "
        "WHERE ii.candidate_user_id = ? "
        "  AND ii.status = 'pending' "
        "  AND ii.notified = 0 "
        "  AND ii.expires_at > datetime('now') "
        "ORDER BY ii.created_at DESC LIMIT 5", (user_id,)).fetchall()


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
    # Phase 2: candidates with FRESH pending invites must hear about them even
    # with zero new matches — an invite expires in 14 days and email is the
    # channel. (Deviation from the spec snippet, which only decorated the
    # matches digest; flagged in the CHANGELOG.) Same email/opt-in columns.
    match_user_ids = {r["user_id"] for r in rows}
    invite_only_rows = [r for r in conn.execute(
        "SELECT DISTINCT ii.candidate_user_id AS user_id, NULL AS n, NULL AS top, "
        "ct.data, u.email AS user_email, u.name AS user_name, "
        "COALESCE(u.notifications_enabled, 1) AS notifications_enabled "
        "FROM interview_invites ii "
        "JOIN career_twins ct ON ct.user_id = ii.candidate_user_id "
        "LEFT JOIN users u ON u.id = ii.candidate_user_id "
        "WHERE ii.status = 'pending' AND ii.notified = 0 "
        "  AND ii.expires_at > datetime('now')").fetchall()
        if r["user_id"] not in match_user_ids]
    # `sent: 0` alone is ambiguous (no users? no emails? no sender?) — count
    # every skip reason so a quiet run is diagnosable from the summary alone.
    sent, skipped_no_email, skipped_opted_out, send_failures = 0, 0, 0, []
    for row in list(rows) + invite_only_rows:
        has_matches = row["n"] is not None
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
        pending_invites = _pending_invites(conn, row["user_id"])
        if has_matches:
            subject = f"Your Career Twin found {row['n']} new jobs for you"
            body_parts = [
                f"Hi {name or 'there'},",
                "",
                f"Your Career Twin found {row['n']} new matches. "
                f"Best fit: {row['top']}/100.",
                "",
                "https://app.emploihq.com/matches",
            ]
        elif pending_invites:
            plural = "s" if len(pending_invites) != 1 else ""
            subject = f"You have {len(pending_invites)} new interview invite{plural}"
            body_parts = [f"Hi {name or 'there'},"]
        else:
            continue  # nothing to say
        if pending_invites:
            body_parts += ["", "You have new interview invites:"]
            for inv in pending_invites:
                body_parts.append(
                    f"- {inv['company_name']} — {inv['role_title']} "
                    f"({'Remote' if inv['is_remote'] else (inv['role_location'] or 'Location unspecified')}) "
                    f"— trust {inv['trust_level'] or 'unverified'}")
            body_parts += ["", "Review them: https://app.emploihq.com/invites"]
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
        if not dry_run and has_matches:
            conn.execute("UPDATE matches SET notified=1, notified_at=datetime('now') WHERE user_id=? AND notified=0", (row["user_id"],)); conn.commit()
        if not dry_run and pending_invites:
            conn.execute(
                "UPDATE interview_invites SET notified=1, notified_at=datetime('now') "
                "WHERE id IN (%s)" % ",".join("?" * len(pending_invites)),
                [inv["id"] for inv in pending_invites])
            conn.commit()
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
