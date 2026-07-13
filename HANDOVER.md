# Emploi — Full Production Handover

**Written:** 2026-07-13  
**Repo:** https://github.com/joyadeniran/emploi  
**Live API:** emploi-api.onrender.com  
**Live App:** app.emploihq.com  
**Company:** Crost Limited RC 9526947  
**Domain:** emploihq.com / @emploihq  

This document is written for a developer who has never seen this codebase. It is honest about what is built, what is half-built, what is missing entirely, and what must be done to take Emploi from its current state to a platform that can be trusted with real users and real money. Read `CLAUDE.md` first — it is the canonical rulebook and overrides this document on specifics. Then read `docs/engineering/01-overview.md` through `09-deployment.md`. Then come back here for the gaps.

---

## What Is Actually Built (Honest State Assessment)

### Fully Built and Tested

| Component | Location | Status |
|---|---|---|
| Core AI logic | `core.py` | Complete. CV extraction, job matching, application generation, interview prep, chat turns. All prompt-injected via `skills/*.md`. |
| Trust engine | `verify.py` | Complete. Deterministic scoring; bot-block semantics correct; injectable for tests. |
| DB layer | `db.py` | Complete. All tables built; upsert patterns; GDPR deletion. |
| FastAPI backend | `api/main.py` | Complete. All endpoints including job sourcing and admin. |
| Job ingestion | `workers/ingest_jobs.py` | Complete. Greenhouse + Lever; DB-seeded source list; rate-limited; dry-run. |
| Matching worker | `workers/match_users.py` | Complete. Anti-join SQL; batch Gemini calls; dry-run. |
| Job source registry | `db.py` + `data/job_sources.json` | Complete. 130 companies; admin CRUD endpoints. |
| Next.js auth shell | `web/` | Auth and routing complete. Google OAuth via NextAuth v5. |
| Onboarding wizard | `web/app/create-career-twin/` | Complete. 8-step PDF → Career Twin flow. |
| Trust Check UI | `web/app/(app)/trust-check/` | Live. Calls real API. |
| Applications tracker UI | `web/app/(app)/applications/` | Live. CRUD to real API. |
| Test suites | `test_e2e.py`, `test_verify.py`, `test_db.py`, `test_api.py`, `test_ingest.py` | All green. 37+ checks in test_ingest covering both workers. |
| Landing | `landing/` | Static HTML. Employs the brand. CTAs link to app. |
| Deployment | Render (paid) + Vercel | API live with disk-mounted SQLite. |

### Built But Not Wired (The Biggest Gap)

The dashboard and matches page **render demo data from `web/lib/data.ts`**. The Career Twin is extracted and stored. The matching worker is built and tested. But the web tier never fetches real matches from the API. When a real user signs in:

- Their Career Twin page shows `PagePlaceholder` — no profile display.
- Their dashboard shows hardcoded fictional OPay/GitLab job cards.
- Their matches page shows the same hardcoded cards.
- The "Apply" button creates a real application row (that part works) but the job it references is from demo data.

This is the single most urgent gap. The infrastructure is all there — it is wiring work, not design work.

### Placeholder Pages (No Real Content)

| Route | What exists | What's needed |
|---|---|---|
| `/career-twin` | `PagePlaceholder` component | Full profile view + edit form |
| `/messages` | `PagePlaceholder` | Career Twin chat (core.py has `chat_turn`) |
| `/saved` | `PagePlaceholder` | Saved jobs from matches |
| `/interview-prep` | `PagePlaceholder` | `core.py` has `prepare_interview` — needs UI |
| `/insights` | `PagePlaceholder` | Analytics over applications, future |
| `/recruiter` | `PagePlaceholder` | v2 feature, explicitly not v1 |

---

## Priority Order for Remaining Work

Below is the full task list in the order a single developer should attack them. Each section names the gap, the file(s) to touch, what the output looks like, and the test requirement.

---

## 1. Wire Real Data into the Dashboard (CRITICAL — do this first)

**Gap:** `web/lib/data.ts` exports hardcoded arrays. Server components on the dashboard and matches pages import from this file instead of fetching the API. The `DEMO_MODE` flag in `web/lib/api.ts` gates this behaviour.

**What to build:**

### 1a. Real matches on the matches page

File: `web/app/(app)/matches/page.tsx`

Currently imports `{ matches }` from `@/lib/data`. Replace with a server-side fetch:

```typescript
// Replace demo import with real fetch
import { apiFetch, ApiUnavailableError, DEMO_MODE } from "@/lib/api";
import { matches as demoMatches } from "@/lib/data"; // keep as fallback

const matchData = DEMO_MODE ? demoMatches : await (async () => {
  try {
    const { matches } = await apiFetch<{ matches: any[] }>("/matches?limit=50");
    return matches; // [{job_id, title, company_name, fit_score, reason, is_remote, apply_url, ...}]
  } catch (e) {
    if (e instanceof ApiUnavailableError) return demoMatches;
    return [];
  }
})();
```

