# 04 — API

**Service:** `api/main.py` (FastAPI). **Run:** `python3 -m uvicorn api.main:app --port 8000`.
**Invariant:** no business logic in endpoints — validate, dispatch to `core`/`verify`/`db`, shape the response.

## Auth model (service-to-service)

The API is **not** browser-facing. The Next.js server calls it with:

| Header | Meaning |
|---|---|
| `X-API-Key` | Shared secret = `EMPLOI_API_KEY` env on both tiers. Unset ⇒ open dev mode (startup log warns; never deploy like this). |
| `X-User-Id` | The authenticated user's stable id (Google `sub`), asserted by the web tier after NextAuth session validation. |

Deploy the API private to the web tier (Render private service / network rules). If it must be public, add per-user JWT verification (see 08-auth.md future work).

## Rate limiting (in-process, per user per path)

`rate_limit` dependency; counters reset on restart (single-process deployment, deliberate). Current limits: default 60/min; `/verify` 10/min; `/career-twin/extract` and `/career-twin/upload` 5 per 5 min; `/matches` 30/min; `/applications/generate` 10/hour. Exceeding returns `429`.

## Endpoints

| Method & path | Body | Returns | Errors |
|---|---|---|---|
| `GET /health` | — | `{ok, version, ai, auth}` — `ai`: Gemini key present; `auth`: API key set | — |
| `GET /career-twin` | — | `{career_twin: {...}}` (empty object if none) | 401 |
| `PATCH /career-twin` | `{data: {...}}` | `{ok}` — partial merge into stored twin | 413 >64KB |
| `POST /career-twin/extract` | `{cv_text}` (≥50 chars) | `{career_twin}` — Gemini extraction, merged + persisted | 422, 502, 503 no key, 429 |
| `POST /career-twin/upload` | multipart PDF | `{career_twin}` — PDF→text→extraction | 413 >15MB, 422 image-only, 502/503, 429 |
| `POST /career-twin/complete` | — | `{ok}` — sets `onboarding_complete` (workers gate on it) | 401 |
| `GET /profile` | — | legacy alias for `GET /career-twin` | 401 |
| `POST /resume/extract` | `{cv_text}` | legacy alias for extract | as above |
| `POST /verify` | `{company?, contact?, job_text?, role?}` (≥1 of company/contact) | verify.py result: `{company, domain, score, level, evidence[], signals}` | 422, 401, 429 |
| `GET /applications` | — | `{applications: [...]}` newest first, extra JSON flattened | 401 |
| `POST /applications` | `{company, role, status, extra?}` | `{id}` (201) | 422 bad status |
| `POST /applications/generate` | `{job: {description|job_text, company?}, include_review?}` | `{job_id}` (202) — async; poll the job status endpoint. 402 when monthly quota exhausted. | 409 no twin, 402 quota, 422 no description, 429 |
| `GET /applications/generate/{job_id}` | — | `{status: pending|done|error, result?: {text, fit_score, ...}, error?: str}` | 404 unknown job |
| `PATCH /applications/{id}` | `{status}` | `{ok}` | 404 not owner, 422 bad status |
| `POST /matches` | `{jobs: [...]}` | `{matches: [...]}` ranked by fit (ad-hoc ranking) | 409 no twin, 422 no jobs, 503, 429 |
| `GET /matches` | `?limit=` | `{matches: [...]}` pre-computed by Worker 3, best fit first, joined with job fields incl. description | 401 |
| `GET /jobs` | `?remote_only&category&limit&offset` | `{jobs, total, limit, offset}` (limit ≤ 200) | 422 bad limit |
| `GET /jobs/{id}` | — | single ingested job | 404 |
| `GET /saved-jobs` | — | `{saved_jobs: [...]}` user's bookmarked jobs joined with ingested_jobs fields | 401 |
| `POST /saved-jobs` | `{job_id}` | `{ok}` (201) — idempotent via UNIQUE constraint | 422 |
| `DELETE /saved-jobs/{job_id}` | — | `{ok}` | 404 |
| `POST /chat` | `{message, history?}` | `{reply, profile_updates?}` — chat_turn with emploi_context injected; profile_updates merged into career twin on non-null | 409 no twin, 503 |
| `POST /chat/attach` | multipart: file + history | `{reply, career_twin?}` — classifies as CV or job listings; merges if CV, scores if jobs | 422, 503 |
| `GET /billing/status` | — | `{tier, status, current_period_end, used_this_month, limit, prices_ngn}` | 401 |
| `POST /billing/checkout` | `{tier: pro|max}` | `{authorization_url, reference}` — Paystack hosted checkout | 400 already on tier, 422 |
| `POST /billing/verify` | `{reference}` | `{tier, status}` — verify a Paystack transaction by reference and activate | 400 failed |
| `POST /billing/cancel` | — | `{ok}` — disables Paystack subscription; reverts to free immediately | 400 no active sub |
| `POST /billing/webhook` | raw body + `X-Paystack-Signature` | `{ok}` | 400 bad sig, 422 unknown event |
| `DELETE /user` | — | `{ok}` — full NDPA/GDPR erasure across all user-keyed tables | 401 |
| `GET /admin/job-sources` | — | source registry (auto-seeds from JSON on first call) | 401 |
| `POST /admin/job-sources` | `{company, ats, token, priority?, ...}` | `{id}` (201) | 422 |
| `PATCH /admin/job-sources/{id}` | partial fields | `{ok}` | 404 |
| `PATCH /admin/job-sources/{id}/toggle` | — | `{ok, active}` | 404 |
| `POST /admin/job-sources/seed` | — | `{ok, seeded}` — no-op if table non-empty | 401 |
| `POST /admin/run/ingest` | `?min_priority=` | Worker 1 result dict | 401, 500 on worker failure |
| `POST /admin/run/match` | — | Worker 3 result dict | 401, 500 |
| `POST /admin/run/verify-employers` | — | Worker 2 result dict | 401, 500 |
| `POST /admin/run/notify` | — | Worker 4 result dict | 401, 500 |
| `POST /admin/run/backup` | — | Worker 5 result dict | 401, 500 |

