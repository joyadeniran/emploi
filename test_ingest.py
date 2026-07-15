"""Offline tests for workers/ingest_jobs.py and workers/match_users.py.
No network, no real Gemini calls. Run: python3 test_ingest.py"""

import json
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db
from workers.ingest_jobs import (run as ingest_run, _strip_html, _is_remote,
                                  _stable_id, _derive_company_domain)


def check(label, cond):
    print(("PASS" if cond else "FAIL"), "-", label)
    return cond


ok = True

# ---- _derive_company_domain -------------------------------------------------
# The heuristic that lets verify_employers score ATS-hosted jobs against the
# real employer domain instead of misattributing to greenhouse.io / lever.co.
ok &= check("_derive_company_domain: plain single-word", _derive_company_domain("Paystack") == "paystack.com")
ok &= check("_derive_company_domain: two-word joined", _derive_company_domain("Fair Money") == "fairmoney.com")
ok &= check("_derive_company_domain: stopwords dropped", _derive_company_domain("Acme Inc.") == "acme.com")
ok &= check("_derive_company_domain: 'Ltd' variant dropped", _derive_company_domain("Kuda Ltd") == "kuda.com")
ok &= check("_derive_company_domain: parenthetical clarifier dropped",
            _derive_company_domain("Loom (Atlassian)") == "loom.com")
ok &= check("_derive_company_domain: punctuation stripped", _derive_company_domain("Chipper Cash") == "chippercash.com")
ok &= check("_derive_company_domain: empty name → None",  _derive_company_domain("") is None)
ok &= check("_derive_company_domain: None → None", _derive_company_domain(None) is None)
ok &= check("_derive_company_domain: all-stopwords → None",
            _derive_company_domain("Inc. Ltd. GmbH") is None)
ok &= check("_derive_company_domain: too-short slug (<3 chars) → None",
            _derive_company_domain("AB") is None)
ok &= check("_derive_company_domain: digits kept", _derive_company_domain("Carry1st") == "carry1st.com")
ok &= check("_derive_company_domain: ampersand stripped", _derive_company_domain("Ben & Jerry's") == "benjerrys.com")

# ---- utility helpers --------------------------------------------------------
ok &= check("_strip_html removes tags", _strip_html("<p>Hello <b>world</b></p>") == "Hello world")
# Greenhouse sends content HTML-escaped — regression: entity soup was stored verbatim
ok &= check("_strip_html unescapes entity-encoded HTML before stripping",
            _strip_html("&lt;div class=&quot;intro&quot;&gt;About &amp;amp; beyond&lt;/div&gt;")
            == "About & beyond")
ok &= check("_strip_html leaves plain text alone", _strip_html("Just words, no markup") == "Just words, no markup")
ok &= check("_is_remote matches 'remote'", _is_remote("Fully remote position"))
ok &= check("_is_remote case-insensitive", _is_remote("REMOTE"))
ok &= check("_is_remote not triggered by unrelated text", not _is_remote("in-office Lagos"))
ok &= check("_stable_id is deterministic", _stable_id("a", "b") == _stable_id("a", "b"))
ok &= check("_stable_id differs for different inputs", _stable_id("a") != _stable_id("b"))

# ---- fake HTTP responses ----------------------------------------------------

GREENHOUSE_RESPONSE = {
    "jobs": [
        {"id": 12345, "title": "Senior Engineer",
         "content": "<p>Build distributed systems. Remote OK.</p>",
         "location": {"name": "Remote"}, "absolute_url": "https://boards.greenhouse.io/testco/12345",
         "departments": [{"name": "Engineering"}]},
        {"id": 12346, "title": "Product Manager",
         "content": "<p>Lead the product team. Lagos.</p>",
         "location": {"name": "Lagos, Nigeria"}, "absolute_url": "https://boards.greenhouse.io/testco/12346",
         "departments": [{"name": "Product"}]},
    ]
}