The API `/matches` endpoint (already built in `api/main.py`) returns rows joined with `ingested_jobs`. The field names differ from the demo type — `company_name` not `company`, `fit_score` not `fit`, `apply_url` not a URL field on the demo object. You need to either normalise at the fetch layer or update the component to accept both shapes. The cleanest approach: add a `toMatchCard(apiRow)` transform function in `web/lib/api.ts` that maps API fields to the `JobMatch` type from `data.ts`.

### 1b. Real dashboard data

File: `web/app/(app)/dashboard/page.tsx`

The dashboard already fetches the Career Twin for the onboarding gate — extend it to also fetch `/matches?limit=5` and `/applications?limit=3`, then pass to the sub-sections. The `hasMatches` constant is currently hardcoded `true`. Replace it:

```typescript
const matchesRes = await apiFetch<{ matches: any[], total: number }>("/matches?limit=5");
const hasMatches = matchesRes.matches.length > 0;
```

When `hasMatches` is `false`, the empty state is already built (the spinner cards saying "Scanning new opportunities..."). This is the moment those render for real.

The `twinSummary` object on the dashboard (newMatches count, highMatches, allVerified) is also hardcoded. Replace with derived values from the fetched matches.

### 1c. Career Twin profile display

File: `web/app/(app)/career-twin/page.tsx`

Currently a `PagePlaceholder`. Replace with a server component that fetches `GET /career-twin` and renders the structured twin. The twin object has fields like `name`, `headline`, `bio`, `skills[]`, `experience[]`, `education[]`, `goals`, `onboarding_complete`. Design a read-only profile card for each section. The editing flow is a stretch goal for v1 but the view is not.

**Test requirement:** No offline test needed for UI pages. Manual test: sign in as a real user, upload a CV, complete the wizard, then verify the dashboard and matches page show your real data and not the OPay/GitLab placeholder cards.

---

## 2. Wire the Apply Button to Real Ingested Jobs (IMPORTANT)

**Gap:** `web/components/ApplyButton.tsx` creates an application row via `POST /api/applications`. But the `job` object it receives comes from the demo data array — it has no real `job_id` from `ingested_jobs`, no real `apply_url`, no real company data from the DB.

Once real matches are wired (step 1), the ApplyButton will receive real data. But you also need to decide: should clicking "Apply" from the Emploi UI:

**Option A (v1 recommended):** Record it in the tracker (already works) and open `apply_url` in a new tab. The user applies on the employer's site manually. Emploi tracks their application status.

**Option B (v2):** Use `core.generate_application` to produce a tailored cover letter + CV first, then show it to the user before they go to the ATS. This doubles Gemini calls and needs a generation endpoint in the API — `POST /applications/generate` is stubbed in `api/main.py` comments but not built.

Option A is all you need for v1 launch. The ApplyButton should:
1. POST `{ company, role, status: "applied", extra: { job_id, apply_url, fit_score } }` to `/api/applications`
2. Open `apply_url` in a new tab
3. Show an optimistic "Applied" state that reverts on network failure

File: `web/components/ApplyButton.tsx` and `web/app/api/applications/route.ts`

---

## 3. Scheduler for the Workers (REQUIRED for Autonomous Matching)

**Gap:** `workers/ingest_jobs.py` and `workers/match_users.py` are both complete but **nothing runs them automatically**. The matching worker is the core product promise — "Career Twins that work while you sleep" — but it never runs unless triggered manually.

**What to build:**

Add two cron services to `render.yaml`:

```yaml
  - type: cron
    name: emploi-ingest
    runtime: python
    plan: starter  # free tier doesn't support cron; starter is $7/mo
    schedule: "0 * * * *"           # every hour (high-priority sources)
    buildCommand: pip install -r requirements.txt
    startCommand: python3 workers/ingest_jobs.py --db /var/data/emploi.sqlite3 --min-priority 8
    envVars:
      - key: EMPLOI_DB_PATH
        value: /var/data/emploi.sqlite3
      - key: PYTHON_VERSION
        value: 3.12.0
    disk:
      name: emploi-data
      mountPath: /var/data
      sizeGB: 1

  - type: cron
    name: emploi-match
    runtime: python
    plan: starter
    schedule: "0 2 * * *"           # 2am nightly
    buildCommand: pip install -r requirements.txt
    startCommand: python3 workers/match_users.py --db /var/data/emploi.sqlite3
    envVars:
      - key: EMPLOI_DB_PATH
        value: /var/data/emploi.sqlite3
      - key: GEMINI_API_KEY
        sync: false
      - key: PYTHON_VERSION
        value: 3.12.0
    disk:
      name: emploi-data
      mountPath: /var/data
      sizeGB: 1
```

**Critical:** All three services (`emploi-api`, `emploi-ingest`, `emploi-match`) must mount the **same named disk** (`emploi-data`) at `/var/data`. Render shares a named disk between services in the same Blueprint. If they don't share the disk, the workers write to a different SQLite file than the API reads from, and nothing appears on the dashboard. This is a real gotcha — verify in the Render dashboard that disk names match exactly.

Also add a daily full-priority ingest run:

```yaml
  - type: cron
    name: emploi-ingest-daily
    schedule: "0 1 * * *"           # 1am daily
    startCommand: python3 workers/ingest_jobs.py --db /var/data/emploi.sqlite3
    # runs ALL priority levels, including priority 1 (daily) sources
```

