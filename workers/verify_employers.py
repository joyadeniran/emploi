"""Worker 2 — refresh trustworthy employer records for direct company domains.

ATS hosts (Greenhouse, Lever, Ashby) are deliberately skipped: verifying an
ATS hostname would incorrectly label the employer as verified. Candidates can
always run the normal Trust Check for an employer found elsewhere.
"""
import argparse
import os
import sys
import time
from urllib.parse import urlparse
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db
import verify

ATS_HOSTS = ("greenhouse.io", "lever.co", "ashbyhq.com")


def _domain(url: str) -> Optional[str]:
    try:
        host = (urlparse(url).hostname or "").lower().strip(".")
        return host or None
    except Exception:
        return None


def run(db_path: str, dry_run: bool = False, max_domains: int = 200,
        max_age_days: int = 7, sleep_fn=time.sleep, model=None,
        dns_fn=verify.dns_resolves, mx_fn=verify.has_mx,
        fetch_fn=verify.fetch_site) -> dict:
    conn = db.connect(db_path, check_same_thread=False)
    rows = conn.execute("SELECT DISTINCT apply_url, company_name FROM ingested_jobs "
                        "WHERE apply_url IS NOT NULL AND apply_url != '' LIMIT ?",
                        (max_domains,)).fetchall()
    targets = []
    for row in rows:
        domain = _domain(row["apply_url"])
        if not domain or any(domain == host or domain.endswith("." + host) for host in ATS_HOSTS):
            continue
        existing = db.get_trust_record(conn, domain)
        if existing and conn.execute("SELECT datetime(?) >= datetime('now', ? || ' days')",
                                    (existing["last_checked_at"], f"-{max_age_days}")).fetchone()[0]:
            continue
        targets.append((domain, row["company_name"] or domain))
    verified, errors = 0, []
    for domain, company in targets:
        if dry_run:
            print(f"  [dry-run] would verify: {domain}")
            continue
        try:
            result = verify.verify_employer(company, domain, model=model, dns_fn=dns_fn,
                                             mx_fn=mx_fn, fetch_fn=fetch_fn, cache={})
            db.upsert_trust_record(conn, domain, company, result)
            verified += 1
        except Exception as exc:
            errors.append(f"{domain}: {exc}")
        sleep_fn(3)
    summary = {"ok": not errors, "verified": verified, "candidates": len(targets),
               "errors": errors, "dry_run": dry_run}
    if not dry_run:
        db.log_event(conn, "VerificationWorkerRun", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--db", default=os.getenv("EMPLOI_DB_PATH", "emploi.sqlite3"))
    parser.add_argument("--max-domains", type=int, default=200)
    args = parser.parse_args()
    result = run(args.db, args.dry_run, args.max_domains)
    sys.exit(0 if result["ok"] else 1)
