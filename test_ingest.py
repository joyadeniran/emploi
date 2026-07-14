"""Offline tests for workers/ingest_jobs.py and workers/match_users.py.
No network, no real Gemini calls. Run: python3 test_ingest.py"""

import json
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db
from workers.ingest_jobs import run as ingest_run, _strip_html, _is_remote, _stable_id


def check(label, cond):
    print(("PASS" if cond else "FAIL"), "-", label)
    return cond


ok = True

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


def fake_fetch(url: str):
    if "greenhouse.io" in url and "testco" in url:
        return GREENHOUSE_RESPONSE
    if "lever.co" in url and "stripe" in url:
        return LEVER_RESPONSE
    if "ashbyhq.com" in url and "ashbyco" in url:
        return ASHBY_RESPONSE
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
    ok &= check("4 jobs written (Greenhouse, Lever, and Ashby)", len(all_jobs) == 4)
    titles = [j["title"] for j in all_jobs]
    ok &= check("greenhouse job 'Senior Engineer' present", "Senior Engineer" in titles)
    ok &= check("lever job 'Backend Developer' present", "Backend Developer" in titles)
    ok &= check("Ashby job is normalized", "ML Engineer" in titles)
    ok &= check("job_sources table seeded on first run",
                len(db.list_job_sources(conn)) >= 3)

    remote_jobs = db.list_jobs(conn, remote_only=True)
    ok &= check("remote jobs correctly flagged", all(j["is_remote"] for j in remote_jobs))
    ok &= check("at least 3 remote jobs", len(remote_jobs) >= 3)

    # Idempotency — second run must not grow the job count
    worker.SOURCES_PATH = sources_path
    ingest_run(db_path, dry_run=False, fetch_fn=fake_fetch)
    worker.SOURCES_PATH = _orig_sources
    ok &= check("second run is idempotent (no duplicates)", db.count_jobs(conn) == 4)

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

print("\n" + ("ALL TESTS PASSED ✅" if ok else "SOME TESTS FAILED ❌"))
sys.exit(0 if ok else 1)