**Test requirement:** After adding to render.yaml, do a manual trigger via Render's "Run Now" button. Verify `events` table in the SQLite DB gets `JobIngestionRun` and `MatchingWorkerRun` rows. Verify `ingested_jobs` and `matches` tables are populated.

---

## 4. Worker 2 — Employer Verification Refresh (MISSING ENTIRELY)

**Gap:** The `employer_trust_records` table exists and `verify.verify_employer()` writes to it via `db.upsert_trust_record()`. But there is **no worker that refreshes stale records** or proactively verifies employers from `ingested_jobs`.

Currently: trust checks only happen when a user explicitly runs the Trust Check UI. So every job in `ingested_jobs` has no pre-computed trust score. The matches page shows "Employer verified" for demo data only.

**What to build:** `workers/verify_employers.py`

```python
"""Worker 2 — Nightly employer verification refresh.

For every distinct domain in ingested_jobs, checks if a trust record exists
and is fresh (< 7 days old). Stale or missing records are re-verified.
Rate-limited: one domain per 3 seconds to avoid hammering DNS + HTTP.

Run: python3 workers/verify_employers.py [--dry-run] [--db PATH] [--max-domains N]
Schedule: nightly, before match worker.
"""

def run(db_path, dry_run=False, max_domains=200, max_age_days=7,
        dns_fn=None, mx_fn=None, fetch_fn=None, model=None):
    conn = db.connect(db_path)
    
    # Find domains needing refresh
    cutoff = f"-{max_age_days} days"
    rows = conn.execute("""
        SELECT DISTINCT 
            LOWER(REPLACE(REPLACE(apply_url, 'https://', ''), 'http://', '')) as domain,
            company_name
        FROM ingested_jobs
        WHERE apply_url IS NOT NULL AND apply_url != ''
        LIMIT ?
    """, (max_domains,)).fetchall()
    
    # Filter to stale/missing
    to_verify = []
    for row in rows:
        domain = row["domain"].split("/")[0]  # strip paths
        existing = db.get_trust_record(conn, domain)
        if existing is None or existing["last_checked_at"] < cutoff:
            to_verify.append({"domain": domain, "company": row["company_name"]})
    
    for source in to_verify:
        if dry_run:
            print(f"  [dry-run] would verify: {source['domain']}")
            continue
        result = verify.verify_employer(
            source["company"], "", "", "",
            model=model, dns_fn=dns_fn, mx_fn=mx_fn,
            fetch_fn=fetch_fn, cache={})
        db.upsert_trust_record(conn, source["domain"], source["company"], result)
        time.sleep(3)  # rate limit — be a polite scanner
    
    db.log_event(conn, "VerificationWorkerRun", {...})
```

The domain extraction from `apply_url` is imprecise — greenhouse URLs are `boards.greenhouse.io/company/jobs/123` which belongs to greenhouse, not the employer. You need to either:

- Store `company_domain` as a separate field in `ingested_jobs` during ingestion (the ingestion worker knows the company name; you can attempt a heuristic: `{token}.com`, `{company-slug}.com`), or
- Accept that auto-verification will have wrong domains for ATS-hosted jobs and only pre-verify companies where the `apply_url` is on the company's own domain.

The ATS-domain problem is a real constraint. Document it honestly. The Trust Check UI (which the user can run manually on any company name) remains the reliable path. The worker's value is batching the ones where domain extraction is reliable.

**Test file:** `test_verify_worker.py` — inject fake DNS/HTTP, seed 3 `ingested_jobs` rows with known domains, run worker, assert `employer_trust_records` populated. Use the `ExplodingModel` pattern from `test_verify.py` to assert the model is NOT called (only `check_site_content` uses the model, and you can control that separately).

---

## 5. Worker 4 — Notifications (MISSING ENTIRELY)

**Gap:** Users have no way to know when new matches arrive unless they log in. This is the feature that makes the platform feel alive between sessions.

**What to build:** `workers/notify_users.py`

**Dependencies:** Resend account at resend.com (`pip install resend`). API key in env as `RESEND_API_KEY`. Email domain must be `emploihq.com` with DNS records verified in Resend.

**Logic:**

```python
def run(db_path, dry_run=False, resend_api_key=None):
    conn = db.connect(db_path)
    
    # Find users with matches created in the last 24h not yet notified
    # Need a `notified_at` column on matches OR a separate `notifications` table
    # Simplest: add `notified INTEGER DEFAULT 0` column to matches table
    
    new_matches = conn.execute("""
        SELECT m.user_id, COUNT(*) as match_count,
               MAX(m.fit_score) as top_score,
               ct.data as twin_data
        FROM matches m
        JOIN career_twins ct ON ct.user_id = m.user_id
        WHERE m.notified = 0
          AND m.created_at >= datetime('now', '-1 days')
        GROUP BY m.user_id
    """).fetchall()
    
    for row in new_matches:
        twin = json.loads(row["twin_data"])
        email = twin.get("email")   # ← THIS IS THE PROBLEM (see below)
        if not email:
            continue
        
        if not dry_run:
            send_digest_email(email, twin.get("name"), row["match_count"], row["top_score"])
            conn.execute("UPDATE matches SET notified=1 WHERE user_id=? AND notified=0", (row["user_id"],))
            conn.commit()
```

