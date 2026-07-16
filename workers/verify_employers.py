"""Worker 2 — refresh trustworthy employer records for direct company domains.

Prefers `ingested_jobs.company_domain` when set (populated by the ingest
worker's `_derive_company_domain` heuristic at write time) — this lets an
ATS-hosted job (greenhouse.io / lever.co / ashbyhq.com / apply.workable.com /
jobs.smartrecruiters.com) still be verified against the employer's actual
domain instead of the ATS host. Rows without a guessed domain fall back to
extracting from apply_url, and ATS hosts are still skipped there.

Candidates can always run the normal Trust Check for an employer found
elsewhere.
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

# ATS hostnames that should never be trust-checked as the employer. Also
# used to filter out a guessed company_domain that accidentally coincides
# with an ATS (defensive; the ingest heuristic shouldn't produce these).
ATS_HOSTS = (
    "greenhouse.io", "lever.co", "ashbyhq.com",
    "workable.com", "smartrecruiters.com",
)


def _is_ats_host(domain: str) -> bool:
    return any(domain == host or domain.endswith("." + host) for host in ATS_HOSTS)


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
    # Prefer company_domain (populated by the ingest heuristic) over
    # apply_url extraction. Order by company_domain-first so that when two
    # rows disagree the guessed domain wins (fixes the ATS-attribution bug).
    rows = conn.execute(
        "SELECT DISTINCT company_domain, apply_url, company_name "
        "FROM ingested_jobs "
        "WHERE company_domain IS NOT NULL "
        "   OR (apply_url IS NOT NULL AND apply_url != '') "
        "LIMIT ?", (max_domains,)).fetchall()
    # Phase 2: registered Employer Portal accounts get the same freshness
    # refresh on their own domain. Vouched employers (warm_intro_by set) are
    # skipped — Joy vouches for them personally. Keep the ATS filter
    # defensively even though employers should never carry an ATS host.
    employer_rows = conn.execute(
        "SELECT DISTINCT company_domain, company_name FROM employers "
        "WHERE company_domain IS NOT NULL AND warm_intro_by IS NULL").fetchall()
    targets = []
    seen = set()
    for row in list(rows) + [
            {"company_domain": r["company_domain"], "apply_url": "",
             "company_name": r["company_name"]} for r in employer_rows]:
        domain = (row["company_domain"] or "").lower().strip() or None
        if not domain:
            domain = _domain(row["apply_url"])
        if not domain or _is_ats_host(domain) or domain in seen:
            continue
        seen.add(domain)
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
            # Registered employer accounts on this domain get the refreshed
            # score written back (portal-level mapping), unless vouched.
            for emp in conn.execute(
                    "SELECT id FROM employers WHERE company_domain = ? "
                    "AND warm_intro_by IS NULL", (domain,)).fetchall():
                level = verify.employer_portal_level(
                    result.get("score"),
                    (result.get("signals") or {}).get("red_flags"),
                    result.get("signals"))
                db.set_employer_trust(conn, emp["id"], result.get("score"), level)
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
