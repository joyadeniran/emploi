"""Offline checks for the employer-verification refresh worker."""
import os
import tempfile
import db
from workers.verify_employers import run

fails = []
def check(label, condition):
    print(("PASS" if condition else "FAIL"), "-", label)
    if not condition: fails.append(label)

with tempfile.TemporaryDirectory() as directory:
    path = os.path.join(directory, "test.sqlite3")
    conn = db.connect(path)
    db.upsert_job(conn, "direct", "1", {"company_name": "Acme", "apply_url": "https://acme.test/jobs"})
    db.upsert_job(conn, "greenhouse", "2", {"company_name": "Ignored", "apply_url": "https://boards.greenhouse.io/ignored/jobs/1"})
    result = run(path, dns_fn=lambda d: True, mx_fn=lambda d: True,
                 fetch_fn=lambda d: (200, ""), sleep_fn=lambda _: None)
    record = db.get_trust_record(conn, "acme.test")
    check("direct company domain is refreshed", result["ok"] and result["verified"] == 1 and record is not None)
    check("ATS hostname is skipped", db.get_trust_record(conn, "boards.greenhouse.io") is None)
    second = run(path, dns_fn=lambda d: (_ for _ in ()).throw(RuntimeError()),
                 mx_fn=lambda d: True, fetch_fn=lambda d: (200, ""), sleep_fn=lambda _: None)
    check("fresh record is not probed again", second["verified"] == 0)
    dry = run(path, dry_run=True, max_age_days=0, sleep_fn=lambda _: None)
    check("dry run never writes", dry["dry_run"] and dry["verified"] == 0)

if fails:
    raise SystemExit(f"{len(fails)} failures")
print("ALL TESTS PASSED ✅")
