# Emploi — End-to-End Performance & Reliability

_Research doc, 2026-07-18. What it takes for the whole pipeline to perform
reliably at scale. Grounded in the actual architecture, not generic advice._

## 1. The end-to-end flows

**Candidate:** sign in (Google) → build Career Twin (Gemini extract) → nightly
**match** scores fresh jobs against the twin → **notify** emails a digest →
candidate opens a match / a public job link → **generate** a tailored CV +
cover letter (Gemini) → apply.

**Employer:** sign in → onboard (trust check) → post a role (ATS API / generic
connector / paste) → **shortlist** (Gemini ranks opted-in twins) → invite /
unlock → candidate accepts, or applies inbound via the public job link.

**Sourcing (background):** **ingest** pulls from 130+ ATS boards + Jooble/Adzuna
aggregators → **verify-employers** scores domains → **backup** snapshots the DB.

## 2. Where time and money actually go

| Stage | Cost driver | Current posture |
|---|---|---|
| Ingest | HTTP fan-out over ~150 sources; Jooble 500/day cap | Hourly (high-pri) + daily (all); per-source fault isolation ✓ |
| Match | **Gemini calls = users × ⌈fresh_unmatched_jobs / batch_size⌉** | Incremental (only unmatched, capped `max_jobs`, batched) ✓ — the single biggest AI cost |
| Generate (CV/letter) | 2–3 Gemini calls per draft, on demand | Async job + poll; monthly per-user cap ✓ |
| Shortlist | 1 Gemini call per role over the opted-in pool | Cached per role; refresh is explicit ✓ |
| Verify | DNS/MX/HTTP + 1 optional Gemini call per domain | Cached per domain; nightly refresh of stale only ✓ |
| Web render | RSC + `apiFetch` round-trips to the API | `no-store` everywhere — **no caching yet** |
| Data | SQLite on one Render disk | Single writer; fine now, a ceiling later |

The design is already cost-aware in the right places (incremental matching,
batching, per-domain/role caching, on-demand generation). The gaps are in
**reliability, data durability, observability, and web-tier caching**, not in
the AI-call accounting.

## 3. Ranked bottlenecks & risks

**P0 — data durability (existential).** The entire product state is one SQLite
file on one Render disk, and `BackupWorkerRun` has *never* run (R2 unconfigured).
A disk incident = total loss of every Career Twin, employer, and application.
Nothing about "performance" matters more than not losing the data.

**P0 — worker liveness (was silently broken).** For ~4 days no worker ran
because the external cron `EMPLOI_API_KEY` was stale (401s, silent). Fixed by
the in-process scheduler (`INTERNAL_SCHEDULER=true`) + the admin control panel
now shows last-run/stale per worker. Keep this observable — a stalled match
means candidates see nothing new and the whole funnel dies quietly.

**P1 — matching cost/latency scales with users × jobs.** With 5k+ aggregator
jobs, the per-user cap (`max_jobs`) and `days_fresh` window are the throttles.
As users grow, one nightly match run's wall-clock and Gemini spend grow linearly.
Aggregator listings are also **noisy/duplicative**, inflating the job set the
matcher pays to score.

**P1 — SQLite single-instance ceiling.** One writer, no horizontal scaling; the
scheduler explicitly assumes a single instance. Fine at current volume; becomes
the wall when concurrent writes (applications, twins, matches) climb or you need
a second API instance.

**P1 — no web-tier caching.** Every dashboard/list render hits the API fresh
(`cache: "no-store"`). Public job pages (the acquisition surface) especially
should be cached/edge-served for fast, shareable loads.

**P2 — AI provider limits.** Gemini rate limits / transient outages are handled
per-call (502, Groq fallback configured), but a large match run can hit limits;
backoff + the fallback path need to stay healthy.

**P2 — email deliverability.** Brevo is configured; digest is the main retention
channel. Sender reputation + not emailing dead invites (already dedup'd) matter
for the funnel, less for "performance" per se.

## 4. What "100% end-to-end performance" requires

**Durability & liveness (do first):**
1. **Configure R2 backup** (`R2_ENDPOINT/ACCESS_KEY/SECRET_KEY/BUCKET`) and
   confirm `BackupWorkerRun` succeeds. Verify a restore actually works — an
   untested backup is not a backup.
2. **Monitor the pipeline.** The admin control panel now surfaces per-worker
   last-run + stale flags and config health. Add an alert (email/Slack/Sentry)
   when any daily worker is >26h stale, so the next silent stall is caught in
   hours, not days. (A Sentry connector exists — wire worker failures to it.)

**Matching efficiency (as users grow):**
3. **Pre-filter before the LLM.** Cheap deterministic pre-scoring (skills/title
   keyword overlap, remote/location, category) to drop obvious non-matches
   before spending a Gemini call — cuts the paid job set materially.
4. **De-dup aggregator jobs** on (normalized title + company + location) at
   ingest so the matcher isn't paying to score the same role twice.
5. **Tier the model.** Use the cheapest adequate model (or Groq) for the
   bulk match pre-score; reserve the strong model for generation/shortlist.
6. Keep matching **incremental** (already is) and cap per-run wall-clock so a
   growing pool can't blow past a run window.

**Data layer:**
7. **Plan the Postgres migration trigger** (it's on the roadmap): move when you
   need a second API instance, hit write-contention, or want real analytics.
   Until then, keep `PRAGMA journal_mode=WAL` in mind and watch the disk.
8. Confirm indexes cover the hot queries (they do today: `matches(user_id)`,
   `ingested_jobs(fetched_at)` back the incremental-match query).

**Web tier:**
9. **Cache the public job pages** (they're server-rendered per request today).
   Edge-cache with revalidation — they're the shareable acquisition surface and
   should load instantly worldwide.
10. Cache stable dashboard reads with short revalidation; stream where the API
    round-trip dominates. Measure Core Web Vitals on the candidate dashboard.

**Observability (the through-line):**
11. Ship structured worker events (already in `events`) to a dashboard/alert.
    The admin panel is step one; automated alerting is step two.
12. Track the funnel end-to-end: sign-in → twin-complete → first-match →
    first-application. A drop at any stage is a performance/UX problem to chase.

## 5. Prioritized action list

- **P0:** R2 backup + verified restore. Stale-worker alert.
- **P1:** LLM pre-filter + aggregator de-dup (cut match cost). Public-page edge cache.
- **P1:** Define the Postgres migration trigger; keep an eye on disk + write load.
- **P2:** Provider backoff hardening; funnel analytics; Core Web Vitals pass.

None of these are blocking today's scale — the pipeline works and is cost-aware.
They are the ordered list of what "100%" reliability and performance require as
Emploi grows from 11 Career Twins to thousands.