LEVER_RESPONSE = [
    {"id": "lever-abc-123", "text": "Backend Developer",
     "descriptionPlain": "Build APIs for fintech. Fully remote.",
     "hostedUrl": "https://jobs.lever.co/stripe/lever-abc-123",
     "workplaceType": "remote", "categories": {"location": "Remote", "team": "Engineering"}},
]

ASHBY_RESPONSE = {"jobs": [{"id": "ashby-1", "title": "ML Engineer",
    "descriptionHtml": "<p>Build AI systems. Remote worldwide.</p>",
    "location": "Remote", "jobUrl": "https://jobs.ashbyhq.com/test/ashby-1",
    "department": "Engineering"}]}

# Workable's public v3 accounts endpoint — {"results": [...]} shape.
# Also cover: draft state is skipped, workplace_type=remote is honoured,
# a bare list response (some tenants) is tolerated.
WORKABLE_RESPONSE = {"results": [
    {"id": "wk-1", "shortcode": "WK001", "title": "Product Designer",
     "state": "published", "department": "Design",
     "url": "https://apply.workable.com/testwk/j/WK001",
     "application_url": "https://apply.workable.com/testwk/j/WK001/apply",
     "location": {"location_str": "Lagos, Nigeria", "country": "Nigeria",
                  "region": "Lagos", "city": "Lagos",
                  "workplace_type": "on_site", "telecommuting": False}},
    {"id": "wk-2", "shortcode": "WK002", "title": "Remote Data Scientist",
     "state": "published", "department": "Data",
     "url": "https://apply.workable.com/testwk/j/WK002",
     "application_url": "https://apply.workable.com/testwk/j/WK002/apply",
     "location": {"location_str": "Remote", "workplace_type": "remote",
                  "telecommuting": True}},
    {"id": "wk-3", "shortcode": "WK003", "title": "Draft — ignore me",
     "state": "draft", "url": "https://apply.workable.com/testwk/j/WK003",
     "location": {"location_str": "Anywhere"}},
]}

# SmartRecruiters public postings — {"content": [...]} shape with
# jobAd.sections.jobDescription.text carrying the short blurb.
SMARTRECRUITERS_RESPONSE = {"content": [
    {"id": "sr-1", "name": "Backend Engineer",
     "location": {"city": "Berlin", "region": "Berlin", "country": "DE",
                  "remote": False, "fullLocation": "Berlin, Germany"},
     "department": {"label": "Engineering"},
     "postingUrl": "https://jobs.smartrecruiters.com/testsr/sr-1",
     "jobAd": {"sections": {"jobDescription": {
         "text": "<p>Build our payments platform. Berlin office.</p>"}}}},
    {"id": "sr-2", "name": "Remote Support Lead",
     "location": {"country": "Global", "remote": True, "fullLocation": "Remote"},
     "department": {"label": "Support"},
     "postingUrl": "https://jobs.smartrecruiters.com/testsr/sr-2",
     "jobAd": {"sections": {"jobDescription": {
         "text": "Support customers across time zones."}}}},
]}


def fake_fetch(url: str):
    if "greenhouse.io" in url and "testco" in url:
        return GREENHOUSE_RESPONSE
    if "lever.co" in url and "stripe" in url:
        return LEVER_RESPONSE
    if "ashbyhq.com" in url and "ashbyco" in url:
        return ASHBY_RESPONSE
    if "workable.com" in url and "testwk" in url:
        return WORKABLE_RESPONSE
    if "smartrecruiters.com" in url and "testsr" in url:
        return SMARTRECRUITERS_RESPONSE
    # deadco / any unknown → simulated failure
    return None


# ---- rich sources JSON (new format) ----------------------------------------