**The email problem:** The Career Twin JSON blob does not currently store the user's email address. The `user_id` is the Google `sub` claim (a stable opaque string like `115702...`), not an email. To send email you need to either:

1. Store the email in the Career Twin blob during onboarding (simplest — add `email` field when the wizard completes), or
2. Add a separate `users` table with `user_id TEXT PRIMARY KEY, email TEXT, name TEXT, created_at TEXT`.

Option 2 is the right design but requires a migration and updating the web tier to `POST /user` on first sign-in. Option 1 is faster but stores PII in the blob (document in your privacy policy).

**Schema change needed** for notifications tracking:

```sql
ALTER TABLE matches ADD COLUMN notified INTEGER NOT NULL DEFAULT 0;
ALTER TABLE matches ADD COLUMN notified_at TEXT;
```

Add to `_SCHEMA` in `db.py` as separate `CREATE INDEX IF NOT EXISTS` + the columns above via a migration helper function. Do NOT add `ALTER TABLE` inside `_SCHEMA` (it runs on every connect and will error on the second run). Instead add `db._migrate(conn)` called from `connect()` that does `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` using a try/except.

**Email template:** Plain text is fine for v1. Resend supports React Email for rich templates — that's v1.x. For now:

```
Subject: Your Career Twin found {N} new jobs for you

Hi {name},

Your Career Twin has been working while you were away. 

Here's what's new:
- {N} new job matches, best fit: {top_score}/100
- {top_job_title} at {top_company}

Log in to see them: https://app.emploihq.com/matches

— Your Career Twin
```

**Test:** Offline. Inject fake `send_fn`. Seed users + matches. Assert send called once per user with unnotified matches. Assert `notified=1` after run. Assert second run sends nothing.

---

## 6. Application Generation Endpoint (FEATURE GAP)

**Gap:** `core.py` has `generate_application(model, profile, job, ...)` fully built with the fit-score contract, reviewer pass, PDF/DOCX export. But **the API has no endpoint that calls it**, and the web tier has no UI for it.

The Streamlit `app.py` uses it — type `/apply Stripe` and it generates a full cover letter. But the Next.js dashboard cannot access this.

**What to build:**

In `api/main.py`:

```python
class GenerateIn(BaseModel):
    job: dict                    # the job dict to apply to
    include_review: bool = True  # reviewer pass doubles calls

@app.post("/applications/generate")
def generate_application_endpoint(body: GenerateIn, user_id: str = Depends(auth)):
    model = require_model()
    profile = db.load_career_twin(get_conn(), user_id)
    if not profile:
        raise HTTPException(409, "complete Career Twin setup first")
    result = run_extraction(
        core.generate_application, model, profile, body.job,
        reviewer=body.include_review)
    # result = {"cover_letter": "...", "cv": "...", "fit_score": 87, "evaluation": "..."}
    return {"generated": result}
```

In the web tier, the flow is: user clicks "Apply" on a match card → modal opens showing a loading state → `POST /api/applications/generate` → shows the cover letter → user copies/downloads → logs the application. The PDF download needs a separate endpoint or you generate it server-side and return base64.

**Cost disclosure requirement (CLAUDE.md invariant):** Any UI that calls the generation endpoint must show the user that it will use 2 Gemini calls (3 with reviewer). Add this as a note on the "Generate Application" modal. This is a hard rule from `CLAUDE.md`.

**Test:** Add to `test_api.py`. Use `FakeModel` that returns a response with `Fit Score: 85/100` at the end. Assert the response contains `fit_score`, `cover_letter`. Assert 503 when no model configured. Assert 409 when no Career Twin.

---

## 7. Settings Page and Data Deletion (LEGAL REQUIREMENT)

**Gap:** `DELETE /user` exists in the API and wipes all rows. But **there is no UI for it** in the web tier. This is a legal requirement under NDPA (Nigerian Data Protection Act) and GDPR if you have EU users.

**What to build:** `web/app/(app)/settings/page.tsx`

Sections needed:
- **Account:** name, email, Google account connected (read-only)
- **Career Twin:** last updated, option to re-upload CV
- **Notifications:** toggle email digests (needs the `users` table mentioned above)
- **Danger zone:** "Delete all my data" — red button, confirmation modal ("This permanently deletes your Career Twin, all applications, and all matches. This cannot be undone."), calls `DELETE /api/user`, then signs out and redirects to login

Also add Settings link to the sidebar (`web/components/Sidebar.tsx`).

The `DELETE /api/user` route handler already exists at `web/app/api/user/route.ts` (check — if not, create it as a proxy to `DELETE /user` on the FastAPI backend).

**Test:** Manual. Sign in, create an application, go to settings, delete account, verify redirect to login, try to sign in again and verify you get an empty profile.

---

## 8. Rate Limiting (SECURITY — Required Before Public Launch)

**Gap:** `docs/engineering/08-auth-and-security.md` explicitly flags this as required before public launch. Currently any API key holder can hit every endpoint without limit. Gemini calls and trust-check DNS/HTTP probes are abusable at scale.

