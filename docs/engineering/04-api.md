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

## Endpoints

| Method & path | Body | Returns | Errors |
|---|---|---|---|
| `GET /health` | — | `{ok, version, ai, auth}` — `ai`: Gemini key present; `auth`: API key set | — |
| `GET /profile` | — | `{profile: {...}}` (empty object if none) | 401 |
| `PUT /profile` | `{profile: {...}}` | `{ok: true}` | 401 |
| `POST /resume/extract` | `{cv_text}` (≥50 chars) | `{profile}` — extracted via Gemini AND persisted | 422 short/garbage, 503 no key |
| `POST /verify` | `{company?, contact?, job_text?, role?}` (at least one of company/contact) | verify.py result: `{company, domain, score, level, evidence[], signals}` | 422, 401 |
| `GET /applications` | — | `{applications: [...]}` newest first, extra JSON flattened | 401 |
| `POST /applications` | `{company, role, status, extra?}` | `{id}` (201) | 422 bad status |
| `PATCH /applications/{id}` | `{status}` | `{ok}` | 404 not owner, 422 bad status |
| `POST /matches` | `{jobs: [...]}` | `{matches: [...]}` ranked by fit | 409 no profile, 422 no jobs, 503 no key |
| `DELETE /user` | — | `{ok}` — full NDPA/GDPR erasure | 401 |

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

- **AI degradation:** every Gemini-backed endpoint returns `503` with a message naming `GEMINI_API_KEY` when no key is configured. `/verify` still works fully (its only AI use — site-content consistency — degrades to "unknown").
- **Verification caching:** per-process per-domain (`_verify_cache`); network probes run once per domain per process. Preserve when touching `/verify` (test asserts one probe).
- **Injectable I/O:** `api.main.dns_fn / mx_fn / fetch_fn` and `app.state.model_factory` are the seams tests patch. Never call probes directly in endpoints.

## Acceptance criteria

- `python3 test_api.py` — all checks pass offline (33 at time of writing: auth, round-trips, degradation, caching, ownership, deletion).
- OpenAPI docs render at `/docs` and match this table.

## Edge cases

- Same-domain second verify → served from cache with fresh red-flag scan (red flags are per-posting, not per-domain).
- PATCH on another user's application → 404 (not 403 — don't leak existence).

## Future extensions

- `POST /applications/generate` (cover letter + CV via `core.generate_application`) — endpoint shape is ready; ship with quota guards (reviewer pass doubles calls; UI must disclose call counts).
- Rate limiting per user id (see 08-auth.md security).
- `/jobs` read endpoints once the ingestion worker lands (05-services.md).