SOURCES_JSON = json.dumps({
    "test_category": [
        {"company": "TestCo", "ats": "greenhouse", "token": "testco",
         "priority": 10, "region": "global", "active": True},
        {"company": "Dead Co", "ats": "greenhouse", "token": "deadco",
         "priority": 5, "region": "global", "active": True},
        {"company": "Stripe", "ats": "lever", "token": "stripe",
         "priority": 7, "region": "global", "active": True},
        {"company": "Ashby Co", "ats": "ashby", "token": "ashbyco",
         "priority": 7, "region": "global", "active": True},
        {"company": "Workable Co", "ats": "workable", "token": "testwk",
         "priority": 7, "region": "global", "active": True},
        {"company": "SmartRec Co", "ats": "smartrecruiters", "token": "testsr",
         "priority": 7, "region": "global", "active": True},
        # career_page ATS: skipped gracefully
        {"company": "Career Page Co", "ats": "career_page", "token": "cpc",
         "priority": 5, "region": "global", "active": True},
    ]
})


def _write_sources(content: str, tmpdir: str) -> str:
    path = os.path.join(tmpdir, "job_sources.json")
    open(path, "w").write(content)
    return path


import workers.ingest_jobs as worker
_orig_sources = worker.SOURCES_PATH

# ---- run tests with a real file-backed DB -----------------------------------

with tempfile.TemporaryDirectory() as tmpdir:
    sources_path = _write_sources(SOURCES_JSON, tmpdir)
    db_path = os.path.join(tmpdir, "test.sqlite3")
    worker.SOURCES_PATH = sources_path

    result = ingest_run(db_path, dry_run=False, fetch_fn=fake_fetch)
    worker.SOURCES_PATH = _orig_sources

    ok &= check("run ok (dead source returns 0 jobs, not an error)", result["ok"])
    ok &= check("fetched count > 0", result["fetched"] > 0)
    ok &= check("written count > 0", result["written"] > 0)
    ok &= check("sources_processed reported", result["sources_processed"] >= 3)

    conn = db.connect(db_path)
    all_jobs = db.list_jobs(conn)
    # 2 Greenhouse + 1 Lever + 1 Ashby + 2 Workable (draft skipped) + 2 SmartRecruiters = 8
    ok &= check("8 jobs written (Greenhouse, Lever, Ashby, Workable, SmartRecruiters)",
                len(all_jobs) == 8)
    titles = [j["title"] for j in all_jobs]
    ok &= check("greenhouse job 'Senior Engineer' present", "Senior Engineer" in titles)
    ok &= check("lever job 'Backend Developer' present", "Backend Developer" in titles)
    ok &= check("Ashby job is normalized", "ML Engineer" in titles)
    ok &= check("Workable published job present", "Product Designer" in titles)
    ok &= check("Workable draft job SKIPPED (state != published)",
                "Draft — ignore me" not in titles)
    ok &= check("SmartRecruiters job present", "Backend Engineer" in titles)
    ok &= check("job_sources table seeded on first run",
                len(db.list_job_sources(conn)) >= 3)

    # Workable: workplace_type=remote flips is_remote regardless of city
    wk_remote = [j for j in all_jobs if j["title"] == "Remote Data Scientist"]
    ok &= check("Workable workplace_type=remote sets is_remote=True",
                len(wk_remote) == 1 and wk_remote[0]["is_remote"])
    # Workable: on_site + Lagos is NOT remote
    wk_onsite = [j for j in all_jobs if j["title"] == "Product Designer"]
    ok &= check("Workable on_site + Lagos is NOT flagged remote",
                len(wk_onsite) == 1 and not wk_onsite[0]["is_remote"])
    # SmartRecruiters: location.remote=True is honoured
    sr_remote = [j for j in all_jobs if j["title"] == "Remote Support Lead"]
    ok &= check("SmartRecruiters location.remote=True sets is_remote",
                len(sr_remote) == 1 and sr_remote[0]["is_remote"])
    # SmartRecruiters: jobAd.sections.jobDescription.text is stored (HTML stripped)
    sr_be = [j for j in all_jobs if j["title"] == "Backend Engineer"]
    ok &= check("SmartRecruiters JD text parsed and HTML-stripped",
                len(sr_be) == 1
                and "payments platform" in (sr_be[0]["description"] or "")
                and "<p>" not in (sr_be[0]["description"] or ""))
    # source_key prefixes are namespaced by ATS
    source_keys = {j["source"] for j in all_jobs}
    ok &= check("workable/ source_key present", "workable/testwk" in source_keys)
    ok &= check("smartrecruiters/ source_key present",
                "smartrecruiters/testsr" in source_keys)

    # company_domain is populated at ingest for every handler — this is what
    # lets verify_employers score an ATS-hosted job against the real employer
    # domain instead of misattributing to the ATS host.
    def _cd(title):
        rows = [j for j in all_jobs if j["title"] == title]
        return rows[0]["company_domain"] if rows else None
    ok &= check("greenhouse handler populates company_domain from company_name",
                _cd("Senior Engineer") == "testco.com")
    ok &= check("lever handler populates company_domain",
                _cd("Backend Developer") == "stripe.com")
    ok &= check("ashby handler populates company_domain (stopwords dropped)",
                _cd("ML Engineer") == "ashby.com")
    # "Workable Co" → stopword "co" drops → "workable.com". This IS an ATS
    # host string; verify_employers._is_ats_host defensively filters it so
    # the misfire never becomes a bad trust record. Assertion here just
    # documents the heuristic honestly.
    ok &= check("workable handler populates company_domain (stopwords dropped)",
                _cd("Product Designer") == "workable.com")
    ok &= check("smartrecruiters handler populates company_domain (stopwords dropped)",
                _cd("Backend Engineer") == "smartrec.com")

    remote_jobs = db.list_jobs(conn, remote_only=True)
    ok &= check("remote jobs correctly flagged",
                all(j["is_remote"] for j in remote_jobs))
    ok &= check("at least 5 remote jobs", len(remote_jobs) >= 5)

    # Idempotency — second run must not grow the job count
    worker.SOURCES_PATH = sources_path
    ingest_run(db_path, dry_run=False, fetch_fn=fake_fetch)
    worker.SOURCES_PATH = _orig_sources
    ok &= check("second run is idempotent (no duplicates)", db.count_jobs(conn) == 8)

    # job_sources not re-seeded on second run (DB is source of truth)
    source_count = len(db.list_job_sources(conn))
    worker.SOURCES_PATH = sources_path
    ingest_run(db_path, dry_run=False, fetch_fn=fake_fetch)
    worker.SOURCES_PATH = _orig_sources
    ok &= check("seed is a no-op when table already populated",
                len(db.list_job_sources(conn)) == source_count)

