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

# ---- Brevo sender (mocked HTTP, no real network/API key) -------------------
with patch("requests.post") as mock_post:
    mock_post.return_value = MagicMock(status_code=201, raise_for_status=lambda: None)
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
    mock_post.return_value = MagicMock(status_code=401)
    mock_post.return_value.raise_for_status.side_effect = Exception("401 unauthorized")
    send = brevo_send_fn("bad-key", "hello@emploihq.com")
    try:
        send("user@example.com", "s", "b")
        check("brevo_send_fn raises on a failed send", False)
    except Exception:
        check("brevo_send_fn raises on a failed send", True)

check("_get_send_fn returns None when BREVO_API_KEY/SENDER_EMAIL unset",
      _get_send_fn() is None)
with patch.dict(os.environ, {"BREVO_API_KEY": "k", "BREVO_SENDER_EMAIL": "s@emploihq.com"}):
    check("_get_send_fn returns a callable once configured", callable(_get_send_fn()))

if fails: raise SystemExit(1)
print("ALL TESTS PASSED ✅")
