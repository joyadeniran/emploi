# Emploi — Changelog

All notable changes to this project. Format loosely follows [Keep a Changelog](https://keepachangelog.com); dates are when the work shipped.

## [Unreleased]
Planned: fresh-listings agent (job APIs + monitored sources), WHOIS domain-age check, OCR for scanned CVs, curator partner pilot (Halo), BYOK option for users, per-user quotas (auth now makes this possible), durable DB storage for deploys (Render Disk / Cloud SQL — free-tier filesystem is ephemeral).

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