# ---- dry-run: reads JSON, prints, no DB writes -----------------------------

with tempfile.TemporaryDirectory() as tmpdir:
    sources_path = _write_sources(SOURCES_JSON, tmpdir)
    db_path = os.path.join(tmpdir, "dryrun.sqlite3")
    worker.SOURCES_PATH = sources_path
    result = ingest_run(db_path, dry_run=True, fetch_fn=fake_fetch)
    worker.SOURCES_PATH = _orig_sources

    ok &= check("dry-run result has dry_run=True", result["dry_run"] is True)
    # dry-run must NOT create DB or write jobs
    if os.path.exists(db_path):
        conn2 = db.connect(db_path)
        ok &= check("dry-run leaves ingested_jobs empty", db.count_jobs(conn2) == 0)
    else:
        ok &= check("dry-run leaves DB empty (no file created)", True)

# ---- min-priority filter ---------------------------------------------------

with tempfile.TemporaryDirectory() as tmpdir:
    sources_path = _write_sources(SOURCES_JSON, tmpdir)
    db_path = os.path.join(tmpdir, "priority.sqlite3")
    worker.SOURCES_PATH = sources_path
    result = ingest_run(db_path, dry_run=False, min_priority=8, fetch_fn=fake_fetch)
    worker.SOURCES_PATH = _orig_sources
    # Only testco (priority 10) should run — stripe (7) and deadco (5) skipped
    ok &= check("min-priority=8 only runs priority>=8 sources",
                result["sources_processed"] == 1)
    conn3 = db.connect(db_path)
    ok &= check("only testco jobs written (2)", db.count_jobs(conn3) == 2)