### Example — trust check

```
POST /verify
X-API-Key: ...  X-User-Id: google-sub-123
{"company": "Acme Corp", "contact": "jobs@acmecorp.com",
 "job_text": "Software engineer role..."}

200 → {"company": "Acme Corp", "domain": "acmecorp.com", "score": 85,
       "level": "Trusted", "evidence": ["✅ contact uses a corporate email domain", ...],
       "signals": {...}}
```

## Behavior contracts

- **AI degradation:** every Gemini-backed endpoint returns `503` with a message naming `GEMINI_API_KEY` when no key is configured; a provider failure mid-call becomes a clean `502` (`run_extraction`), never a raw 500. `/verify` still works fully (its only AI use — site-content consistency — degrades to "unknown").
- **Cost disclosure:** `/applications/generate` with `include_review` costs 3 Gemini calls (2 without). The web UI must disclose this before invoking — the generation dialog does.
- **Verification caching:** per-process per-domain (`_verify_cache`); network probes run once per domain per process. Preserve when touching `/verify` (test asserts one probe).
- **Injectable I/O:** `api.main.dns_fn / mx_fn / fetch_fn` and `app.state.model_factory` are the seams tests patch. Never call probes directly in endpoints.
- **SQLite contention:** connections use a 30s busy timeout to absorb ordinary write contention.
- **Async generation:** `POST /applications/generate` returns `202 {job_id}` immediately and runs both Gemini calls in a background thread. The client polls `GET /applications/generate/{job_id}` until `status` is `done` or `error`. Per-call Gemini timeout is 25 s (`GENERATE_CALL_TIMEOUT_S`). On success the worker calls `db.log_generation()` before marking done.
- **Quota enforcement:** before any AI spend, the generation endpoint checks `db.count_generations_this_month()` against `core.monthly_generation_limit(tier)`. If `used >= limit`, returns `402` immediately. See [10 — Billing](10-billing.md) for tier limits.
- **Worker triggers:** `/admin/run/*` default to `background=true` (202 + background thread) to beat Render's ~100 s proxy timeout; pass `?background=false` for sync mode (used in tests). Require only `X-API-Key` (no user in a scheduled run). A worker failure in sync mode surfaces as `500`, never a false `200`.

## Acceptance criteria

- `python3 test_api.py` — all checks pass offline (auth, round-trips, degradation, caching, ownership, deletion, rate limits, generation paths).
- OpenAPI docs render at `/docs` and match this table.

## Edge cases

- Same-domain second verify → served from cache with fresh red-flag scan (red flags are per-posting, not per-domain).
- PATCH on another user's application → 404 (not 403 — don't leak existence).

## Future extensions

- Per-user JWT verification if the API is ever exposed publicly.
- Shared rate-limit store (Redis) when multi-instance; the in-process guard is a single-process design.
