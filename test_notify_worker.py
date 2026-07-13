"""Offline checks for notification digests."""
import os, tempfile
import db
from workers.notify_users import run
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
if fails: raise SystemExit(1)
print("ALL TESTS PASSED ✅")
