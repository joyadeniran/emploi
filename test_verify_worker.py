"""Offline checks for the employer-verification refresh worker."""
import os
import tempfile
import db
from workers.verify_employers import run, _is_ats_host

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

# ---- company_domain heuristic — the ATS-attribution bug fix ----------------
# Rows written by the ingest worker now carry a guessed company_domain. Verify
# that (a) verify_employers prefers it over apply_url extraction, and (b) an
# ATS-hosted apply_url no longer results in the ATS being trust-checked.
with tempfile.TemporaryDirectory() as directory:
    path = os.path.join(directory, "cd.sqlite3")
    conn = db.connect(path)
    # A greenhouse-hosted job that now carries a guessed employer domain.
    # Before this fix: verify_employers extracted boards.greenhouse.io from
    # apply_url and skipped it (ATS host) — so this employer was NEVER
    # trust-checked despite being in the pipeline.
    db.upsert_job(conn, "greenhouse", "10", {
        "company_name": "Paystack",
        "apply_url": "https://boards.greenhouse.io/paystack/jobs/12345",
        "company_domain": "paystack.com",
    })
    # A workable-hosted job — same story with a different ATS.
    db.upsert_job(conn, "workable", "11", {
        "company_name": "FairMoney",
        "apply_url": "https://apply.workable.com/fairmoney/j/ABC123/",
        "company_domain": "fairmoney.com",
    })
    # A malformed apply_url with a valid guessed domain — the guess wins.
    db.upsert_job(conn, "lever", "12", {
        "company_name": "Kuda",
        "apply_url": "not://a/valid/url",
        "company_domain": "kuda.com",
    })
    # ATS-attribution defense: if the guessed domain accidentally IS an
    # ATS host (shouldn't happen with the current heuristic but defense
    # in depth), it must still be skipped.
    db.upsert_job(conn, "greenhouse", "13", {
        "company_name": "Ashby Corp",
        "apply_url": "https://boards.greenhouse.io/ashby/jobs/1",
        "company_domain": "ashbyhq.com",
    })
    result = run(path, dns_fn=lambda d: True, mx_fn=lambda d: True,
                 fetch_fn=lambda d: (200, ""), sleep_fn=lambda _: None)
    check("guessed company_domain (paystack.com) is verified even though "
          "apply_url is on greenhouse.io",
          db.get_trust_record(conn, "paystack.com") is not None)
    check("workable-hosted job → fairmoney.com verified, not workable.com",
          db.get_trust_record(conn, "fairmoney.com") is not None
          and db.get_trust_record(conn, "workable.com") is None
          and db.get_trust_record(conn, "apply.workable.com") is None)
    check("guessed domain used even when apply_url is malformed",
          db.get_trust_record(conn, "kuda.com") is not None)
    check("guessed domain that IS an ATS host is defensively skipped",
          db.get_trust_record(conn, "ashbyhq.com") is None)
    # Same run must NOT accidentally attribute a match to the ATS host.
    check("boards.greenhouse.io still never verified as the employer",
          db.get_trust_record(conn, "boards.greenhouse.io") is None)
    # Three real employer domains → 3 verified this run.
    check("exactly three real employer domains verified from four rows",
          result["verified"] == 3)

# ---- Phase 2: registered Employer Portal accounts get refreshed too ---------
with tempfile.TemporaryDirectory() as directory:
    path = os.path.join(directory, "emp.sqlite3")
    conn = db.connect(path)
    cold = db.create_employer(conn, "Cold Co", "coldco.com", "hm-1")
    vouched = db.create_employer(conn, "Warm Co", "warmco.com", "hm-2")
    db.vouch_employer(conn, vouched, "joy")
    result = run(path, dns_fn=lambda d: True, mx_fn=lambda d: True,
                 fetch_fn=lambda d: (200, ""), sleep_fn=lambda _: None)
    check("cold employer's domain verified by the worker",
          db.get_trust_record(conn, "coldco.com") is not None)
    check("vouched employer's domain skipped (Joy vouches personally)",
          db.get_trust_record(conn, "warmco.com") is None)
    refreshed = db.get_employer(conn, cold)
    check("refreshed score written back to the employers row (portal level)",
          refreshed["trust_score"] is not None
          and refreshed["trust_level"] in ("high", "medium", "low", "avoid"))
    check("vouched employer's trust untouched",
          db.get_employer(conn, vouched)["trust_score"] is None)

# _is_ats_host smoke tests — defensive filter against all 5 ATS hosts.
check("_is_ats_host: boards.greenhouse.io", _is_ats_host("boards.greenhouse.io"))
check("_is_ats_host: jobs.lever.co", _is_ats_host("jobs.lever.co"))
check("_is_ats_host: jobs.ashbyhq.com", _is_ats_host("jobs.ashbyhq.com"))
check("_is_ats_host: apply.workable.com", _is_ats_host("apply.workable.com"))
check("_is_ats_host: jobs.smartrecruiters.com", _is_ats_host("jobs.smartrecruiters.com"))
check("_is_ats_host: paystack.com is NOT an ATS", not _is_ats_host("paystack.com"))

if fails:
    raise SystemExit(f"{len(fails)} failures")
print("ALL TESTS PASSED ✅")
