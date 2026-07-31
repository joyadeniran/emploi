# 05 — Backend Services & Background Workers

The "services" are logical seams inside the Python core, not microservices. Do not split processes until scale forces it — the seams below keep that option open.

## Services (as built)

| Service | Lives in | Responsibilities |
|---|---|---|
| Career Twin | `core.py`: `extract_profile`, `parse_profile_json`, `chat_turn` | CV → structured profile; conversational profile updates (`{"reply","profile_updates"}` protocol, only known keys accepted) |
| Trust | `verify.py` | Deterministic scoring from named signals; blacklist/whitelist (`data/blacklist.json`); per-domain caching |
| Matching | `core.py`: `match_jobs`, `build_match_prompt` | Weighted fit scoring against the profile (rubric in `skills/evaluation.md`) |
| Application | `core.py`: `generate_application`, `generate_cv`, `batch_generate`, exports (`make_pdf`, `make_docx`) | Tailored cover letter + full CV; markdown-safe, currency-safe exports |
| Interview | `core.py`: `prepare_interview` | STAR prep from real experience only |
| Persistence | `db.py` | Profiles, applications, deletion right |
| API | `api/main.py` | HTTP dispatch over all of the above (see 04-api.md) |

## Background workers (as built)

Each worker is a standalone script (`workers/<name>.py`), runnable manually with `python3 workers/<name>.py [--dry-run]` against any SQLite file. Every `run()` function is also callable in-process — this is load-bearing (see "Scheduling" below) — so never give a worker's `run()` a side effect that only makes sense from a CLI entry point (argument parsing, `sys.exit`, etc. stay in `if __name__ == "__main__":`).

### Worker 1 — Job ingestion (`workers/ingest_jobs.py`)
- **Inputs:** public, keyless board APIs — Greenhouse, Lever, Ashby, Workable, SmartRecruiters and **Workday** (`{tenant}.{wd}.myworkdayjobs.com/wday/cxs/...`, token `tenant:site` or `tenant:wdN:site`; the bank/corporate tier that Greenhouse/Lever never covers — SuccessFactors/Taleo need per-tenant credentials so they stay `career_page` placeholders) — plus the env-keyed aggregators Jooble (`JOOBLE_API_KEY`, token `location:keywords`, the main Nigeria volume lever) and Adzuna (`ADZUNA_APP_ID`/`_KEY`, **no Nigeria endpoint**). Source list comes from the `job_sources` DB table, seeded once from `data/job_sources.json`; add/disable sources via `/admin/job-sources` after that.
- **Output:** rows in `ingested_jobs` (03-database.md), deduped on `(source, source_job_id)`; hash title+company+description when a source lacks stable ids. Every normalizer also stores a guessed `company_domain` and an inferred ISO-3166 `country` (`_derive_country`) — Nigeria matched first and most thoroughly; an unrecognised location stores NULL, never a guess.
- **Schedule:** hourly for `priority >= 8` sources (`--min-priority 8`), full daily run for everything else. **Retries:** per-source try/except — one dead source never kills the run.

### Worker 2 — Company verification refresh (`workers/verify_employers.py`)
- **Inputs:** distinct `apply_url` domains in `ingested_jobs` whose `employer_trust_records` entry is missing or older than 7 days. Greenhouse/Lever/Ashby hostnames are deliberately skipped — verifying an ATS domain would mislabel it as the employer.
- **Output:** upserted `employer_trust_records` via `verify.verify_employer`, unchanged trust-scoring code.
- **Schedule:** daily, 3s sleep between domains (be a polite scanner).

### Worker 3 — Matching (`workers/match_users.py`)
- **Inputs:** every user with `career_twins.data.onboarding_complete = true`, cross-joined against `ingested_jobs` fetched in the last `--days-fresh` days that the user hasn't already been matched against (SQL anti-join on `matches`).
- **Output:** `matches` rows, best fit first; feeds the dashboard's "I found N new job matches" and `GET /matches`.
- **Schedule:** nightly. **Cost guard:** `core.match_jobs` batches jobs per Gemini call (default 50/call); `--max-jobs` caps jobs scored per user per run.