# ---- bad sources file → graceful error -------------------------------------

with tempfile.TemporaryDirectory() as tmpdir:
    worker.SOURCES_PATH = os.path.join(tmpdir, "nonexistent.json")
    result = ingest_run(os.path.join(tmpdir, "x.sqlite3"), dry_run=True)
    worker.SOURCES_PATH = _orig_sources
    ok &= check("missing sources file (dry-run) → ok=False, never crashes",
                result["ok"] is False)

# ---- manual curation handler ------------------------------------------------
# The honest answer for employers without a public ATS feed (Nigerian banks,
# Workday shops, etc). Reads data/manual_jobs/{token}.json; auto-expires
# entries older than MANUAL_JOB_MAX_AGE_DAYS; malformed entries are skipped
# without killing the whole file.

from workers.ingest_jobs import _ingest_manual
import workers.ingest_jobs as _ijworker
from datetime import datetime, timedelta

with tempfile.TemporaryDirectory() as tmpdir:
    # Point the handler at a temp manual_jobs dir.
    manual_dir = os.path.join(tmpdir, "manual_jobs")
    os.makedirs(manual_dir)
    _orig_manual = _ijworker.MANUAL_JOBS_DIR
    _ijworker.MANUAL_JOBS_DIR = manual_dir

    # Compose a manual file with three entries:
    #   1. fresh + complete → written
    #   2. stale (60 days old) → skipped by age filter
    #   3. malformed (not a dict) → skipped, no crash
    fresh_date = datetime.utcnow().date().isoformat()
    stale_date = (datetime.utcnow() - timedelta(days=60)).date().isoformat()
    file_content = [
        {"job_id": "gtco-1", "title": "Risk Analyst",
         "description": "Enterprise risk role.", "location": "Lagos, Nigeria",
         "is_remote": False, "apply_url": "https://gtco.com/careers/1",
         "salary_text": None, "category": "Risk", "posted_at": fresh_date},
        {"job_id": "gtco-2", "title": "Old Role — should not ingest",
         "description": "Expired.", "location": "Lagos",
         "apply_url": "https://gtco.com/careers/2",
         "posted_at": stale_date},
        "this is not a dict — must be skipped, not crash the run",
    ]
    open(os.path.join(manual_dir, "gtco.json"), "w").write(
        json.dumps(file_content))

    db_path = os.path.join(tmpdir, "manual.sqlite3")
    conn = db.connect(db_path)

    source = {"company": "GTCO", "ats": "manual", "token": "gtco",
              "priority": 5, "region": "nigeria", "active": True}
    fetched, written = _ingest_manual(source, conn, False)
    ok &= check("manual handler reports fetched=len(payload) including skipped rows",
                fetched == 3)
    ok &= check("manual handler writes only the fresh, well-formed job",
                written == 1)

    jobs = db.list_jobs(conn)
    ok &= check("manual job title stored", jobs and jobs[0]["title"] == "Risk Analyst")
    ok &= check("manual job source_key namespaced under manual/",
                jobs[0]["source"] == "manual/gtco")
    ok &= check("manual job company_domain derived from company_name",
                jobs[0]["company_domain"] == "gtco.com")
    ok &= check("stale posted_at (60d ago) is NOT ingested",
                all(j["title"] != "Old Role — should not ingest" for j in jobs))

    # is_remote heuristic — an entry with is_remote=false but "remote" in
    # the description should still flip.
    remote_dir_file = [
        {"job_id": "gtco-3", "title": "Remote Ops Coordinator",
         "description": "Fully remote hire; no office required.",
         "location": "Lagos", "is_remote": False,
         "apply_url": "https://gtco.com/careers/3",
         "posted_at": fresh_date},
    ]
    open(os.path.join(manual_dir, "gtco.json"), "w").write(
        json.dumps(remote_dir_file))
    _ingest_manual(source, conn, False)
    jobs = db.list_jobs(conn, remote_only=True)
    ok &= check("is_remote flag flipped by 'remote' in description",
                any(j["title"] == "Remote Ops Coordinator" for j in jobs))

    # Missing file — graceful (0 fetched, no crash)
    missing_src = {"company": "NoFile", "ats": "manual", "token": "nofile",
                    "priority": 5, "region": "nigeria", "active": True}
    f2, w2 = _ingest_manual(missing_src, conn, False)
    ok &= check("missing manual file → (0,0), no crash",
                f2 == 0 and w2 == 0)

    # Bad JSON — graceful
    open(os.path.join(manual_dir, "broken.json"), "w").write("{not json")
    broken_src = {"company": "Broken", "ats": "manual", "token": "broken",
                   "priority": 5, "region": "nigeria", "active": True}
    f3, w3 = _ingest_manual(broken_src, conn, False)
    ok &= check("malformed manual file → (0,0), no crash",
                f3 == 0 and w3 == 0)

    # Dry-run doesn't write.
    open(os.path.join(manual_dir, "dryrun.json"), "w").write(
        json.dumps([{"job_id": "dr-1", "title": "Dry Run",
                     "description": "", "location": "Remote",
                     "apply_url": "https://x.com/1",
                     "posted_at": fresh_date}]))
    dr_src = {"company": "Dry Run Co", "ats": "manual", "token": "dryrun",
              "priority": 5, "region": "global", "active": True}
    f4, w4 = _ingest_manual(dr_src, conn, True)  # dry_run=True
    ok &= check("dry-run reports written but skips DB",
                w4 == 1
                and not any(j["title"] == "Dry Run" for j in db.list_jobs(conn)))

    # manual is registered in _ATS_HANDLERS.
    ok &= check("manual registered in _ATS_HANDLERS",
                _ijworker._ATS_HANDLERS.get("manual") is _ingest_manual)

    _ijworker.MANUAL_JOBS_DIR = _orig_manual


