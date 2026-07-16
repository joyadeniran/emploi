"""Offline checks for notification digests."""
import os, tempfile
from unittest.mock import patch, MagicMock
import db
from workers.notify_users import run, brevo_send_fn, _get_send_fn
fails=[]
def check(label, ok):
 print(("PASS" if ok else "FAIL"), "-", label); fails.extend([] if ok else [label])
with tempfile.TemporaryDirectory() as d:
 path=os.path.join(d,"n.sqlite3"); conn=db.connect(path)
 db.save_career_twin(conn,"u",{"name":"Ada","email":"ada@example.com"})
 job=db.upsert_job(conn,"t","1",{"title":"Engineer","company_name":"Acme"}); db.upsert_match(conn,"u",job,90,"fit")
 calls=[]; result=run(path,send_fn=lambda *args: calls.append(args))
 check("sends one digest", result["sent"]==1 and len(calls)==1)
 check("marks sent matches", conn.execute("SELECT notified FROM matches").fetchone()[0]==1)
 check("second run sends nothing", run(path,send_fn=lambda *args: calls.append(args))["sent"]==0)
 # Diagnostics: sent:0 must be explainable from the summary alone
 db.save_career_twin(conn,"noemail",{"name":"Bola"})  # twin without email
 job2=db.upsert_job(conn,"t","2",{"title":"PM","company_name":"Acme"}); db.upsert_match(conn,"noemail",job2,80,"fit")
 r2=run(path,send_fn=lambda *args: None)
 check("summary counts users skipped for missing email", r2["skipped_no_email"]==1 and r2["sent"]==0)
 check("summary reports sender_configured", r2["sender_configured"] is True)
 r3=run(path,send_fn=None)
 check("summary shows unconfigured sender honestly", r3["sender_configured"] is False)

 # Users table wins over career_twins.data.email — a twin without an email
 # blob field still gets a digest if the users row has one. And a user's
 # notifications_enabled=false must be respected regardless of email presence.
 db.save_career_twin(conn, "u2", {"name": "Chi"})  # no email in blob
 db.upsert_user(conn, "u2", "chi@example.com", "Chi Nwosu")
 job3 = db.upsert_job(conn, "t", "3", {"title": "Data", "company_name": "Acme"})
 db.upsert_match(conn, "u2", job3, 88, "fit")
 sent = []
 r4 = run(path, send_fn=lambda to, s, b: sent.append(to))
 check("users.email wins when career_twins.data.email is missing",
       "chi@example.com" in sent)

 # Opt out — user u3 with digests disabled must be skipped even with email.
 db.save_career_twin(conn, "u3", {"name": "Dami"})
 db.upsert_user(conn, "u3", "dami@example.com", "Dami")
 db.set_notifications_enabled(conn, "u3", False)
 job4 = db.upsert_job(conn, "t", "4", {"title": "Ops", "company_name": "Acme"})
 db.upsert_match(conn, "u3", job4, 75, "fit")
 sent5 = []
 r5 = run(path, send_fn=lambda to, s, b: sent5.append(to))
 check("opted-out user is skipped even with a valid email",
       "dami@example.com" not in sent5 and r5["skipped_opted_out"] >= 1)
 # And the match stays unnotified — we must not mark it sent for an opt-out.
 check("opted-out user's matches remain unnotified for a later run",
       conn.execute("SELECT notified FROM matches WHERE user_id='u3'").fetchone()[0] == 0)

 # Outcome-tracking nudge: an applied application > 14 days old with no
 # outcome update shows up in the digest as a "how did it go?" prompt.
 db.save_career_twin(conn, "u4", {"name": "Ejike"})
 db.upsert_user(conn, "u4", "ejike@example.com", "Ejike")
 app_stale = db.add_application(conn, "u4", {"company": "Kuda",
                                              "role": "Senior BE",
                                              "status": "applied"})
 # Backdate the application to 20 days ago so it qualifies for the nudge.
 conn.execute("UPDATE applications SET created_at=datetime('now', '-20 days'), "
              "outcome_updated_at=NULL WHERE id=?", (app_stale,))
 conn.commit()
 job5 = db.upsert_job(conn, "t", "5", {"title": "Data", "company_name": "Acme"})
 db.upsert_match(conn, "u4", job5, 82, "fit")
 bodies = []
 run(path, send_fn=lambda to, s, b: bodies.append(b))
 check("stale applied → digest contains How did these go? prompt",
       any("How did these go?" in b for b in bodies))
 check("digest names the stale application (role at company)",
       any("Senior BE at Kuda" in b for b in bodies))
 check("digest links to /applications for updating status",
       any("/applications" in b for b in bodies))

 # A recent applied application (2 days ago) must NOT trigger the nudge.
 db.save_career_twin(conn, "u5", {"name": "Fola"})
 db.upsert_user(conn, "u5", "fola@example.com", "Fola")
 app_fresh = db.add_application(conn, "u5", {"company": "Chime",
                                              "role": "PM",
                                              "status": "applied"})
 conn.execute("UPDATE applications SET created_at=datetime('now', '-2 days'), "
              "outcome_updated_at=NULL WHERE id=?", (app_fresh,))
 conn.commit()
 job6 = db.upsert_job(conn, "t", "6", {"title": "Design",
                                        "company_name": "Acme"})
 db.upsert_match(conn, "u5", job6, 65, "fit")
 fresh_bodies = []
 run(path, send_fn=lambda to, s, b: (
     fresh_bodies.append(b) if to == "fola@example.com" else None))
 check("recent applied (< 14d) does NOT trigger a nudge",
       all("How did these go?" not in b for b in fresh_bodies))