### Worker 4 — Notifications (`workers/notify_users.py`)
- **Inputs:** `matches` rows with `notified = 0`, joined to the user's Career Twin for their captured email (set on `POST /career-twin/complete`).
- **Output:** one digest email per user via the Brevo transactional API (`BREVO_API_KEY` + `BREVO_SENDER_EMAIL`); `notified`/`notified_at` set only after a confirmed send. Candidate digests also carry fresh interview invites and stale-application "how did it go?" nudges.
- **Second pass (employer side):** one digest per role poster summarizing new inbound applicants (`role_applications` where `notified = 0`), deduped by `role_applications.notified`; opt-out and missing-email are honored and counted separately (`employer_sent` / `employer_skipped_*` / `employer_send_failures`).
- **Schedule:** nightly, after Worker 3. **Rule:** max one digest per user per scheduled run — never per new match.

### Worker 5 — Backup (`workers/backup_db.py`)
- **Inputs:** the live SQLite file.
- **Output:** a `PRAGMA quick_check`-verified snapshot (via SQLite's online backup API, safe against concurrent writers) uploaded to Cloudflare R2 as `backups/emploi-YYYY-MM-DD.sqlite3`. Missing R2 config or a failed upload is a hard failure — nothing is ever reported as backed up that wasn't.
- **Schedule:** nightly, after ingest/verify/match.

## Scheduling: in-process, single source of truth

**Render Cron Jobs cannot mount a persistent disk at all** — not their own, and not one shared with another service ([Render docs](https://render.com/docs/disks): "Cron jobs can't provision or access a persistent disk"). Every worker needs the same SQLite file the `emploi-api` service uses, so scheduling runs **in-process on `emploi-api`** (the one service with the disk), not as separate cron jobs.

- `INTERNAL_SCHEDULER=true` on `emploi-api` starts `_start_internal_scheduler` (`api/main.py`), a daemon thread that runs every worker on the cadence in `_scheduler_jobs()` (ingest hourly + daily, verify, match, expire, notify, backup). This is the **sole** scheduler.
- `api/main.py` also exposes `POST /admin/run/{ingest,match,verify-employers,notify,expire-invites,backup}`, authed by `X-API-Key` only (no user in a scheduled run), for **manual/one-off** triggers. Heavy workers (ingest/match/verify) run in a background thread and return `202` immediately; notify/backup/expire are synchronous.
- **The separate `type: cron` curl-trigger services were removed (2026-07-27).** They duplicated the internal scheduler — every worker was scheduled twice at the same UTC minute and ran concurrently against one SQLite file on a single 0.5-CPU instance, causing write-lock + CPU contention that made the crons' own `curl` fail (exit 28 = the ingest 202 couldn't return within `--max-time` behind a lock-blocked threadpool; exit 22 = a worker raised `database is locked` → 500, or the overloaded instance returned 502/503). Never schedule the workers from two places at once; if external cron is ever wanted, disable `INTERNAL_SCHEDULER` first.
- **Optional integrations degrade, don't page:** an unconfigured Brevo sender (notify) or absent R2 (backup) is a clean skip (`ok:true`, `skipped`/`sender_configured:false`) → the trigger returns `200`, not a nightly 500. A *configured* integration that then fails still returns `ok:false` → 500 (real problem, stays loud).
- `test_api.py` covers the `/admin/run/*` endpoints fully offline by monkeypatching each imported worker module's `run()` — no real network, Gemini calls, or R2 upload in CI.

## Error handling policy (all services)

- User-facing failure → structured error with a human message (chat: `say()`; API: HTTPException detail; web: friendly state). Exceptions never reach a raw error screen.
- Gemini failures: 429 → formatted quota message (free tier 20 req/day + retry window); timeouts → retry once, then degrade with a message.
- Parsing model output: always through `parse_profile_json`/`parse_json_array` — they return `{}`/`[]` on garbage, never raise.

## Logging (event vocabulary)

Log these as structured events (stdout JSON now; `events` table later): `ResumeUploaded`, `ProfileExtracted`, `CareerTwinUpdated`, `TrustCheckRun`, `MatchesGenerated`, `ApplicationCreated`, `ApplicationStatusChanged`, `UserDeleted`, `GeminiCall` (with call count + model). Never log CV contents, profile fields, or API keys.

## Acceptance criteria

- Every worker runs standalone with `--dry-run` printing what it would write.
- A worker crash affects only its own run (idempotent upserts; dedup keys).
- Gemini call counts are logged per run.

## Edge cases

- Source API shape change → normalization guarded per-field with defaults; unknown fields dropped, run continues.
- Duplicate job across sources → allowed (dedup is per source); cross-source dedup is a future extension.
