"""Offline tests for workers/spot_check_sources.py.
Fake fetcher — no real Greenhouse/Lever/Ashby/Workable/SmartRecruiters calls.
Run: python3 test_spot_check.py"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import workers.ingest_jobs as worker
from workers.spot_check_sources import run as spot_check_run


def check(label, cond):
    print(("PASS" if cond else "FAIL"), "-", label)
    return cond


ok = True

# Minimal fake fetchers for each ATS shape.
LIVE_GREENHOUSE = {"jobs": [{"id": 1, "title": "Job", "content": "",
                             "location": {"name": "Remote"}, "absolute_url": "",
                             "departments": []}]}
LIVE_LEVER = [{"id": "1", "text": "Job", "descriptionPlain": "",
               "hostedUrl": "", "workplaceType": "remote", "categories": {}}]
LIVE_WORKABLE = {"results": [{"id": "wk1", "shortcode": "S", "title": "Job",
                              "state": "published", "location": {}}]}


def fake_fetch(url: str):
    if "livecompany" in url:
        if "greenhouse.io" in url:
            return LIVE_GREENHOUSE
        if "lever.co" in url:
            return LIVE_LEVER
        if "workable.com" in url:
            return LIVE_WORKABLE
    # Any URL containing "deadco" or unknown → simulated dead source
    return None


SOURCES_JSON = json.dumps({
    "test": [
        {"company": "Live GH", "ats": "greenhouse", "token": "livecompany",
         "priority": 10, "region": "global", "active": True},
        {"company": "Live Lever", "ats": "lever", "token": "livecompany",
         "priority": 10, "region": "global", "active": True},
        {"company": "Dead GH", "ats": "greenhouse", "token": "deadco",
         "priority": 5, "region": "global", "active": True},
        {"company": "Live Workable", "ats": "workable", "token": "livecompany",
         "priority": 7, "region": "global", "active": True},
        # Inactive sources should never count against ok
        {"company": "Off", "ats": "greenhouse", "token": "off1",
         "priority": 5, "region": "global", "active": False},
        # Unsupported ATS should be reported but never count against ok
        {"company": "Career Page Co", "ats": "career_page", "token": "cpc",
         "priority": 5, "region": "global", "active": True},
    ]
})


with tempfile.TemporaryDirectory() as tmpdir:
    path = os.path.join(tmpdir, "job_sources.json")
    open(path, "w").write(SOURCES_JSON)
    _orig = worker.SOURCES_PATH
    worker.SOURCES_PATH = path

    result = spot_check_run(fetch_fn=fake_fetch, sleep_fn=lambda _: None)

    worker.SOURCES_PATH = _orig

    ok &= check("checked count includes every source row",
                result["checked"] == 6)
    # Only "deadco" active source returns 0 → dead_active == 1
    ok &= check("exactly one active source returned 0 jobs",
                result["dead_active"] == 1)
    ok &= check("ok=False when at least one active source is dead",
                result["ok"] is False)

    # Per-source assertions
    by_token = {(r["ats"], r["token"], r["company"]): r for r in result["sources"]}
    ok &= check("live greenhouse reported >0 fetched",
                by_token[("greenhouse", "livecompany", "Live GH")]["fetched"] == 1)
    ok &= check("live lever reported >0 fetched",
                by_token[("lever", "livecompany", "Live Lever")]["fetched"] == 1)
    ok &= check("live workable reported >0 fetched",
                by_token[("workable", "livecompany", "Live Workable")]["fetched"] == 1)
    ok &= check("dead greenhouse reported 0 fetched with DEAD note",
                by_token[("greenhouse", "deadco", "Dead GH")]["fetched"] == 0
                and "DEAD" in by_token[("greenhouse", "deadco", "Dead GH")]["note"])
    ok &= check("inactive source is skipped (fetched=None, doesn't fail run)",
                by_token[("greenhouse", "off1", "Off")]["fetched"] is None)
    ok &= check("unsupported ATS is skipped (fetched=None)",
                by_token[("career_page", "cpc", "Career Page Co")]["fetched"] is None)

# Second scenario: --include-inactive probes inactive sources too
with tempfile.TemporaryDirectory() as tmpdir:
    path = os.path.join(tmpdir, "job_sources.json")
    open(path, "w").write(json.dumps({"test": [
        {"company": "Inactive GH", "ats": "greenhouse", "token": "livecompany",
         "priority": 5, "region": "global", "active": False},
    ]}))
    _orig = worker.SOURCES_PATH
    worker.SOURCES_PATH = path
    result = spot_check_run(include_inactive=True, fetch_fn=fake_fetch,
                            sleep_fn=lambda _: None)
    worker.SOURCES_PATH = _orig
    ok &= check("--include-inactive actually probes inactive sources",
                result["sources"][0]["fetched"] == 1)

# Third scenario: --only-ats filter narrows to one ATS
with tempfile.TemporaryDirectory() as tmpdir:
    path = os.path.join(tmpdir, "job_sources.json")
    open(path, "w").write(SOURCES_JSON)
    _orig = worker.SOURCES_PATH
    worker.SOURCES_PATH = path
    result = spot_check_run(only_ats="workable", fetch_fn=fake_fetch,
                            sleep_fn=lambda _: None)
    worker.SOURCES_PATH = _orig
    ok &= check("--only-ats=workable narrows to workable rows only",
                all(r["ats"] == "workable" for r in result["sources"])
                and len(result["sources"]) == 1)

print("\n" + ("ALL TESTS PASSED ✅" if ok else "SOME TESTS FAILED ❌"))
sys.exit(0 if ok else 1)
