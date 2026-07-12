# 08 — Auth & Security

## Authentication (as built)

- **Users:** Google OAuth via NextAuth v5 (`web/auth.ts`). JWT session strategy; `session.user.id` = Google `sub`. Sign-up and sign-in are the same flow.
- **Route protection:** `web/app/(app)/layout.tsx` calls `auth()` and redirects to `/login`. (Next 16 deprecates middleware; this is the supported pattern here.) Verified: unauthenticated hits 307 → `/login`.
- **Dev login:** Credentials provider `dev-login`, enabled ONLY when `AUTH_DEV_LOGIN=true` AND `NODE_ENV !== "production"`. It must never appear in a production build.
- **Service-to-service:** web → API with `X-API-Key` (shared secret) + `X-User-Id` (asserted by web after session validation). The API refuses missing/wrong keys when `EMPLOI_API_KEY` is set, and logs a loud warning when unset.
- **Streamlit app:** independent Google OIDC (`st.login`) — unchanged.

## Authorization

- v1: single role (candidate). Every DB query is user-scoped; mutations verify ownership (404, not 403, for others' rows).
- Future roles (recruiter, admin): add a `role` claim at the web tier and a `roles` column server-side; never trust a role sent from the browser.

## Secrets

| Secret | Lives in | Never |
|---|---|---|
| `AUTH_SECRET`, `GOOGLE_CLIENT_ID/SECRET` | web env (Vercel) | in git, in client bundles |
| `EMPLOI_API_KEY` | web env + API env | in browser (only `lib/api.ts` server-only module uses it) |
| `GEMINI_API_KEY` | API env / Streamlit secrets | logged, echoed, committed |

`.env*` files are gitignored in both tiers; `.env.example` documents every variable.

## Security checklist (enforced now)

- **Input validation:** Pydantic schemas on every API body; status whitelist; cv_text length floor.
- **SQL injection:** parameterized queries only (`db.py` — the only SQL file).
- **Prompt injection:** untrusted text (CVs, postings) is parsed against strict output contracts; trust scores computed in code; chat profile updates accept only known keys (see 06-ai-layer.md).
- **XSS:** React escaping everywhere; no `dangerouslySetInnerHTML`.
- **Data rights:** `DELETE /user` = full erasure; privacy policy reflects actual storage behavior.
- **Headers between tiers:** API key comparison; user id required on every authed route.

## Security checklist (required before public launch — flagged, not yet built)

- **Rate limiting** on the API per user id (and on `/api/trust-check` per session) — network probes and Gemini calls are abusable.
- **File upload validation** when CV upload lands in web: extension + magic bytes + size cap; parse PDFs server-side only.
- **HTTPS everywhere** (Vercel/Render defaults); HSTS on the landing host.
- **Dependency audit** in CI (`npm audit`, `pip-audit`) with a triage policy.

## Logging & audit

Structured events per 05-services-and-workers.md. Log user **ids**, never CV/profile contents. Auth failures log the reason without the presented key.

## Acceptance criteria

- test_api.py auth block passes (401 matrix).
- Production build with `AUTH_DEV_LOGIN=true` still hides dev login (`NODE_ENV` guard).
- `grep -rn "EMPLOI_API_KEY" web/app web/components` → only server-side modules.

## Edge cases

- Google account with no name/picture → UI fallbacks (initials, "Account").
- Session expiry mid-action → API 401 → web surfaces sign-in redirect rather than a raw error.
