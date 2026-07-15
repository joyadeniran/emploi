# data/manual_jobs — curated employer feeds

One JSON file per company. Filename = the source token used in
`data/job_sources.json` (e.g. `gtco.json` for the source
`{"ats": "manual", "token": "gtco"}`).

## When to use

Curated feeds are the honest answer for employers that don't publish a public
ATS feed and can't be scraped without legal/reliability risk. First target set
is the Nigerian corporates (GTCO, Access Bank, MTN, Dangote, etc) — the
"why isn't Emploi useful to me?" gap for the primary Nigerian user, since
their ATS-hosted employers (Andela, Flutterwave, Paystack, Kuda, OPay, ...)
are also currently dead per the 2026-07-15 spot-check.

Curator commitment: ~30 min/week per top-20 company set. Realistic because
each usually has 5-15 open roles at any time.

## File shape

```json
[
  {
    "job_id": "gtco-req-001",
    "title": "Senior Risk Analyst",
    "description": "…full JD here (HTML tags allowed, will be stripped)…",
    "location": "Lagos, Nigeria",
    "is_remote": false,
    "apply_url": "https://gtco.com/careers/senior-risk-analyst",
    "salary_text": null,
    "category": "Risk",
    "posted_at": "2026-07-10"
  }
]
```

- `job_id` — stable per (company, role); a repeated ingest upserts on
  `(source, source_job_id)` so no dupes even if the file is re-read.
  If you omit it, a hash of (token, title, apply_url) is used.
- `posted_at` — ISO date or datetime. Anything older than
  `MANUAL_JOB_MAX_AGE_DAYS` (30 days, in `workers/ingest_jobs.py`) is
  silently skipped so stale files don't keep feeding old roles into matches.
- `is_remote` — set explicitly; the ingest also flips it to true if the
  location or description contains "remote" (case-insensitive).

## Registering the source

Once you have a JSON file for a token, add or enable a row in
`data/job_sources.json` (fresh installs only) or use the admin API on
the running DB:

```bash
curl -X POST -H "X-API-Key: $KEY" -H "X-User-Id: admin" \
  -H "Content-Type: application/json" \
  https://emploi-api.onrender.com/admin/job-sources \
  -d '{"company":"GTCO","ats":"manual","token":"gtco","priority":5,"region":"nigeria","active":true}'
```

Then run one ingest:

```bash
curl -f -X POST -H "X-API-Key: $KEY" \
  https://emploi-api.onrender.com/admin/run/ingest?background=false
```

## Freshness

`workers/spot_check_sources.py` covers curated tokens the same way it covers
ATS ones — a file that returns 0 non-expired jobs shows up as `DEAD` and
gets flipped by `workers/heal_job_sources.py`. Update the file each week
(or set a calendar reminder). A file untouched for >14 days is a candidate
for review, not a bug.