**What to build:** Add per-user rate limiting to `api/main.py` using a simple in-process counter (acceptable for a single-process Render deployment):

```python
from collections import defaultdict
from time import time

_rate_counters: dict = defaultdict(list)

RATE_LIMITS = {
    "default": (60, 60),          # 60 requests per 60 seconds
    "/verify": (10, 60),          # 10 trust checks per minute (DNS + HTTP probes)
    "/career-twin/extract": (5, 300),  # 5 CV extractions per 5 minutes
    "/applications/generate": (10, 3600),  # 10 generations per hour
    "/matches": (30, 60),
}

def check_rate(user_id: str, path: str):
    limit, window = RATE_LIMITS.get(path, RATE_LIMITS["default"])
    now = time()
    key = f"{user_id}:{path}"
    calls = [t for t in _rate_counters[key] if now - t < window]
    if len(calls) >= limit:
        raise HTTPException(status_code=429, detail=f"Rate limit: {limit} requests per {window}s")
    calls.append(now)
    _rate_counters[key] = calls
```

Wire as a dependency or call at the start of each endpoint. Note: this resets on every Render deploy (process restart). For persistent rate limiting you need Redis — skip that for now and document the limitation.

**Test:** Add to `test_api.py`. Make N+1 requests with the same user id, assert the N+1th returns 429.

---

## 9. Privacy Policy and Terms of Service (LEGAL — Required Before Inviting Real Users)

**Gap:** `docs/engineering/09-deployment.md` has `[ ] Privacy/Terms pages reachable from app footer as well as landing` as an incomplete launch checklist item. There is no privacy policy page.

**What is needed:**

Emploi stores and processes:
- Google account data (name, email, profile picture)
- Full CV text (personal employment history, education, contact details)
- Career profile derived from the CV
- Job application records
- Match results with fit score and reasoning

Under NDPA (Nigeria), users have rights to access, correct, and delete their data. Under GDPR (EU, if applicable), the same plus explicit consent, data minimisation, and the right not to be subject to automated decisions.

**Minimum required:**

1. `/privacy` page at `app.emploihq.com/privacy` explaining what is stored, for how long, and how to delete it
2. `/terms` page covering acceptable use, service availability, limitations of the AI
3. Links in the footer of every page and the login page
4. The "Delete all my data" button described in §7 is the data deletion mechanism — reference it in the privacy policy

**Who writes it:** A lawyer or a privacy policy generator (Termly, iubenda) for NDPA/GDPR. A developer should not write this from scratch. Budget $100–300 for a proper policy or use a template service.

**Implementation:** Add these as static Next.js pages (no auth required):
- `web/app/privacy/page.tsx`
- `web/app/terms/page.tsx`

They can be simple markdown-rendered pages. Use `@tailwindcss/typography` (already likely in the stack, check `package.json`) to style the prose.

---

## 10. CV Upload in the Web Dashboard (FEATURE GAP)

**Gap:** The Career Twin wizard (`/create-career-twin`) handles first-time CV upload. But once a user has completed onboarding, there is no way to re-upload a CV to update their Career Twin from the dashboard. The Career Twin page is a `PagePlaceholder`.

**What to build:**

In `web/app/(app)/career-twin/page.tsx`:
- Show the current Career Twin data (name, headline, skills, experience, education)
- A "Update from CV" button that opens a file upload modal
- The modal calls `POST /api/career-twin/upload` (the endpoint exists in the API)
- After upload, the page revalidates and shows the updated data

The `POST /career-twin/upload` endpoint in `api/main.py` already handles this — it extracts the CV, merges with the existing twin, and saves. The web tier just needs a route handler and a UI.

Route handler `web/app/api/career-twin/upload/route.ts`:

```typescript
// This needs to handle multipart/form-data, not JSON
// The existing wizard already has this pattern — copy from create-career-twin/
```

---

## 11. Google OAuth Consent Screen (DEPLOYMENT BLOCKER)

**Gap:** `docs/engineering/09-deployment.md` says `Google OAuth client created... still in Testing mode — whitelist test users, then publish the consent screen`. Publishing the OAuth consent screen requires:

1. A domain verification record in Google Search Console for `emploihq.com`
2. A privacy policy URL (see §9 — this blocks OAuth publishing)
3. The OAuth consent screen form filled with: App name "Emploi", support email, developer contact email, homepage URL, privacy policy URL, terms of service URL
4. A review submission to Google (takes 1–5 business days for unverified apps; verified apps take longer)

Until the consent screen is published, only whitelisted Google accounts can sign in. This is the hard blocker for any public launch.

**Steps:**
1. Complete §9 (privacy policy) — required for the consent screen form
2. Go to Google Cloud Console → APIs & Services → OAuth consent screen
3. Fill all required fields
4. Verify domain ownership via Search Console
5. Submit for verification (choose "External" user type)
6. While waiting: add every test user's Google email to the whitelist manually

---

## 12. CI Pipeline (ENGINEERING HYGIENE)

**Gap:** `docs/engineering/09-deployment.md` mentions `.github/workflows/test.yml` but this file either does not exist or is not complete. Without CI, every push to main is unverified until someone runs the tests manually.

**What to build:** `.github/workflows/test.yml`

