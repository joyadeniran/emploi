"""Worker 5 — daily SQLite backup to Cloudflare R2 (HANDOVER §13, Option B).

A raw file copy of a live WAL database can be torn mid-write, so the snapshot
is taken with SQLite's online backup API and integrity-checked before upload.
Upload I/O is injectable (`upload_fn`) so tests stay offline; the default
uploader reads R2_* env vars and uses boto3 (lazy import — the rest of the
app never needs it). Missing configuration is a clean, honest failure:
nothing is uploaded, nothing pretends to have been.
"""
import argparse, datetime, os, sqlite3, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db

_R2_VARS = ("R2_ENDPOINT", "R2_ACCESS_KEY", "R2_SECRET_KEY", "R2_BUCKET")


def _default_upload(local_path, key):
    missing = [v for v in _R2_VARS if not os.getenv(v)]
    if missing:
        raise RuntimeError("R2 not configured (missing %s)" % ", ".join(missing))
    import boto3  # lazy: only the backup cron needs it
    s3 = boto3.client(
        "s3",
        endpoint_url=os.getenv("R2_ENDPOINT"),
        aws_access_key_id=os.getenv("R2_ACCESS_KEY"),
        aws_secret_access_key=os.getenv("R2_SECRET_KEY"),
    )
    s3.upload_file(local_path, os.getenv("R2_BUCKET"), key)


def run(db_path, dry_run=False, upload_fn=None):
    if not os.path.exists(db_path):
        return {"ok": False, "error": "database file not found: %s" % db_path}
    upload_fn = upload_fn or _default_upload
    key = "backups/emploi-%s.sqlite3" % datetime.date.today().isoformat()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            snap_path = os.path.join(tmp, "snapshot.sqlite3")
            src = sqlite3.connect(db_path)
            dst = sqlite3.connect(snap_path)
            try:
                src.backup(dst)  # consistent even against concurrent writers
            finally:
                dst.close(); src.close()
            checker = sqlite3.connect(snap_path)
            try:
                verdict = checker.execute("PRAGMA quick_check").fetchone()[0]
            finally:
                checker.close()
            if verdict != "ok":
                return {"ok": False, "error": "snapshot failed integrity check: %s" % verdict}
            size = os.path.getsize(snap_path)
            if dry_run:
                return {"ok": True, "dry_run": True, "key": key, "bytes": size}
            upload_fn(snap_path, key)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    result = {"ok": True, "dry_run": False, "key": key, "bytes": size}
    try:
        conn = db.connect(db_path, check_same_thread=False)
        db.log_event(conn, "BackupWorkerRun", result)
        conn.close()
    except Exception:
        pass  # the backup itself succeeded; event logging is best-effort
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=os.getenv("EMPLOI_DB_PATH", "emploi.sqlite3"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = run(args.db, args.dry_run)
    print(result)
    sys.exit(0 if result["ok"] else 1)
