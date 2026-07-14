# Emploi — Changelog

All notable changes to this project. Format loosely follows [Keep a Changelog](https://keepachangelog.com); dates are when the work shipped.

## [Unreleased]
Planned: more job sources (Jooble/Adzuna behind env keys, Workable, SmartRecruiters), generic career-page connector + company registry (design pass first), browser extension, WHOIS domain-age check, OCR for scanned CVs, curator partner pilot (Halo), BYOK option for users, Postgres migration when multi-instance is needed.

### Added — product sprint: editing, chat, search, import, notifications
- **Career Twin inline editing** (`web/components/CareerTwinEditor.tsx`): every section of the Career Twin page — name+headline, About, skills, experience, education, career goals — now has a pen-icon edit mode with save/cancel, persisting through the existing `PATCH /career-twin` partial merge. Fixes the long-standing "my name is in caps and I can't change it" gap; CV re-upload stays available but is no longer the only way to change anything.
- **Career Twin chat is live on /messages**: new `POST /chat` (FastAPI) wraps `core.chat_turn` — one Gemini call per turn, capped history, rate-limited 20/min. New `core.apply_chat_updates` maps chat's legacy update keys onto the Career Twin schema (`title→headline`, `goals` appended to `career_goals`, skills merged case-insensitively, experience/education appended as entries) so a chat remark never overwrites a curated profile. Plain-text fallback when the model ignores the JSON contract. Chat UI shows "Profile updated: …" chips when the Twin learns something.
- **Browse Jobs + working search** (`/jobs`): free-text `q` search over title/company/description added to `db.list_jobs`/`count_jobs` (LIKE-escaped so `%`/`_` can't match-everything), exposed via `GET /jobs?q=`, with a server-rendered search page (works without JS), remote-only filter, and per-job tailored-apply via the existing generation dialog. The topbar search box — static since the mockup — now actually submits to `/jobs?q=…` and ⌘K focuses it.
- **Import a job** (`/import-job`): the core Streamlit flow, finally in the dashboard — paste any JD (LinkedIn, WhatsApp, email) + company/contact → deterministic Trust Check with evidence → low-trust warning ("never pay a fee…", the product guardrail) → tailored generation with cost disclosure → one-click tracker entry. Linked from Job Matches, Browse Jobs, the sidebar-adjacent empty state, and the dashboard.
- **Notification bell is real**: dropdown fetches the user's latest matches ("title · company · fit") linking to /matches; unread dot only shows when there's something to see. Full notification center deferred until there are more event types worth showing.

### Fixed (post-launch, spotted in production data)
- **Greenhouse descriptions were stored as entity soup**: Greenhouse's `content` field arrives HTML-escaped (`&lt;div&gt;…`), so `_strip_html` saw no tags and stored the encoded markup verbatim — polluting stored descriptions, match prompts, and the generation dialog. `_strip_html` now unescapes (twice, for double-encoded payloads) before stripping; regression tests added. Existing rows self-heal on the next ingest run since `upsert_job` overwrites descriptions.

### Changed
- **Dashboard empty state is honest now**: the infinite "Scanning new opportunities…" spinners (nothing was running — matching is nightly) are replaced with static checkmarks stating the real cadence (hourly ingest, nightly matching, email digest) plus two things the user can do immediately: browse live jobs or import one.
- **Heavy worker triggers are async** (`/admin/run/{ingest,match,verify-employers}?background=true` default): Render's HTTP proxy kills responses after ~100s, so the synchronous triggers reported false failures for runs that actually completed (observed live: a 1,508-job ingest returned fine at ~95s; the match run's response was killed mid-run). Heavy triggers now return `202 started` immediately and run in a daemon thread; the authoritative outcome is the worker's own `events` row + service log. `?background=false` keeps the sync path (used by tests). Notify/backup finish in seconds and stay synchronous. `render.yaml` comments + curl timeouts updated to match.
- **Generation/chat proxy timeouts fixed**: `apiFetch` defaults to a 10s abort — a reviewed generation (3 Gemini calls) or a chat turn routinely exceeds that. The generate route now passes a 55s signal (latent bug: long generations were being aborted client-side), chat passes 40s.

### Fixed
- **Blueprint sync still failed after the cron/disk fix — a second, unrelated error:** `services[0] disks are not supported for free tier services`. `emploi-api` itself declared `plan: free` alongside its `disk:` block; Render doesn't allow a disk on any free-tier service, not just cron jobs — that combination was invalid before the cron work was ever added, it just hadn't been re-validated until this sync. The service is already running on a paid Render plan in production, so the YAML was simply out of date. Changed to `plan: starter` (the minimum paid tier that supports disks) — **verify this matches your actual billing tier in the Render dashboard**, since a Blueprint sync can change a live service's plan to match the file.
- **The last Render blueprint deploy silently failed — every cron service (`emploi-ingest`, `emploi-match`, `emploi-verify-employers`, `emploi-notify`, `emploi-backup`) never got created.** Root cause: **Render Cron Jobs cannot mount a persistent disk at all**, not even one shared with another service — a hard product limitation, not a config mistake ([Render docs](https://render.com/docs/disks): "Cron jobs can't provision or access a persistent disk"). `render.yaml` had a `disk:` block on every cron entry so the workers could reach the same SQLite file the API uses; that's invalid and broke the whole blueprint sync, which is why only the two original web services (`emploi-api`, `emploi`) ever showed up in the dashboard. Fixed by moving execution into the always-on API process instead: `api/main.py` gains `POST /admin/run/{ingest,match,verify-employers,notify,backup}`, authenticated by `X-API-Key` only (no per-user context — there's no user in a scheduled run), each calling the matching worker's `run()` in-process where the disk is already mounted. The cron services in `render.yaml` are now disk-free `curl -sf -X POST .../admin/run/<name>` calls on their existing schedules — `curl -f` means a worker failure surfaces as the cron's own failure, not just "the request was sent." Trade-off stated plainly in `05-services-and-workers.md`: a scheduled run briefly ties up the one running API process; revisit with a real task queue if that ever becomes noticeable at higher traffic. 7 new offline `test_api.py` checks cover all five endpoints via monkeypatched worker modules — no real network, Gemini, or R2 calls in CI. `docs/engineering/04-api.md` and `05-services-and-workers.md` updated to match the live topology (both were still describing the "planned" state).
- **Critical: generated applications were silently missing most of the Career Twin.** `core._profile_block` (used by `generate_application`, `build_cv_prompt`, `prepare_interview`, and the review pass) read the legacy flat-string `PROFILE_KEYS` (`title`/`experience`/`education`/`goals`) directly off the profile dict. Every wizard-onboarded user's Career Twin uses different keys (`headline`/`current_role`/`bio`/`career_goals`, no `experience`/`education` at all before this release) — so `_profile_block` rendered "None" for Title, Experience, Education, and Goals in every generation prompt since the wizard replaced the old onboarding flow. `_profile_block` now understands both schemas: it falls back through `title → headline → current_role`, `goals → career_goals`, joins list-valued skills/goals, and renders structured experience/education entries (see below) with a `bio` fallback when no structured experience exists. Regression tests assert no field renders "None" for a wizard-schema profile, and the legacy flat-string schema (still used by the Streamlit `extract_profile` path) is unaffected.
- **Missing feature, not a parsing bug: Career Twin had no structured experience or education at all.** `build_career_twin_extraction_prompt` never asked Gemini for work history or qualifications — only `name/headline/current_role/experience_years/location/skills/bio`. The Career Twin page's Experience/Education sections were rendering a feature that was never built. Extraction now also returns `experience`/`education` as `[{"summary": "one-line role/company/dates/achievement"}]` and `[{"summary": "one-line degree/institution/year"}]`, normalized and capped at 15 entries each (`normalize_entries`, `MAX_TWIN_ENTRIES`). The wizard's `CareerTwin` type, `EMPTY_TWIN`, and `mergeExtracted` now carry these fields through from upload to save.
- **Wizard's Activate step had no way back on failure.** Steps 4-7 already had a `NavButtons` back button; step 8's error state only offered "Try again", trapping a user whose save failed with no way to review or fix their earlier answers. Added a Back button returning to the Goals step, data intact.
- **Career Twin page had no way to update from a new CV**, despite the Settings page's copy explicitly promising one ("Update your profile from a new CV on your Career Twin page"). The `POST /career-twin/upload` endpoint already existed and already merges rather than replaces preference fields; it was just never wired into any UI outside the first-run wizard. New `UpdateCvButton` component on the Career Twin page uploads a PDF, re-extracts, and refreshes the page — preferences (career goals, salary range, etc.) are untouched since extraction never touches those keys.

### Changed
- **Notification sender switched Resend → Brevo:** `workers/notify_users.py` now builds its production `send_fn` from Brevo's transactional email API (`BREVO_API_KEY` + `BREVO_SENDER_EMAIL`), added as a nightly `emploi-notify` Render cron (30 2 * * *, after Worker 3) sharing the `emploi-data` disk. Missing config is still a safe no-op — never a false "sent". `docs/engineering/02-stack.md`, `05-services-and-workers.md`, `09-deployment.md`, and `HANDOVER.md` updated to match. New offline coverage: mocked `requests.post` asserts the Brevo payload shape and that a failed send raises (so matches are never marked notified on a bad send).

### Fixed
- **Production-loop wiring:** Dashboard, Job Matches, and Career Twin now read the authenticated user’s real API data. New users with no matches see the honest “getting to work” state; an unavailable API has a clearly labelled sample-data fallback rather than silently showing fictional opportunities.
- **Apply flow:** real job IDs, fit scores, and ATS URLs are recorded in the application tracker; after a successful record, a valid employer URL opens in a separate tab. Malformed source URLs cannot break tracking.
- **API resilience:** costly trust, extraction, upload, and match endpoints now have an in-process per-user rate limit. SQLite waits up to 30 seconds for a competing worker/API write rather than immediately failing on normal lock contention. Added API regression coverage for the verification limit.
- **Web quality gate:** removed the onboarding animation’s synchronous effect-state update and stale unused state; `npm run lint` and `npm run build` now pass cleanly.

### Changed
- **Spec drift fixed (HANDOVER §15):** `docs/engineering/03-database.md` now documents all seven as-built tables (career_twins rename, ingested_jobs, employer_trust_records, matches + notified migration, job_sources, events), the backup worker, and the additive-migration rule; `04-api.md` documents the live career-twin, jobs, matches, generation, deletion, and admin job-source endpoints plus the per-user rate limits and 502/503 degradation contract.

### Added
- **Streamlit admin guard (HANDOVER §14):** the legacy chat/console no longer has to run publicly as a free Gemini wrapper. Opt-in `EMPLOI_ADMIN_CODE` (access code before render) and `EMPLOI_ADMIN_EMAILS` (Google-sign-in allowlist via new tested `core.admin_allowed`, fails closed on missing email) locks; both unset = local dev unchanged. `render.yaml` now marks the code as a required prod secret.
- **DB backup worker (Worker 5):** `workers/backup_db.py` snapshots the production SQLite file with the online backup API (consistent against concurrent writers), integrity-checks the snapshot, and uploads it to Cloudflare R2 as `backups/emploi-YYYY-MM-DD.sqlite3`. Missing R2 configuration or upload failure is a clean non-zero exit — nothing is ever reported as backed up that wasn't. Nightly Render cron added (03:00, after ingest/verify/match); offline suite `test_backup_db.py` in CI; `boto3` added (lazy-imported, backup cron only).
- **Notification foundation:** Career Twin activation records the authenticated email, matches have additive `notified` migration fields, and the offline-tested notification worker sends one digest per user and marks matches only after a successful injected delivery. A production Brevo sender remains intentionally unconfigured until `BREVO_API_KEY`/`BREVO_SENDER_EMAIL` and a verified sending domain are supplied (see the Brevo switch entry above).
- **Tailored application UI:** Job Matches now opens a reviewed-draft dialog instead of immediately recording an application. It discloses the 3-call reviewed / 2-call unreviewed Gemini cost, displays and copies the returned draft and fit score, then records the application before opening a validated ATS URL. Match joins now include the job description required for grounded generation.
- **Dashboard legal pages:** public `/privacy` and `/terms` routes now explain CV/Gemini processing, retention and deletion, Trust Check limits, responsible AI use, and the never-pay-a-fee safety rule. Login links now remain within the app, supplying stable URLs for the Google OAuth consent screen.
- **Ashby job ingestion:** Worker 1 now supports public Ashby posting feeds alongside Greenhouse and Lever, normalizing either documented response shape and retaining the same source-level fault isolation and deduplication. Offline tests cover a full Ashby write and repeat-run idempotency.
- **Account deletion UI:** added Settings navigation and the authenticated `/api/user` delete proxy. The settings page requires a second explicit confirmation, handles backend failure without losing the page, and signs the user out only after the API confirms permanent NDPA/GDPR erasure.
- **Tailored-application API:** `POST /applications/generate` now uses the stored Career Twin and `core.generate_application`, exposes the parsed fit score, and returns clear 503/409/422 failures instead of raw provider errors. The server-only Next.js proxy has the same 60-second execution allowance as CV extraction; API contract tests cover all response paths.
- **Employer verification refresh worker:** `workers/verify_employers.py` refreshes stale direct-company domains nightly, records deterministic trust results, and deliberately skips Greenhouse, Lever, and Ashby hostnames so an ATS is never misrepresented as the employer. Its fully offline regression suite is now part of CI.
- **Render scheduling and CI coverage:** added hourly/high-priority and daily/full ingestion, nightly verification refresh, and nightly matching cron definitions sharing the API database path; CI now runs worker verification/ingestion and the web lint/build gates.

## [0.12.1] — 2026-07-13 — Worker 3 (matching), job source registry, 130-company seed
### Added
- **`workers/match_users.py`** — Worker 3 (the product feature): for every user with a completed Career Twin, fetches fresh unmatched jobs (SQL anti-join on `matches`, configurable `--days-fresh` window), batches them through `core.match_jobs` (one Gemini call per batch of 50), and upserts ranked results into `matches`. A single user failure never stops the run. `--dry-run` prints what would be scored without calling Gemini or writing. `--min-priority` and `--batch-size` flags. Returns `{ok, users_processed, total_matches, total_calls, errors, dry_run}`. Designed to run nightly on Render Cron after Worker 1.
- **`db.py` — `job_sources` table + admin functions**: `seed_job_sources(conn, path)` — idempotent seed from JSON (no-op if table is already populated; DB is source of truth after first seed). `list_job_sources`, `upsert_job_source`, `set_job_source_active`, `get_job_source` for admin-API-managed source registry.
- **`data/job_sources.json` rewritten** — 130 companies across 8 categories (`african_tech`, `remote_global`, `ai`, `developer_tools`, `enterprise_saas`, `fintech`, `large_tech`, `nigerian_companies`). Each entry carries `{company, ats, token, priority, region, active}`. Priority 10=hourly, 7=every 3h, 5=twice daily, 1=daily. Nigerian banks and large tech (no public ATS APIs) marked `active: false` so they're seeded but idle until we add custom scrapers.
- **`api/main.py` — admin job-source endpoints**: `GET/POST /admin/job-sources`, `PATCH /admin/job-sources/{id}`, `PATCH /admin/job-sources/{id}/toggle`, `POST /admin/job-sources/seed`. Auto-seeds from JSON on first `GET`. Allows adding/disabling sources and changing priority without redeployment.
- **`workers/ingest_jobs.py` updated** — now reads source list from `job_sources` DB table (seeded on first run from JSON). `--min-priority N` flag to run only high-priority sources on frequent schedules. `_ATS_HANDLERS` dict for extensible ATS support (Greenhouse + Lever live; others skip gracefully).
- **`test_ingest.py` rewritten** — now covers both Worker 1 (ingest) and Worker 3 (match): 37 checks total. New tests: rich JSON seed format, `job_sources` seeding idempotency, `min_priority` filter, Worker 3 match production, idempotency (anti-join), `onboarding_complete` guard, dry-run no-write, `batch_size=1` multiple-call validation.

All 5 suites green (`test_e2e`, `test_verify`, `test_db`, `test_api`, `test_ingest`).

## [0.12.0] — 2026-07-13 — Job sourcing: ingestion worker + sourcing API
### Added
- **`db.py` — 4 new tables** (`ingested_jobs`, `employer_trust_records`, `matches`, `events`) with full index set and `UNIQUE` dedup constraints. New functions: `upsert_job`, `list_jobs`, `count_jobs`, `upsert_trust_record`, `get_trust_record`, `upsert_match`, `list_matches`, `log_event`. `clear_user` extended to wipe `matches` and `events` for the deleted user (NDPA/GDPR). All type annotations backported to `Optional[…]` for Python 3.9 compatibility.
- **`workers/ingest_jobs.py`** — Worker 1: fetches jobs from public Greenhouse board API (`/v1/boards/{token}/jobs?content=true`) and Lever postings API (`/v0/postings/{slug}?mode=json`), normalises to the shared job dict shape, upserts into `ingested_jobs` with dedup on `(source, source_job_id)`. Per-source `try/except` — one dead board never kills the run. Polite `0.5s` rate-limit sleep between requests. `--dry-run` flag prints what would be written, touches nothing. Injectable `fetch_fn` seam for offline tests.
- **`data/job_sources.json`** — curated company board tokens: 24 Greenhouse + 16 Lever, remote-friendly companies known to hire in Africa/EMEA (Andela, Deel, Flutterwave, Paystack, Stripe, GitLab, Automattic, etc.). Edit freely — the worker reads this file each run.
- **`GET /jobs`** — list ingested jobs with optional `?remote_only=true`, `?category=`, `?limit=`, `?offset=` filters. Returns `{jobs, total, limit, offset}`. Limit capped at 200. **`GET /jobs/{id}`** — single job by id (404 if not found). **`GET /matches`** — user's pre-computed match rankings from the matches table (empty until the matching worker runs), best fit first.
- **`web/app/api/jobs/route.ts`**, **`web/app/api/matches/route.ts`** — Next.js proxy routes forwarding to the FastAPI backend with the standard `apiFetch` auth and error handling.
- **`test_ingest.py`** — 15 offline tests: utility helpers, fake Greenhouse/Lever HTTP responses, 3-job write, idempotency, `--dry-run` leaves DB empty, missing sources file graceful error.
- **`test_db.py`** extended with 6 new checks for all new table functions.
- **`test_api.py`** extended with 10 new checks for `/jobs` and `/matches` endpoints (filtering, 404, limit validation, match roundtrip).

All 5 suites green (`test_e2e`, `test_verify`, `test_db`, `test_api`, `test_ingest`). Next.js production build clean (27 pages).

## [0.11.4] — 2026-07-13 — Trust signal: bot-blocked sites no longer punished
### Changed
- **`fetch_site` 403 semantics resolved** (the 0.11.0 flagged item, decided with Joy): bot-defense statuses `{401, 403, 405, 429}` now count as "site exists" — a configured server/CDN answering proves the same infrastructure bar as a 200 (parked/dead domains can't produce them), so legitimate CDN-fronted employers (e.g. paystack.com) no longer swing 30 points down. The content-consistency LLM check is **skipped** for blocked sites (`site_content` stays absent — observed evidence only, never guessed), and the evidence line says so honestly: "website answers (bot protection blocked our content check)". 404/410/5xx and connection failures still count as no reachable website. Regression tests: 403 scores equal to a live site sans content judgment, the model is provably never called (exploding fake), 404/connection-failure semantics unchanged.

## [0.11.3] — 2026-07-13 — Gotcha sweep + branded loading (LoadingMark)
### Added
- **`LoadingMark`** (`web/components/LoadingMark.tsx`): the animated Emploi logo loop from the design handoff — 3 mark bars pulsing in a cascading wave (1.15 s cycle, 0.16 s stagger, scaleY 1→1.16 + opacity 0.5→1, cosine curve), pure CSS keyframes, `prefers-reduced-motion` respected, `role="status"` for screen readers. Replaces the generic Sparkles pulse-circles in wizard steps 3/8; new route-level `loading.tsx` for the `(app)` group and the wizard show it during server-render waits. Synced to the claude.ai/design system project (11 components now).
- **Branded error surfaces**: root `error.tsx` (glass card matching login), `(app)/error.tsx` (in-shell retry, sidebar keeps working), `not-found.tsx` (branded 404) — no user ever sees Next.js's unstyled error screen.
### Fixed
- **`apiFetch` had no timeout** — a hung backend request stalled server renders indefinitely. Now 10 s `AbortSignal.timeout`, with timeout mapped to `ApiUnavailableError` (demo-data fallback paths already handle it). "not authenticated" now carries status 401 instead of surfacing as 500.
- **Applications page: a network throw during a status change skipped the optimistic-update revert** and surfaced as an unhandled rejection — now caught and reverted.
- **Gemini provider failures returned raw 500s**: `run_extraction()` in `api/main.py` wraps every model-backed endpoint (extract, upload, matches, legacy) — rate limits/outages now return a clean 502 "temporarily unavailable" (regression-tested with a raising fake model).
- **No upload size ceiling on the API**: `/career-twin/upload` reads at most 15 MB and 413s beyond it (client caps at 10 MB, but the API must not trust callers). Career-twin PATCH payloads capped at 64 KB (JSON-in-SQLite protection). Tests for both.
- **API key comparison is now timing-safe** (`secrets.compare_digest`).
- Application id path segment URL-encoded in the web PATCH proxy.

## [0.11.2] — 2026-07-13 — Onboarding extraction fixed end-to-end (launch blockers cleared)
### Fixed
- **CV extraction returned the wrong schema — the wizard form opened blank.** The API extracted legacy `PROFILE_KEYS` (`title`, `experience`, `skills` as a comma-string) while the wizard expects `headline`/`current_role`/`experience_years`/`skills[]`/`bio` — only `name` and `location` ever matched, so users saw an empty form with just their name. New `core.extract_career_twin()` (own prompt + `parse_career_twin_json`) returns the wizard's exact schema with deterministic normalization: skills always a clean list (comma/semicolon strings split), `experience_years` mapped onto the wizard's `<select>` buckets (`normalize_experience_years`), all-empty objects rejected as failed extractions. Both `/career-twin/extract` and `/career-twin/upload` use it. 17 new offline checks in `test_e2e.py`, API contract checks updated in `test_api.py`.
- **Latent crash: comma-string skills would `tags.map()`-crash step 5.** The wizard now merges extracted data defensively (`mergeExtracted`): only known CareerTwin keys, only non-empty values, list fields coerced to arrays even if an older API build sends strings — verified in-browser (mock upload with comma-string skills renders three chips, no crash).
- **Fake progress: the extraction checklist checked off items on a 450 ms timer**, reporting success while Gemini was still generating. `AnimatedChecklist` reworked: the current stage always shows a spinner, a checkmark only means "moved past this stage", and the final stage can never complete on a timer — the step advances only when the fetch actually resolves. The skip path no longer plays extraction theater at all: no file → straight to a "Tell us about yourself" manual form (no "AI Extracted" badge, no resume-reading animation). All timers on the upload path are gone — no race is possible.
- **"All set" shown even when the profile save failed** (step 8 swallowed errors), which then bounced the user back to the wizard on next login. Activation now verifies both the PATCH and `/complete` responses and shows a branded retry screen on failure.
- **Vercel could kill the upload mid-extraction**: `/api/career-twin/upload` now sets `maxDuration = 60` (Gemini takes 10–30 s; the default function limit is shorter).
- **`python-multipart` added to requirements.txt** — required by FastAPI's `UploadFile`; was only present transitively.
- **Demo data drift**: `experience_years: "4"` didn't match any wizard select option (renders blank) — now `"4 years"` in all three demo payloads.
### Added
- **Branded sign-out page** (`/signout`, wired via NextAuth `pages.signOut`): matches the login page design (logo, brand orbs, glass card), shows the signed-in user's name, confirm + go-back actions — replaces NextAuth's unbranded default.
### Notes
- The 0.11.1-era race-condition fix (`cc46fd9`) had never been pushed — production was still running the old timer code, which is why the bug appeared "unfixed". This release ships everything.

## [0.11.1] — 2026-07-12 — Production deploy fixes (app.emploihq.com live)
### Fixed
- **`emploi-api` 500s on every DB endpoint in production**: `render.yaml` set `EMPLOI_DB_PATH=/var/data/emploi.sqlite3` but the disk block was commented out, so `/var/data` never existed and `db.connect()` raised on each request (surfaced as 500 on `/applications`). Disk block is now active (1 GB at `/var/data`) — running on a paid Render plan.
- **App favicon**: `web/app/icon.svg` added with the landing page's logo SVG (extracted from its inline data URI) so app.emploihq.com no longer shows the default favicon.
### Added
- **`/emploi` project skill** (`.claude/skills/emploi/SKILL.md`, now versioned): architecture map, auth chain, env matrix, test commands, deploy runbook, and known production gotchas — so any Claude session starts with the full operating picture.
### Notes
- Live topology: web on Vercel at app.emploihq.com, api on Render at emploi-api.onrender.com, landing headed to Hostinger. Vercel env vars set (AUTH_SECRET, AUTH_URL, Google OAuth pair, EMPLOI_API_URL/KEY). Google OAuth is still in Testing mode — sign-in only works for whitelisted test users.

## [0.11.0] — 2026-07-12 — Live backend: FastAPI service, real trust checks, real tracker
### Added
- **`api/` — FastAPI service** (thin dispatch over `core.py`/`verify.py`/`db.py`, zero business logic): `/health`, `/profile` GET/PUT, `/resume/extract` (Gemini, persisted), `/verify` (deterministic trust engine, per-domain cache), `/applications` CRUD with ownership checks + status whitelist, `/matches` (Gemini), `DELETE /user` (NDPA/GDPR erasure). Service-to-service auth: `X-API-Key` shared secret + `X-User-Id` asserted by the web tier; open-dev-mode warning when unkeyed. AI endpoints return a clear 503 without `GEMINI_API_KEY`; `/verify` works fully without it.
- **`test_api.py`**: 33 offline checks (auth matrix, profile round-trip per user, fenced-JSON extraction, garbage-output 422, red-flag cap intact through the API, one-probe-per-domain caching, CRUD + cross-user 404, full deletion). Wired into CI. New deps: fastapi, uvicorn, httpx.
- **Dashboard is now live, not a mock**: Trust Check page runs real deterministic checks (verified in-browser: scam posting with fee/WhatsApp text scored 5/100 AVOID with named red flags vs 45/100 for a bare corporate contact); Matches "Apply" creates a real tracked application; Applications page reads from SQLite, status changes PATCH and survive reload — with an explicit "sample data" banner fallback whenever the API is offline. Server-only API client (`web/lib/api.ts`) keeps the shared secret out of the browser.
- **Engineering Specification v2.0**: `docs/engineering/01–09` (overview/invariants, stack, database, API contracts, services & workers, AI layer, frontend, auth & security, testing/deployment/roadmap) — AI-native, each section with acceptance criteria; root `SPEC.md` rewritten as the index.
- Deployment: `render.yaml` gains the `emploi-api` service (health check, disk-ready); DEPLOY.md documents the three-tier topology, env matrix, and deploy order.
### Flagged (needs Joy's call — trust-signal semantics)
- `fetch_site` treats HTTP 403 as "no reachable website"; bot-blocking sites (e.g. paystack.com) lose the site-up signal. Counting 403 as "site exists" would change point semantics — not touched per the trust-scoring change policy.

## [0.10.0] — 2026-07-12 — Next.js SaaS dashboard (web/) with Google sign-in
### Added
- **`web/`: the Career Twin dashboard as a real SaaS app** (Next.js 16, React 19, Tailwind v4, TypeScript), matching the approved mockup and the landing-page design system. Routes: `/login`, `/dashboard` (greeting, Career Twin hero with bot illustration, Top Job Matches with fit rings, Recent Applications table, right rail: profile-strength ring + checklist, Trust Check card, Application Overview stats), `/matches`, `/applications` (status-filterable table), `/trust-check`, plus consistent placeholders for Messages/Saved/Interview Prep/Insights/Career Twin/Recruiter Workspace. Sidebar (with Upgrade card + Free-plan meter) collapses to a drawer on mobile; topbar has search, notifications, and an account menu with sign-out.
- **Auth**: NextAuth v5 with Google sign-in (env-configured, see `web/.env.example`); every `(app)` route is server-side protected (unauthenticated → `/login`, verified 307). A `AUTH_DEV_LOGIN=true` demo login (dev-only, disabled in production builds) lets the signed-in dashboard be exercised before Google OAuth credentials exist. Sign-in, sign-out, drawer, and filters all verified in-browser.
- `web/lib/data.ts`: typed demo data marked as the seam for the future FastAPI backend wrapping `core.py`/`verify.py` (zero logic was duplicated from Python).
### Changed
- Landing page local dev rewrite now points app CTAs at the Next.js dashboard (`localhost:3000`); production target stays `app.emploihq.com`. The Streamlit chat app remains unchanged on `:8501` as the working generation product.
### Notes
- Next 16 deprecates `middleware.ts` (renamed `proxy.ts`, discouraged) — route protection is done in the `(app)` layout via `auth()` + redirect instead.
- `npm run build` and `npm run lint` pass; all four Python suites still green.

## [0.9.4] — 2026-07-12 — Mobile navigation + mobile hero-mock fixes
### Added
- Mobile hamburger menu on the landing page (nav links were simply hidden under 820px with no way to reach them): glass dropdown panel with all section links + Log in, animated burger→X icon, `aria-expanded`/`aria-controls`, closes on link tap. 7 new checks in `test_landing.py` (suite: 65).
### Fixed
- Hero dashboard mock on small screens: the 4-column stat row overflowed the card (4th stat clipped off-screen, labels wrapping badly — reported via screenshot). Stats now collapse to a 2×2 grid under 560px with tightened card padding. Verified at 375px: all four stats visible, no horizontal overflow.

## [0.9.3] — 2026-07-12 — Domain → emploihq.com, Crost Limited identity, visual audit
### Changed
- **Domain**: all links, emails and app URLs moved from emploi.ng to **emploihq.com** (hello@/support@emploihq.com, app.emploihq.com, og:url, footers) — now matching the `@emploihq` social handles.
- **Legal pages are official**: "draft for legal review" banners removed from `landing/privacy.html`, `landing/terms.html` and the `docs/` sources. Both pages (and the landing footer) now carry the operator identity: **Emploi is a brand of Crost Limited, registered in Nigeria (RC 9526947)**; copyright line is © 2026 Crost Limited. Terms gained a "Who we are" section; placeholder contact/entity notes in the docs filled in.
- **Positioning copy**: no longer "remote job seekers in Africa & Asia" — now "Starting in Africa, built for the world" (meta description, footer blurb); trust-section copy generalised.
### Fixed (visual audit, desktop/768px/375px, all three pages)
- `.hero`/`section.block` shorthand paddings were overriding `.wrap`'s horizontal padding — content touched the screen edge on viewports under ~1170px. Now only vertical paddings are set.
- Hero headline overflowed its grid track and touched the right edge at 375px — grid children get `min-width:0` and the h1 steps down to 2.1rem under 420px. Verified: no horizontal overflow on any page at 375px.
### Tests
- `test_landing.py` extended to 58 checks: emploihq.com everywhere with no stale emploi.ng, Crost Limited + RC 9526947 on every page, no draft language remains, Africa-first/global positioning present, no remote-only copy.

## [0.9.2] — 2026-07-12 — Landing page goes direct-to-product + full link audit
### Changed
- Landing page no longer collects a waitlist — the app is live, so every CTA (nav, hero, both pricing plans, final section, footer "Log in") now sends users straight into the product to sign in and set up their Career Twin. App links point at `https://app.emploi.ng` and are rewritten to `http://localhost:8501` by a small script when the page is browsed locally, so every link works in dev too.
- Footer Privacy/Terms no longer point at raw `../docs/*.md` (broken on any static host): new brand-styled `landing/privacy.html` and `landing/terms.html`, generated from the docs drafts, both still carrying the "draft for legal review" banner. Privacy storage section updated to reflect signed-in persistence (0.9.0) instead of "nothing is stored".
- App sign-in screen and chat greeting rebranded to Career Twin ("Sign in, drop your CV, and your Career Twin is saved across sessions") — copy only, no logic changes.
### Added
- `test_landing.py`: offline link audit (45 checks) — every in-page anchor resolves, local file links exist, all app CTAs target the product, social links use `@emploihq`, contact emails use `@emploi.ng`, no waitlist copy remains, legal pages cross-link and keep the never-pay-a-fee warning. Wired into CI.
### Verified
- Streamlit app boots on `localhost:8501` and the landing CTAs resolve to it locally; `privacy.html`/`terms.html` serve 200 and render.

## [0.9.1] — 2026-07-11 — New landing page (Career Twin brand)
### Changed
- `landing/index.html` rebuilt around the new purple "Career Twin" brand: glassmorphism (frosted nav, cards, score panel), kinetic animations (floating gradient orbs, staggered hero text, animated dashboard mock with count-up stats and fit-score rings, 3D hover tilt, logo marquee, scroll-triggered reveals, live trust-score countdown to 10/100 AVOID), inline new logo SVG + favicon. Sections: hero, how-it-works (5 steps), why-Emploi (4 cards), scam-protection demo, pricing (Free ₦0 / Pro ₦3,500 early-bird, consistent with business/one-pager.md), waitlist CTA (mailto fallback until a form backend is connected), footer. Respects `prefers-reduced-motion`; responsive down to 375px (nav CTA collapses to "Get started"). Still a single static file, zero JS dependencies, deployable to any static host.
- All contact addresses now use the planned domain: hello@emploi.ng / support@emploi.ng. Footer social links point at the recommended handle `@emploihq` (checked available on X, GitHub, YouTube; likely on TikTok/Instagram — not yet registered).
### Notes
- Domain check (2026-07-11): `emploi.ng` is unregistered at NIRA (NXDOMAIN) — register soon. `emploi.com.ng` is an active, unrelated "freelancing platform" (Instagram `@emploi_ng`, ~466 followers) — brand-collision risk to monitor. `@emploi` is taken on X, Instagram and GitHub.

## [0.9.0] — 2026-07-05 — Google Sign-In + per-user persistence
### Added
- **Google Sign-In** via Streamlit-native OIDC (`st.login`/`st.user`, Authlib). Enabled by adding an `[auth]` section to secrets (template: `.streamlit/secrets.example.toml`; setup steps in DEPLOY.md). Without it the app runs exactly as before — anonymous, session-only, nothing persisted.
- **Per-user persistence** for signed-in users: profile and tracker stored via `db.py` (keyed by Google `sub`), hydrated once per session, profile saved on change. `EMPLOI_DB_PATH` env var selects the SQLite file.
- `db.clear_user()` — "Clear all data" now also deletes a signed-in user's stored data (NDPA/GDPR deletion right); `db.connect()` gained `check_same_thread` for Streamlit's shared cached connection. 3 new offline checks in `test_db.py`.
### Security notes
- No passwords stored anywhere; identity comes from Google's OIDC claims. Cookie secret and OAuth credentials live in gitignored secrets only.

## [0.8.0] — 2026-07-05 — Shared blacklist/whitelist + startup scaffolding
### Added
- **Shared employer blacklist/whitelist** (`data/blacklist.json`, loaded by `verify.load_lists`). A blacklisted domain caps trust at 10 (Avoid) regardless of other signals; a whitelisted domain adds +20 but never overrides red flags (cap 35 stands). File ships empty; missing/malformed file degrades to empty sets — verification never crashes on data problems. 8 new offline checks in `test_verify.py`.
- **Persistence scaffold** (`db.py` + `test_db.py`, 10 offline checks): SQLite storage for profiles (JSON blobs, schema-flexible) and tracker entries, keyed by `user_id`. Deliberately NOT wired into the app — on a shared deployment, persisting without auth would leak one user's CV to the next visitor. This is the data layer for the persistence roadmap item; integration waits for auth.
- **CI**: `.github/workflows/test.yml` runs all three offline suites on every push/PR.
- **Startup scaffolding**: `LICENSE` (proprietary, with MIT attribution for the adapted skill prompts), `.env.example`, `docs/PRIVACY.md` + `docs/TERMS.md` (drafts flagged for legal review — NDPA/GDPR aware), `business/one-pager.md` + `business/unit-economics.xlsx` (live-formula model: ~$0.02 API cost per application, ~86% gross margin at ₦3,500/mo; Gemini pricing and CBN FX sourced July 2026), `landing/index.html` (static, deployable to any static host — static HTML is fine on Vercel/Netlify, unlike the Streamlit app).

## [0.7.0] — 2026-07-04 — Conversational memory + profile self-updates
### Added
- Chat is now context-aware: the last 8 messages ride along with every conversational turn.
- The agent can update the profile from conversation — "I want senior marketing roles" updates the goals field (only known profile keys accepted; the reply confirms what changed). Structured `{"reply", "profile_updates"}` protocol with graceful fallback to plain text.
- Friendly quota errors: 429s now explain the free-tier limit (20 requests/day) and the retry window instead of dumping the raw API error; all handler error paths use the same formatter.

## [0.6.1] — 2026-07-04
### Changed
- Cover-letter downloads no longer include the Fit Evaluation section — downloads contain only sendable content; the evaluation stays on-screen (a user could otherwise have attached the gaps analysis to a real application). Handles both current and legacy section headers.

## [0.6.0] — 2026-07-04 — Full tailored CV generation
### Added
- Every application now produces a COMPLETE ready-to-send CV (not just bullet suggestions), downloadable as PDF/Word/text alongside the cover letter.
- `skills/cv_template.md`: CV structure, relevance-weighted content selection (cut lowest-value bullets first, posting-relevant content survives regardless of recency), ground-truth-only rules with "(stretch — verify)" marking.
- Sidebar shows API-call cost per application (3 with reviewer pass, 2 without).

## [0.5.2] — 2026-07-04
### Fixed
- PDF/Word downloads dumped raw markdown (`##`, `**`, `*` bullets, `|` tables) and mangled ₦ into `?`. Exports now render markdown properly: bold headers, real bullets, formatted table rows, currency-safe text. Regression tests do a full PDF→text roundtrip asserting no markdown tokens survive.

## [0.5.1] — 2026-07-04
### Fixed
- Slash-prefixed commands (`/verify`, `/apply 2`, `/batch 3`, `/tracker`) were falling through to the career-chat handler; the intent router now strips a leading `/`. Regression tests added (suite: 60 checks).

## [0.5.0] — 2026-07-04 — Employer verification (scam protection)
### Added
- `verify.py`: deterministic trust engine. Score (0–100) computed in code from named evidence: free-mail vs corporate contact domain, DNS + MX records, live website, company-name/domain consistency, scam-pattern lexicon (fee requests, WhatsApp-only contact, crypto salaries, unrealistic pay). Any red flag caps the score at 35; no contact info caps at 40 ("unverified", never guessed).
- Gemini's only verification role: one narrow judgment on fetched homepage content (consistent / inconsistent / unclear); errors degrade to "unknown".
- Trust column (🟢🟡🟠🔴) in match results; automatic verification + low-trust warning on `apply`; `verify 2` / `verify info@company.com` shows full evidence. Per-session domain cache (network probed once per employer).
- `test_verify.py`: 27 offline checks with injected DNS/HTTP/LLM fakes covering every scoring path.
- New deps: `requests`, `dnspython`. Job extraction now also captures the contact field.
### Known limits (documented in README)
- No WHOIS/domain-age, no LinkedIn/Glassdoor checks; a scammer with a real website can still pass. Risk reduction, not a guarantee.

## [0.4.0] — 2026-07-04 — Skills system (prompt IP port)
### Added
- `skills/` folder: markdown prompt modules injected into every Gemini call, editable without code changes. Adapted from [MadsLorentzen/ai-job-search](https://github.com/MadsLorentzen/ai-job-search) (MIT).
  - `writing_style.md` — hard anti-cliché rules, forward-looking cover-letter framing, "interview backtrack test" against overclaiming (stretchy CV bullets get flagged "(stretch — verify)").
  - `evaluation.md` — five-dimension weighted fit rubric (skills 30 / experience 25 / culture 15 / career alignment 30 + location gate), verdict thresholds, honest-scoring rules (must name gaps; warns when experience match < 50).
  - `interview_prep.md` — STAR prep from the candidate's real experience, tough-question answers, questions to ask, roleplay mode.
- `interview` chat command (`interview`, `interview 2`, `interview Acme`).
- Reviewer pass now enforces the style guide and re-checks over-generous fit scores.

## [0.3.0] — 2026-07-04 — Smarter documents + server-side key
### Added
- PDF classification: every uploaded PDF is classified (CV / job listings / other) before processing — job-listing PDFs no longer get mangled by the CV parser.
- Job extraction from listing PDFs (e.g. Halo hiring sheets) → ranked matching against the profile in one call (fit score + reason per job) → `apply 1` / `apply <company>`.
- `match` command for ranked matching over any loaded job source.
- API key resolved server-side from `GEMINI_API_KEY` env var or Streamlit secrets; users never see a key field in production (sidebar input remains as dev-mode fallback). Shared-key model for the pilot; BYOK later.
### Fixed
- Company-column detection for terse sheet headers ("co", "org").

## [0.2.0] — 2026-07-04 — Agent chat UI + CV auto-fill
### Changed
- Replaced the tab-based UI with a single chat interface; an intent router dispatches uploads and commands (CV PDF → profile, sheet → jobs, pasted JD → generate, `batch N`, `tracker`, free text → career coach with profile context).
### Added
- CV PDF upload → Gemini extracts the full profile automatically (no manual form); editable in sidebar.
- `core.py` split from `app.py` (all logic UI-free and testable).
- Deploy files: `render.yaml` (Render blueprint), `Dockerfile` (Cloud Run-ready), `DEPLOY.md`.
### Fixed
- fpdf2 multi-line rendering bug (cursor position after `multi_cell`).

## [0.1.0] — 2026-07-04 — Initial release
- Named **Emploi** (checked: no existing AI job tool with the name; note: collides with generic French usage).
- Streamlit app: profile form, CSV/Excel job-list import, Gemini-tailored cover letter + CV bullets + fit score, application tracker with CSV export.
- Reviewer pass (second Gemini call critiques and tightens drafts; original draft preserved).
- Batch mode across imported job sheets, ranked by fit.
- PDF / Word (.docx) / text downloads.
- Offline test suite with a fake Gemini model (no API key needed).