```yaml
name: test

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  python-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python3 -m pip install -r requirements.txt
      - run: python3 test_e2e.py
      - run: python3 test_verify.py
      - run: python3 test_db.py
      - run: python3 test_api.py
      - run: python3 test_ingest.py

  web-build:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: web
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
          cache-dependency-path: web/package-lock.json
      - run: npm ci
      - run: npm run lint
      - run: npm run build
        env:
          # Stub vars — build must succeed without real secrets
          AUTH_SECRET: "ci-stub-32-chars-exactly-padding"
          EMPLOI_API_URL: "http://localhost:8000"
          EMPLOI_API_KEY: "ci-stub"
          NEXTAUTH_URL: "http://localhost:3000"
```

**Test requirement:** Push a branch with a deliberate failing test and confirm the PR is blocked.

---

## 13. Persistent DB Backup Strategy (DATA SAFETY)

**Gap:** The production database is a single SQLite file on a Render Disk. A disk corruption or accidental deletion is unrecoverable without a backup. The `docs/engineering/09-deployment.md` mentions "copy the SQLite file on deploy" but this is not implemented anywhere.

**Options (choose one):**

**Option A (fast, free):** Litestream — streams WAL replication to S3/R2 in real-time. Add a `litestream.yml` config and run `litestream replicate` in the background alongside uvicorn. Cloudflare R2 is free for the first 10 GB. Cost: 0. Complexity: medium (Procfile/start script change).

**Option B (simple, cheap):** Add a daily cron worker that copies the SQLite file to Cloudflare R2 using `boto3`:

```python
# workers/backup_db.py
import boto3, os, datetime
s3 = boto3.client("s3", endpoint_url=os.getenv("R2_ENDPOINT"),
                  aws_access_key_id=os.getenv("R2_ACCESS_KEY"),
                  aws_secret_access_key=os.getenv("R2_SECRET_KEY"))
key = f"backups/emploi-{datetime.date.today()}.sqlite3"
s3.upload_file(os.getenv("EMPLOI_DB_PATH"), os.getenv("R2_BUCKET"), key)
```

**Option C (no new infra):** Render Disk snapshots are available in the dashboard and taken automatically on paid plans. Verify this is enabled and test restore before real users arrive.

Until a backup strategy is in place, a disk incident = complete data loss. This matters for users who have completed the Career Twin wizard and have application history.

---

## 14. Streamlit Admin Console (INTERNAL TOOL — USEFUL BUT DEFERRED)

**Current state:** `app.py` is the legacy Streamlit chat app that predates the Next.js dashboard. It is being repurposed as an internal admin console but has not been started on this path.

**What it should become:**

- **Trust review queue:** list of pending/low-trust employers from `employer_trust_records`; admin can override a score or add to blacklist/whitelist
- **Ingestion monitor:** last run time, source-by-source job counts, error log from `events` table
- **Prompt testing:** upload a test CV, run extraction, see the structured output — useful for tuning `skills/writing_style.md`
- **User admin:** view user count, application count; trigger `clear_user` for GDPR requests

**Why deferred:** The Streamlit chat is still the only way to generate applications outside the API. Before converting `app.py`, wire the generation endpoint (§6) so the Next.js app can do it. Then `app.py` can become pure admin.

**Immediate action:** Add authentication to `app.py`. Currently it runs in anonymous mode on Render with no auth guard. Anyone who knows the URL can use it as a free Gemini wrapper. The `GEMINI_API_KEY` should not be accessible to the public Streamlit instance. Options: Render's access policy (IP allowlist) or adding `st.login()` with an allowlist of admin Google accounts.

---

## 15. The Spec/Code Drift (MAINTENANCE)

`docs/engineering/03-database.md` documents the old schema (only `profiles` and `applications`). The actual `db.py` now has 6 tables. The doc shows the new tables as "Planned" when they are already built. 

Similarly, `docs/engineering/04-api.md` documents the old endpoints and shows `/jobs` and `/matches` as "future extensions" when they are live.

**Action:** Update the spec after every architectural change. This document was always supposed to be updated alongside `CHANGELOG.md`. A developer reading the spec will be misled about what's built. Spend 30 minutes after each sprint updating the relevant spec section.

---

## 16. The ATS Coverage Gap (PRODUCT LIMITATION — BE HONEST ABOUT IT)

**Current state:** The ingest worker supports Greenhouse and Lever (both have public APIs requiring no API key). These two ATSes cover a large portion of growth-stage tech companies but miss:

| ATS | Coverage | Status |
|---|---|---|
| Greenhouse | ~40% of YC/tech startups | ✅ Built |
| Lever | ~20% of growth-stage startups | ✅ Built |
| Ashby | ~15% of newer startups | ❌ Has public API (`jobs.ashby.io/api/postings?teamToken={token}`) — build next |
| Workday | Enterprise companies | ❌ No public API; requires scraping or partnerships |
| Taleo/Oracle | Banks, Nigerian corporates | ❌ No public API |
| Custom career pages | All others | ❌ Requires scraping; legal gray area |

For Ashby, the endpoint is `https://api.ashbyhq.com/posting-public/apiPostings/{token}` (open, no key). Adding it is a ~50-line handler in `workers/ingest_jobs.py` following the same pattern as `_ingest_greenhouse`. Add `"ashby"` to `_ATS_HANDLERS`.

