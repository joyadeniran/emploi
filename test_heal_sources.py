"""Offline tests for workers/heal_job_sources.py.
No network — fake fetcher decides which sources are live vs dead.
Run: python3 test_heal_sources.py"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db
import workers.ingest_jobs as ingest_worker
from workers.heal_job_sources import run as heal_run


def check(label, cond):
    print(("PASS" if cond else "FAIL"), "-", label)
    return cond


ok = True

# Live fixture: one greenhouse company returns a job; every other URL 404s.
LIVE_GH = {"jobs": [{"id": 1, "title": "Job", "content": "",
                     "location": {"name": "Remote"},
                     "absolute_url": "https://boards.greenhouse.io/live/1",
                     "departments": []}]}


def fake_fetch(url: str):
    if "greenhouse.io" in url and "live-co" in url:
        return LIVE_GH
    return None  # every other source is dead


with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, "heal.sqlite3")
    conn = db.connect(path)

    # Seed the source registry directly: 1 live gh, 3 dead (various ATSes),
    # and 1 unsupported ATS. All start active=true.
    live_id = db.upsert_job_source(conn, "Live Co", "greenhouse", "live-co",
                                    priority=10, region="global", active=True)
    dead_gh = db.upsert_job_source(conn, "Dead GH", "greenhouse", "dead-gh",
                                    priority=5, region="global", active=True)
    dead_lever = db.upsert_job_source(conn, "Dead Lever", "lever", "dead-lever",
                                       priority=5, region="global", active=True)
    dead_workable = db.upsert_job_source(conn, "Dead Workable", "workable",
                                          "dead-workable", priority=5,
                                          region="global", active=True)
    unsup = db.upsert_job_source(conn, "Career Page Co", "career_page", "cpc",
                                  priority=5, region="global", active=True)

    # Dry-run: reports the split but changes nothing.
    result_dry = heal_run(path, dry_run=True, fetch_fn=fake_fetch,
                          sleep_fn=lambda _: None)
    ok &= check("dry-run reports 1 kept + 3 disabled + 1 unsupported",
                result_dry["kept_active"] == 1
                and result_dry["disabled"] == 3
                and result_dry["unsupported"] == 1)

    # Dry-run must not have touched the active flag.
    active_after_dry = {
        s["id"]: s["active"] for s in db.list_job_sources(conn)
    }
    ok &= check("dry-run does not disable any source",
                active_after_dry[live_id] == 1
                and active_after_dry[dead_gh] == 1
                and active_after_dry[dead_lever] == 1
                and active_after_dry[dead_workable] == 1)

    # Real run: disables the 3 dead sources, keeps the 1 live + 1 unsupported.
    result = heal_run(path, dry_run=False, fetch_fn=fake_fetch,
                      sleep_fn=lambda _: None)
    ok &= check("real run reports the same split",
                result["kept_active"] == 1 and result["disabled"] == 3
                and result["unsupported"] == 1)

    active_after = {s["id"]: s["active"] for s in db.list_job_sources(conn)}
    ok &= check("live source stays active", active_after[live_id] == 1)
    ok &= check("dead greenhouse now inactive", active_after[dead_gh] == 0)
    ok &= check("dead lever now inactive", active_after[dead_lever] == 0)
    ok &= check("dead workable now inactive", active_after[dead_workable] == 0)
    # Unsupported ATS (career_page) is left active — the ingest worker's
    # dispatcher already no-ops it, disabling would lose the "known employer,
    # no source yet" record.
    ok &= check("unsupported ATS left active (not our call to disable)",
                active_after[unsup] == 1)

    # The heal run logged an event with the disabled ids.
    ev = conn.execute("SELECT payload FROM events WHERE type='HealJobSourcesRun' "
                      "ORDER BY id DESC LIMIT 1").fetchone()
    import json as _json
    payload = _json.loads(ev["payload"])
    ok &= check("HealJobSourcesRun event records disabled_ids",
                set(payload["disabled_ids"]) == {dead_gh, dead_lever, dead_workable})

    # Idempotency: a second run only sees the still-active sources and finds
    # nothing new to disable (live is still live, unsupported is still unsupported).
    result_second = heal_run(path, dry_run=False, fetch_fn=fake_fetch,
                             sleep_fn=lambda _: None)
    ok &= check("second heal run is a no-op on already-clean DB",
                result_second["disabled"] == 0
                and result_second["kept_active"] == 1
                and result_second["unsupported"] == 1)

# Handler-throws case: an unexpected exception during probe is treated as
# dead + logged, never crashes the run.
class ExplodingHandler:
    def __call__(self, *a, **kw):
        raise RuntimeError("simulated ATS handler explosion")

with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, "explode.sqlite3")
    conn = db.connect(path)
    src_id = db.upsert_job_source(conn, "Boom Co", "greenhouse", "boom",
                                    priority=5, region="global", active=True)

    # Swap in the exploding handler.
    _orig_gh = ingest_worker._ATS_HANDLERS["greenhouse"]
    ingest_worker._ATS_HANDLERS["greenhouse"] = ExplodingHandler()
    try:
        result = heal_run(path, dry_run=False, fetch_fn=fake_fetch,
                          sleep_fn=lambda _: None)
    finally:
        ingest_worker._ATS_HANDLERS["greenhouse"] = _orig_gh

    ok &= check("handler exception → source disabled, run still ok",
                result["ok"] and result["disabled"] == 1)
    active_after = {s["id"]: s["active"] for s in db.list_job_sources(conn)}
    ok &= check("exploded source is now inactive", active_after[src_id] == 0)

print("\n" + ("ALL TESTS PASSED ✅" if ok else "SOME TESTS FAILED ❌"))
sys.exit(0 if ok else 1)