# =====================================================================
# Worker 3 — match_users.py offline tests
# =====================================================================

from workers.match_users import run as match_run

class FakeModel:
    """Returns a plausible match result for every job in the batch."""
    def generate_content(self, prompt):
        import re as _re
        # build_match_prompt uses [0], [1], ... bracket notation for job indices
        indices = _re.findall(r'^\[(\d+)\]', prompt, _re.MULTILINE)
        scores = [{"index": int(i), "fit_score": 80 - int(i)*2,
                   "reason": f"good match for job {i}"} for i in indices]
        class R: pass
        r = R(); r.text = json.dumps(scores)
        return r


with tempfile.TemporaryDirectory() as tmpdir:
    db_path = os.path.join(tmpdir, "match.sqlite3")
    conn = db.connect(db_path)

    # No users yet → graceful empty run
    result = match_run(db_path, model=FakeModel())
    ok &= check("matching with no users → ok=True, zero matches",
                result["ok"] and result["total_matches"] == 0)

    # Seed a user with a completed Career Twin
    db.save_career_twin(conn, "u1", {
        "name": "Ada", "skills": ["Python", "SQL"], "onboarding_complete": True,
        "headline": "Data Engineer", "bio": "5 years in data."})

    # No jobs yet → still ok, zero matches
    result = match_run(db_path, model=FakeModel())
    ok &= check("matching with completed twin but no jobs → ok, zero matches",
                result["ok"] and result["total_matches"] == 0)

    # Seed some jobs
    j1 = db.upsert_job(conn, "test/src", "j1",
                       {"title": "Data Engineer", "company_name": "Acme",
                        "description": "Python, SQL, BigQuery", "is_remote": True})
    j2 = db.upsert_job(conn, "test/src", "j2",
                       {"title": "Backend Dev", "company_name": "Halo",
                        "description": "Node.js, TypeScript", "is_remote": True})
    j3 = db.upsert_job(conn, "test/src", "j3",
                       {"title": "PM", "company_name": "Notion",
                        "description": "Product strategy", "is_remote": True})

    result = match_run(db_path, model=FakeModel(), days_fresh=365)
    ok &= check("matching produces results for seeded user",
                result["ok"] and result["total_matches"] > 0)
    ok &= check("gemini called at least once", result["total_calls"] >= 1)

    matches = db.list_matches(conn, "u1")
    ok &= check("matches written to DB", len(matches) > 0)
    ok &= check("matches sorted best fit first",
                all(matches[i]["fit_score"] >= matches[i+1]["fit_score"]
                    for i in range(len(matches)-1)))

    # Idempotency: second run should re-score (already matched) only if --force,
    # by default new jobs only. With days_fresh=365 and no new jobs → 0 new matches.
    prev_count = len(matches)
    result2 = match_run(db_path, model=FakeModel(), days_fresh=365)
    ok &= check("second run skips already-matched jobs",
                result2["total_matches"] == 0)
    ok &= check("match table count unchanged", len(db.list_matches(conn, "u1")) == prev_count)

    # User without onboarding_complete is ignored
    db.save_career_twin(conn, "u2", {"name": "Bola", "onboarding_complete": False})
    result3 = match_run(db_path, model=FakeModel(), days_fresh=365)
    ok &= check("user without onboarding_complete not matched",
                len(db.list_matches(conn, "u2")) == 0)

    # --dry-run: no writes
    j4 = db.upsert_job(conn, "test/src", "j4",
                       {"title": "New Job", "company_name": "New Co",
                        "description": "fresh", "is_remote": True})
    result_dry = match_run(db_path, dry_run=True, model=FakeModel(), days_fresh=365)
    ok &= check("match dry-run has dry_run=True", result_dry["dry_run"] is True)
    ok &= check("match dry-run doesn't write j4 to matches",
                all(m["job_id"] != j4 for m in db.list_matches(conn, "u1")))

    # batch_size=1 still produces correct results (multiple Gemini calls)
    j5 = db.upsert_job(conn, "test/src", "j5",
                       {"title": "ML Engineer", "company_name": "Scale",
                        "description": "machine learning", "is_remote": True})
    j6 = db.upsert_job(conn, "test/src", "j6",
                       {"title": "DevOps", "company_name": "HashiCorp",
                        "description": "terraform k8s", "is_remote": True})
    result_b1 = match_run(db_path, model=FakeModel(), days_fresh=365, batch_size=1)
    ok &= check("batch_size=1 calls Gemini once per unmatched job",
                result_b1["total_calls"] >= result_b1["total_matches"] > 0)

    # Preference gating: a remote-only Nigeria-based user never has an
    # on-site San Francisco job scored (no Gemini spend, no match row).
    db.save_career_twin(conn, "u3", {
        "name": "Remi", "onboarding_complete": True,
        "remote_preference": "Remote", "preferred_locations": ["Nigeria"],
        "skills": ["Ops"]})
    db.upsert_job(conn, "test/src", "j7",
                  {"title": "Onsite Office Manager", "company_name": "SF Co",
                   "description": "in office daily", "is_remote": False,
                   "location": "San Francisco, CA"})
    match_run(db_path, model=FakeModel(), days_fresh=365)
    u3_titles = [m["title"] for m in db.list_matches(conn, "u3")]
    ok &= check("preference gate: on-site SF job never matched for remote-only user",
                "Onsite Office Manager" not in u3_titles)
    ok &= check("preference gate: remote jobs still matched for that user",
                len(u3_titles) > 0 and all(t != "Onsite Office Manager" for t in u3_titles))

print("\n" + ("ALL TESTS PASSED ✅" if ok else "SOME TESTS FAILED ❌"))
sys.exit(0 if ok else 1)