For Workday/Taleo/custom career pages, the honest answer is: we cannot cover them cleanly without scraping, which has legal and stability risks. The `active: false` flag in `job_sources.json` for entries with `ats: "career_page"` is the right call — mark them, do not pretend.

**What to tell users:** "We currently source jobs from Greenhouse and Lever boards, covering thousands of companies. Career pages for banks and large multinationals like GTBank, Access Bank, Google, and Amazon are not currently sourced automatically — use the Trust Check to verify employers you find elsewhere."

---

## Known Bugs and Edge Cases Not Yet Fixed

### Dashboard `hasMatches = true` hardcoded

As documented in §1 above. The empty state ("Your Career Twin is getting to work") never renders for real users because `hasMatches` is `true` regardless. A new user who completes the wizard will see a dashboard with fictional job cards instead of the honest empty state. Fix: step 1.

### `list_matches` returns empty until workers have run

A user who signs up and completes the Career Twin wizard will have `matches` = [] until the nightly worker runs (or a manual trigger). The UI needs to handle this gracefully: show the "getting to work" state and prompt the user to come back later. This is partially handled by the `hasMatches` flag once step 1 is done.

### Match `job_id` from `match_users.py` vs the `scored` dict

In `workers/match_users.py`, the inner loop does:
```python
job_id = result.get("id")
```

But `core.match_jobs` returns `{**j, "index": i, "fit_score": ..., "reason": ...}` where `j` is the job dict from `ingested_jobs`. The `id` field is the `ingested_jobs.id` integer — this is correct. But verify with `SELECT * FROM matches` after the first real worker run that `job_id` values actually exist in `ingested_jobs.id`.

### Career Twin `email` field missing

The Career Twin wizard does not capture or store the user's email address. The notification worker (§5) needs it. The Google session has the email — capture it when the wizard completes or on first `GET /career-twin`. Add to the wizard's `complete` step:

```typescript
// In the wizard's final submit
await apiFetch("/career-twin", { method: "PATCH", body: JSON.stringify({
  data: { ...existingTwin, email: session.user.email }
}) });
```

### SQLite concurrency on Render

The API runs as a single uvicorn process (single thread by default on Render). If workers run as separate Render cron jobs, they share the SQLite file via the Render Disk. SQLite handles concurrent readers fine but concurrent writers will serialize. If the ingest worker and the API are both writing simultaneously during an hourly ingest run, writes will queue. This is acceptable at current scale. Document it as a known limitation; add `timeout=30` to `sqlite3.connect()` to avoid immediate lock errors.

### `EMPLOI_API_KEY` not set in production (open dev mode)

The API logs a loud `WARNING: EMPLOI_API_KEY not set — API running in OPEN DEV MODE` if the env var is absent. Confirm this is set in the Render dashboard for `emploi-api`. If it is not set, any HTTP client can call any endpoint by providing any `X-User-Id` header and impersonate any user.

---

## The Complete Launch Checklist

From `docs/engineering/09-deployment.md` and the gaps above:

### Technical (Developer)
- [ ] Wire real matches into dashboard and matches page (§1)
- [ ] Wire real Career Twin data into career-twin page (§1c)
- [ ] Fix ApplyButton to use real job data (§2)
- [ ] Add cron services to `render.yaml` for Worker 1 + Worker 3 (§3)
- [ ] Build Worker 2 — verify employers (§4)
- [ ] Build Worker 4 — email notifications, requires Resend account (§5)
- [ ] Build application generation endpoint + UI (§6)
- [ ] Build Settings page with data deletion (§7)
- [ ] Add rate limiting to the API (§8)
- [ ] Add CI workflow (§12)
- [ ] Implement DB backup (§13)
- [ ] Add Ashby ATS handler (§16)
- [ ] Remove `AUTH_DEV_LOGIN=true` from production Vercel env
- [ ] Confirm `EMPLOI_API_KEY` is set in Render
- [ ] Update `docs/engineering/03-database.md` and `04-api.md` to reflect current state

### Legal / Business
- [ ] Draft privacy policy covering CV/profile storage, NDPA/GDPR rights, email notifications (§9)
- [ ] Draft terms of service
- [ ] Add privacy + terms links to app footer and login page
- [ ] Publish Google OAuth consent screen (requires privacy policy URL) (§11)
- [ ] Domain emploihq.com → static landing page live (Hostinger)
- [ ] Verify HTTPS on all three tiers

### Operational
- [ ] Resend account created, emploihq.com domain verified for email sending
- [ ] Cloudflare R2 bucket created for DB backups (or Litestream configured)
- [ ] First manual worker run verified end-to-end (jobs → matches → visible on dashboard)
- [ ] PostHog (or equivalent) installed for usage analytics
- [ ] Alert/monitor on the API health endpoint (UptimeRobot is free)

