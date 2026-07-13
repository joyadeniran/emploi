"""Offline checks for the DB backup worker (Worker 5)."""
import os, sqlite3, tempfile
import db
from workers.backup_db import run
fails = []
def check(label, ok):
    print(("PASS" if ok else "FAIL"), "-", label); fails.extend([] if ok else [label])

with tempfile.TemporaryDirectory() as d:
    path = os.path.join(d, "b.sqlite3")
    conn = db.connect(path)
    db.save_career_twin(conn, "u1", {"name": "Ada"})

    # 1. Happy path: snapshot uploaded once, key dated, snapshot is a valid DB
    calls = []
    def fake_upload(local_path, key):
        calls.append((local_path, key))
        # snapshot must be a consistent, queryable SQLite file at upload time
        c = sqlite3.connect(local_path)
        row = c.execute("SELECT user_id FROM career_twins").fetchone()
        c.close()
        assert row[0] == "u1"
    result = run(path, upload_fn=fake_upload)
    check("backup succeeds", result["ok"] is True)
    check("uploads exactly once", len(calls) == 1)
    check("key is dated sqlite3 object", calls[0][1].startswith("backups/emploi-") and calls[0][1].endswith(".sqlite3"))
    check("reports snapshot size", result.get("bytes", 0) > 0)

    # 2. Dry run: no upload, still ok
    calls2 = []
    r2 = run(path, dry_run=True, upload_fn=lambda p, k: calls2.append(k))
    check("dry run ok", r2["ok"] is True and r2["dry_run"] is True)
    check("dry run uploads nothing", calls2 == [])

    # 3. Upload failure: clean error, no exception
    r3 = run(path, upload_fn=lambda p, k: (_ for _ in ()).throw(RuntimeError("boom")))
    check("upload failure returns ok=False", r3["ok"] is False and "boom" in r3.get("error", ""))

    # 4. Missing DB file: clean error
    r4 = run(os.path.join(d, "missing.sqlite3"), upload_fn=lambda p, k: None)
    check("missing db returns ok=False", r4["ok"] is False)

    # 5. No upload seam and no R2 env: clean 'not configured' error, never fabricates success
    for var in ("R2_ENDPOINT", "R2_ACCESS_KEY", "R2_SECRET_KEY", "R2_BUCKET"):
        os.environ.pop(var, None)
    r5 = run(path)
    check("unconfigured R2 returns ok=False", r5["ok"] is False and "R2" in r5.get("error", ""))

if fails:
    raise SystemExit(1)
print("ALL TESTS PASSED ✅")
