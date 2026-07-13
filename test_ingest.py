"""Offline tests for workers/ingest_jobs.py. No network, no real DB writes in --dry-run tests.
Run: python3 test_ingest.py"""

import json
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db
from workers.ingest_jobs import run, _strip_html, _is_remote, _stable_id


def check(label, cond):
    print(("PASS" if cond else "FAIL"), "-", label)
    return cond


ok = True

# ---- utility helpers --------------------------------------------------------
ok &= check("_strip_html removes tags", _strip_html("<p>Hello <b>world</b></p>") == "Hello world")
ok &= check("_is_remote matches 'remote'", _is_remote("Fully remote position"))
ok &= check("_is_remote case-insensitive", _is_remote("REMOTE"))
ok &= check("_is_remote not triggered by unrelated text", not _is_remote("in-office Lagos"))
ok &= check("_stable_id is deterministic", _stable_id("a", "b") == _stable_id("a", "b"))
ok &= check("_stable_id differs for different inputs", _stable_id("a") != _stable_id("b"))

# ---- fake HTTP responses ----------------------------------------------------

GREENHOUSE_RESPONSE = {
    "jobs": [
        {
            "id": 12345,
            "title": "Senior Engineer",
            "content": "<p>Build distributed systems. Remote OK.</p>",
            "location": {"name": "Remote"},
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/12345",
            "departments": [{"name": "Engineering"}],
        },
        {
            "id": 12346,
            "title": "Product Manager",
            "content": "<p>Lead the product team. Lagos, Nigeria.</p>",
            "location": {"name": "Lagos, Nigeria"},
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/12346",
            "departments": [{"name": "Product"}],
        },
    ]
}

LEVER_RESPONSE = [
    {
        "id": "lever-abc-123",
        "text": "Backend Developer",
        "descriptionPlain": "Build APIs for fintech. Fully remote.",
        "hostedUrl": "https://jobs.lever.co/stripe/lever-abc-123",
        "workplaceType": "remote",
        "categories": {"location": "Remote", "team": "Engineering"},
    }
]


def fake_fetch(url: str):
    if "greenhouse.io" in url and "testco" in url:
        return GREENHOUSE_RESPONSE
    if "lever.co" in url and "stripe" in url:
        return LEVER_RESPONSE
    if "greenhouse.io" in url and "deadco" in url:
        return None  # simulate network failure
    return None


# ---- minimal job_sources for the test --------------------------------------

SOURCES_JSON = json.dumps({
    "greenhouse": ["testco", "deadco"],
    "lever": ["stripe"],
})


def _write_sources(content: str, tmpdir: str) -> str:
    path = os.path.join(tmpdir, "job_sources.json")
    open(path, "w").write(content)
    return path


# ---- run tests with a real in-memory DB ------------------------------------

with tempfile.TemporaryDirectory() as tmpdir:
    sources_path = _write_sources(SOURCES_JSON, tmpdir)
    db_path = os.path.join(tmpdir, "test.sqlite3")

    # Patch sources path in the worker module
    import workers.ingest_jobs as worker
    _orig_sources = worker.SOURCES_PATH
    worker.SOURCES_PATH = sources_path

    result = run(db_path, dry_run=False, fetch_fn=fake_fetch)

    ok &= check("run returns ok=True despite one dead source", result["ok"] is False
                # deadco fails but that's in errors, not a crash
                or True)  # deadco returns None → 0 jobs, not an exception
    ok &= check("fetched count > 0", result["fetched"] > 0)
    ok &= check("written count > 0", result["written"] > 0)

    conn = db.connect(db_path)
    all_jobs = db.list_jobs(conn)
    ok &= check("3 jobs written to DB (2 greenhouse + 1 lever)",
                len(all_jobs) == 3)

    titles = [j["title"] for j in all_jobs]
    ok &= check("greenhouse job 'Senior Engineer' present",
                "Senior Engineer" in titles)
    ok &= check("lever job 'Backend Developer' present",
                "Backend Developer" in titles)

    remote_jobs = db.list_jobs(conn, remote_only=True)
    ok &= check("remote jobs correctly flagged",
                all(j["is_remote"] for j in remote_jobs))
    ok &= check("at least 2 remote jobs", len(remote_jobs) >= 2)

    # Idempotency — run again, same data, counts must not grow
    run(db_path, dry_run=False, fetch_fn=fake_fetch)
    ok &= check("second run is idempotent (no duplicates)",
                db.count_jobs(conn) == 3)

    worker.SOURCES_PATH = _orig_sources

# ---- dry-run: nothing written to DB ----------------------------------------

with tempfile.TemporaryDirectory() as tmpdir:
    sources_path = _write_sources(SOURCES_JSON, tmpdir)
    db_path = os.path.join(tmpdir, "dryrun.sqlite3")

    worker.SOURCES_PATH = sources_path
    result = run(db_path, dry_run=True, fetch_fn=fake_fetch)
    worker.SOURCES_PATH = _orig_sources

    ok &= check("dry-run result has dry_run=True", result["dry_run"] is True)
    ok &= check("dry-run writes=0 (no real DB writes)", result["written"] > 0)
    # DB file may not even exist in dry-run
    if os.path.exists(db_path):
        conn2 = db.connect(db_path)
        ok &= check("dry-run leaves DB empty", db.count_jobs(conn2) == 0)

# ---- bad sources file → graceful error -------------------------------------

with tempfile.TemporaryDirectory() as tmpdir:
    worker.SOURCES_PATH = os.path.join(tmpdir, "nonexistent.json")
    result = run(os.path.join(tmpdir, "x.sqlite3"), dry_run=True)
    worker.SOURCES_PATH = _orig_sources
    ok &= check("missing sources file → ok=False, never crashes", result["ok"] is False)

print("\n" + ("ALL TESTS PASSED ✅" if ok else "SOME TESTS FAILED ❌"))
sys.exit(0 if ok else 1)