### Product (Content)
- [ ] 130 job sources verified — spot-check 10 at random that Greenhouse/Lever API returns jobs
- [ ] Privacy policy explains what Gemini processes (CVs are sent to Google's API — this must be disclosed)
- [ ] Low-trust warning ("never pay a fee...") visible and tested on apply flow
- [ ] Error messages user-facing and in English (not stack traces)

---

## Architecture Decisions Made — Do Not Revisit Without Cause

These were deliberate choices. The context for each is in `CLAUDE.md` and the spec. Do not change them without re-reading the rationale:

1. **SQLite over Postgres.** One process on Render. No concurrent write contention at current scale. Migration to Postgres is triggered by multi-instance need, not calendar. The migration is documented in `docs/engineering/03-database.md`.

2. **Logic in `core.py`/`verify.py`, never `app.py` or `api/main.py`.** Every `if` that isn't UI dispatch or HTTP validation is in the wrong file. This is not style — it is what makes the system testable offline.

3. **Trust scores computed in code, never by an LLM.** `verify.compute_trust()` maps signals to points deterministically. An LLM cannot be argued into changing a score by a malicious job posting. This is the core of the scam-protection promise.

4. **Fake model / injected I/O in tests.** Every test runs offline. `FakeModel`, injected `dns_fn`/`mx_fn`/`fetch_fn`. Never a real API call or network probe in tests. If your test needs real network, the test is wrong.

5. **Skills are the prompt system.** `skills/*.md` is how you change AI behaviour without touching Python. Tests assert that skill marker phrases appear in built prompts. Rewrite a skill = update its markers and the tests that check them, together.

6. **`job_sources` DB as source of truth after first seed.** Edit sources via the admin API or directly in the DB. The JSON file is for bootstrapping only. Adding sources in `data/job_sources.json` after the DB is populated does nothing unless you call `POST /admin/job-sources/seed` (which is a no-op if the table is non-empty) — you need to use `POST /admin/job-sources` instead.

---

## Cost Model (Current)

| Component | Cost/month | Notes |
|---|---|---|
| Render API service (paid, no sleep) | $7 | Required; free tier sleeps and loses disk |
| Render Disk (1GB) | $1 | Mounted at `/var/data`; the SQLite file lives here |
| Render Cron (Worker 1 + 3) | $7–14 | 1–2 starter cron services at $7 each |
| Vercel (web tier) | $0 | Hobby tier; upgrade at $20/mo if team needed |
| Gemini API | ~$0.02/application, ~$0.001/match batch | 2.5-flash pricing; monitor at scale |
| Resend (email) | $0 for 3k/mo | Sufficient for early users |
| Cloudflare R2 (DB backups) | $0 for <10GB | |
| **Total** | **~$15–30/mo** | Before significant user volume |

At 100 active users generating 10 applications/month each: +$20/mo in Gemini costs. At 1000 users: $200/mo. Plan for Gemini cost before scale — the model is the unit cost, not infrastructure.

---

## Where the Code Lives for Each Feature

Quick reference for a developer starting any section of this work:

| Feature | Files to read | Files to change |
|---|---|---|
| Real dashboard data | `web/app/(app)/dashboard/page.tsx`, `web/lib/data.ts`, `web/lib/api.ts` | `dashboard/page.tsx`, `web/lib/data.ts` (add transform functions) |
| Real matches | `web/app/(app)/matches/page.tsx`, `web/app/api/matches/route.ts`, `api/main.py` (`GET /matches`) | `matches/page.tsx` |
| Career Twin page | `web/app/(app)/career-twin/page.tsx`, `api/main.py` (`GET /career-twin`) | `career-twin/page.tsx` |
| Worker 2 (verify) | `verify.py`, `db.py` (`upsert_trust_record`), `workers/ingest_jobs.py` (pattern) | new `workers/verify_employers.py` |
| Worker 4 (notify) | `db.py` (`list_matches`), `workers/match_users.py` (pattern) | `db.py` (add `notified` column), new `workers/notify_users.py` |
| Application generation | `core.py` (`generate_application`), `api/main.py` | `api/main.py` (add endpoint), new `web/app/api/applications/generate/route.ts` |
| Settings + deletion | `api/main.py` (`DELETE /user`), `db.py` (`clear_user`) | new `web/app/(app)/settings/page.tsx`, `web/components/Sidebar.tsx` |
| Rate limiting | `api/main.py` | `api/main.py` |
| Notifications | `db.py`, `verify.py`, `render.yaml` | `db.py` (migration), new `workers/notify_users.py`, `render.yaml` (cron) |
| CI | none | new `.github/workflows/test.yml` |
| Privacy policy | none | new `web/app/privacy/page.tsx`, `web/app/terms/page.tsx`, `web/components/Sidebar.tsx` |

---

## Final Honest Assessment

The infrastructure is solid. The data model is right. The trust engine is the real moat and it works. The AI layer is well-designed and testable. The workers are built and tested.

What Emploi does not yet have is **a complete product loop**. A user can sign in, upload a CV, and get a Career Twin. They cannot yet see their own real job matches, get a notification that new ones arrived, or generate a tailored application from the web UI. These are all buildable with the infrastructure that exists — they are wiring tasks, not design tasks. Every missing piece connects to something that already works.

The most important single action after reading this is: **wire real matches into the dashboard** (§1). Once a real user can see "I found 12 new jobs for you" based on their actual Career Twin, the product becomes real. Everything else builds from that moment.