# ---- Phase 2: interview-invite digests --------------------------------------
with tempfile.TemporaryDirectory() as d:
 path=os.path.join(d,"inv.sqlite3"); conn=db.connect(path)
 emp=db.create_employer(conn,"Acme Corp","acme.com","hm-1")
 db.update_employer(conn,emp,trust_score=80,trust_level="high")
 role=db.create_role(conn,emp,"hm-1",{"title":"Data Analyst","description":"d","is_remote":True})
 # Candidate WITH a fresh invite but NO new matches must still get a digest.
 db.save_career_twin(conn,"ci",{"name":"Ada"})
 db.upsert_user(conn,"ci","ada@example.com","Ada")
 db.create_invite(conn,role["id"],"ci","hm-1",fit_score=88)
 bodies=[]; subjects=[]
 r=run(path,send_fn=lambda to,s,b:(subjects.append(s),bodies.append(b)))
 check("invite-only candidate still gets a digest", r["sent"]==1)
 check("invite digest subject names the invite",
       any("interview invite" in s for s in subjects))
 check("invite digest line has company, role, Remote and trust level",
       any("Acme Corp — Data Analyst (Remote) — trust high" in b for b in bodies))
 check("invite digest links /invites", any("app.emploihq.com/invites" in b for b in bodies))
 # Dedup: the same invite must not ride a second nightly digest.
 check("invite marked notified after the digest",
       conn.execute("SELECT notified FROM interview_invites").fetchone()[0]==1)
 r2=run(path,send_fn=lambda to,s,b: bodies.append(b))
 check("an invite rides exactly one digest (notified flag)", r2["sent"]==0)
 # A user with matches AND a fresh invite gets ONE email with both sections.
 db.save_career_twin(conn,"cm",{"name":"Bola"})
 db.upsert_user(conn,"cm","bola@example.com","Bola")
 j=db.upsert_job(conn,"t","1",{"title":"PM","company_name":"Halo"})
 db.upsert_match(conn,"cm",j,82,"fit")
 db.create_invite(conn,role["id"],"cm","hm-1")
 both=[]
 r3=run(path,send_fn=lambda to,s,b: both.append((to,s,b)))
 check("matches + invite in one digest",
       r3["sent"]==1 and "new jobs" in both[0][1]
       and "interview invites" in both[0][2] and "matches" in both[0][2])
 # An EXPIRED pending invite never appears in a digest.
 db.save_career_twin(conn,"ce",{"name":"Chi"})
 db.upsert_user(conn,"ce","chi@example.com","Chi")
 inv=db.create_invite(conn,role["id"],"ce","hm-1")
 conn.execute("UPDATE interview_invites SET expires_at = datetime('now', '-1 days') WHERE id=?",(inv,))
 conn.commit()
 r4=run(path,send_fn=lambda to,s,b: None)
 check("expired invite never advertised in a digest", r4["sent"]==0)
 # dry-run reports without sending
 db.save_career_twin(conn,"cd",{"name":"Didi"})
 db.upsert_user(conn,"cd","didi@example.com","Didi")
 db.create_invite(conn,role["id"],"cd","hm-1")
 sent_dry=[]
 r5=run(path,dry_run=True,send_fn=lambda *a: sent_dry.append(a))
 check("dry-run counts invite digests but sends nothing",
       r5["dry_run"] is True and r5["sent"]>=1 and sent_dry==[])

# ---- Brevo sender (mocked HTTP, no real network/API key) -------------------
with patch("requests.post") as mock_post:
    mock_post.return_value = MagicMock(status_code=201, ok=True)
    send = brevo_send_fn("fake-key", "hello@emploihq.com")
    send("user@example.com", "subject", "body")
    args, kwargs = mock_post.call_args
    check("brevo_send_fn posts to the Brevo API", args[0] == "https://api.brevo.com/v3/smtp/email")
    check("brevo_send_fn sends the api-key header", kwargs["headers"]["api-key"] == "fake-key")
    check("brevo_send_fn payload has sender/to/subject/textContent",
          kwargs["json"]["sender"]["email"] == "hello@emploihq.com"
          and kwargs["json"]["to"] == [{"email": "user@example.com"}]
          and kwargs["json"]["textContent"] == "body")

with patch("requests.post") as mock_post:
    mock_post.return_value = MagicMock(
        status_code=401, ok=False,
        text='{"code":"unauthorized","message":"Key not found"}')
    send = brevo_send_fn("bad-key", "hello@emploihq.com")
    try:
        send("user@example.com", "s", "b")
        check("brevo_send_fn raises on a failed send", False)
    except RuntimeError as exc:
        check("brevo_send_fn raises on a failed send", True)
        check("brevo_send_fn surfaces Brevo's actual error body, not just the status code",
              "Key not found" in str(exc))

check("_get_send_fn returns None when BREVO_API_KEY/SENDER_EMAIL unset",
      _get_send_fn() is None)
with patch.dict(os.environ, {"BREVO_API_KEY": "k", "BREVO_SENDER_EMAIL": "s@emploihq.com"}):
    check("_get_send_fn returns a callable once configured", callable(_get_send_fn()))

if fails: raise SystemExit(1)
print("ALL TESTS PASSED ✅")
