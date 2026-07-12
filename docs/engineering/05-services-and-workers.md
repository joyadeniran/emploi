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

## Background workers (planned — build in this order)

Each worker is a standalone script, runnable manually (`python3 workers/<name>.py`) and via Render Cron. Never wire workers into the web/API request cycle.

### Worker 1 — Job ingestion
- **Inputs:** Greenhouse public board API (`boards-api.greenhouse.io/v1/boards/{token}/jobs`, no key) and Lever (`api.lever.co/v0/postings/{company}`, no key) first; Jooble/Adzuna behind env keys.
- **Output:** rows in `ingested_jobs` (03-database.md), deduped on `(source, source_job_id)`; hash title+company+description when a source lacks stable ids.
- **Schedule:** daily. **Retries:** per-source try/except — one dead source must not kill the run; log and continue.

### Worker 2 — Company verification refresh
- **Inputs:** distinct domains in `ingested_jobs` + `employer_trust_records` older than 7 days.
- **Output:** upserted `employer_trust_records`. Uses `verify.verify_employer` unchanged.
- **Schedule:** daily, rate-limited (sleep between domains — be a polite scanner).

### Worker 3 — Matching
- **Inputs:** users with profiles × fresh `ingested_jobs` in their categories.
- **Output:** `matches` rows; feeds the dashboard's "I found N new job matches".
- **Schedule:** nightly. **Cost guard:** batch prompts (`core.match_jobs` takes a job list); cap jobs/user/night; log Gemini call counts.

### Worker 4 — Notifications
- **Inputs:** new `matches`, application status nudges.
- **Output:** email via Resend (template per event type). WhatsApp/push are future.
- **Schedule:** after Worker 3. **Rule:** max one digest email per user per day.

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
