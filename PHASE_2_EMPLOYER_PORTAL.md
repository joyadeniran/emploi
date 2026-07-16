# Phase 2 — Employer Portal (Executor Spec)

> **⚠️ ADDENDUM 2026-07-16 — decisions resolved with Joy during execution.**
> Where this addendum conflicts with the body below, the addendum wins.
> The build shipped 2026-07-16 implements the addendum.
>
> **Billing model replaced (§10 items 1, 3, 6).** No pay-per-role fee, no
> employer subscription. Instead **pay-per-unlock**: role #1 is entirely free
> (posting → shortlist → up to **10** invites, hard 429 above; contact
> revealed on candidate ACCEPT). Every later role is free to post and view
> its shortlist, but inviting a candidate requires **unlocking** them first —
> ₦1,000 per candidate, sold as credit packs (minimum 5 = ₦5,000, one-time
> Paystack checkout, `employer_credit_ledger` + `candidate_unlocks` tables).
> Volume discounts deferred.
>
> **Contact-reveal rule changed (supersedes §3's accept-only promise).** On
> PAID roles, an unlock reveals the candidate's structured contact view
> immediately (Joy's explicit decision). On the FREE role the classic
> accept-gated flow stays. The Settings opt-in copy discloses both honestly
> — consent is informed; nobody had opted in before this shipped.
>
> **Warm intros (§10 item 5, §5.9).** No pre-created employer rows and no
> `POST /admin/employers`. Everyone — including Joy's contacts — signs up
> cold via Google and runs the trust check. Joy vouches employers AFTER
> signup from the new **Next.js `/admin` dashboard** (metrics rollup +
> trust-alert list + vouch button; backed by `GET /admin/metrics` and
> `POST /admin/employers/{id}/vouch`, gated by `ADMIN_EMAILS` on the web
> tier and `X-API-Key` at the API).
>
> **Trust mapping (§5.9).** Implemented as spec'd
> (`verify.employer_portal_level`), with one portal-only cap: a company
> domain that fails DNS can never rate better than "low" (at onboarding
> there's no job text for red flags, and the domain-as-contact corporate
> bonus would otherwise let a dead domain reach "medium"). Also, onboarding
> verifies the COMPANY DOMAIN (worker-style), not the session email — under
> Google-auth-for-everyone a personal-gmail contact would flatten every cold
> signup to "low". Candidate-side scoring untouched.
>
> **Notify worker (§5.6).** Deviation from the snippet: candidates with
> fresh pending invites get a digest even with zero new matches (an invite
> expires in 14 days; email is the channel). Dedup is a `notified` flag on
> `interview_invites` (same pattern as `matches.notified`), not the 1-day
> window.
>
> **Confirmed as proposed:** 14-day expiry (item 2), low-trust = badge
> warning (4), close-reason nudge (7), warm invite email copy (8), accept
> returns employer contact email (9), small "Hiring?" link on /login (10).
> Hire confirmation is inline on the role page rather than a separate
> `/hire` route.

**Written:** 2026-07-15
**Scope:** Everything discussed in this session. Read straight through before touching code.
**Prerequisites:** `CLAUDE.md`, `HANDOVER.md`, `SPEC.md`, `docs/engineering/01–10`.
**Assumes:** Session 2026-07-14/15 shipped state (12 test suites, 597 checks, all green).

This document is the complete brief for building Emploi's employer portal — the second product surface in the three-workspace vision. It merges the strategic conversation (ChatGPT + Claude + Joy) with concrete engineering execution. The executor should not need to re-derive any decision from scratch.

---

## 1. Executive Summary

Emploi expands from a candidate-only tool to a two-sided marketplace. Long-term architecture is **three workspaces sharing one intelligence layer**:

1. **Career Twin Workspace** — for professionals (exists, in production)
2. **Employer Portal** — for hiring managers first, agencies later (this build)
3. **Career Advisor Workspace** — for bootcamps/NGOs/coaches (deferred until candidate CAC becomes painful)

**Phase 2 goal:** launch a freemium employer portal targeted at hiring managers Joy pitches through her LinkedIn network. Pattern is **Interview Marketplace**: candidate must accept an invite before the employer sees any contact information. Employer never sees raw CV — only the structured Career Twin view, and only after accept.

**Pricing:** first role is entirely free (unlimited candidates, unlimited invites, hard cap 30 to prevent abuse). Second role requires Paystack payment (₦20,000/role or upgrade to unlimited monthly).

**Supply side:** run Meta ads to grow opted-in Career Twin pool. Do not demo the employer product until the pool is 500+ opted-in Twins.

**Sequencing:** ~6-7 weeks total. Candidate polish + Meta ads (week 1-2), employer build (week 2-5), founder-led sales to 5 warm intros (week 5-7), open self-serve signup (week 7+).

**Founder-led sales:** Joy is the salesperson for the first 20 employers. Do not hire before then.

---

## 2. What's Already Shipped (This Session, 2026-07-14/15)

Do not re-implement any of the following. All 12 test suites green.

- **Workable + SmartRecruiters ATS handlers** (`_ATS_HANDLERS` now covers 6: greenhouse, lever, ashby, workable, smartrecruiters, manual)
- **`_derive_company_domain` heuristic** — every ingested job gets a guessed employer domain (`_derive_company_domain(company_name)` → `{slug}.com`, with stopword stripping for Inc/Ltd/Co/GmbH etc)
- **`verify_employers` fix** — prefers `company_domain` over `apply_url`; `ATS_HOSTS` covers all 5 ATSes defensively; `_is_ats_host` filter
- **Diagnostics endpoint** — `GET /admin/diagnostics` returns `{ready_for_launch, open_items[], config, last_worker_runs, counts}` with API-key auth. Never emits secret values.
- **Spot-check + heal workers** — `workers/spot_check_sources.py` (safe on prod, no writes), `workers/heal_job_sources.py` (auto-disables dead sources in DB). Live spot-check on 2026-07-15 revealed 85 of 100 active tokens dead; seed patched.
- **Users table** — `users(id, email, name, email_verified, notifications_enabled, created_at, last_seen_at)`. Source of truth for email + digest opt-in, replaces the `career_twins.data.email` PII blob.
- **`POST /user/session`** — idempotent per-render upsert, called by web tier in `(app)/layout.tsx`.
- **`PATCH /user/notifications`** — digest opt-in toggle.
- **Outcome tracking** — `applied → heard_back → interview → offer → rejected | withdrawn | ghosted` (7 valid statuses). `outcome_notes` + `outcome_updated_at` columns. Notify worker adds "How did these go?" prompts (capped 5/user) for applications still `applied` after 14 days.
- **Manual curation ATS handler** (`_ingest_manual`) — reads `data/manual_jobs/{token}.json`; auto-expires entries older than 30 days; malformed rows skipped.
- **12 offline test suites** — `test_e2e`, `verify`, `db`, `api`, `ingest`, `billing`, `landing`, `backup_db`, `notify_worker`, `verify_worker`, `spot_check`, `heal_sources`. All green.

**Files added or modified this session:** `db.py`, `api/main.py`, `data/job_sources.json`, `data/manual_jobs/README.md + example.json`, `workers/{ingest_jobs, notify_users, verify_employers, spot_check_sources, heal_job_sources}.py`, `docs/engineering/{03,04}.md` + new `10-billing.md`, plus corresponding test files.

---

## 3. Strategic Decisions (Locked — do not re-open without Joy)

Each of these is defended in the transcript. If the executor's instinct is to violate one, stop and ask.

### Non-negotiables

- **Candidate opt-in for recruiter visibility. Default OFF.** No exceptions. `career_twins.recruiter_visibility = 0` unless the candidate explicitly enables it in Settings.
- **Interview Marketplace pattern.** Employer never sees the candidate's email, phone, or raw CV until the candidate has ACCEPTED an interview invite. Not "invited"; ACCEPTED. This is the entire trust promise.
- **Structured Twin view, never raw CV.** After accept, employer sees name, email, phone, headline, skills, experience, education — all from the Career Twin. If the candidate wants to send their CV, they attach it in the follow-up email (out of Emploi). This keeps Emploi as the curation layer, not a résumé passthrough.
- **Trust engine gates strangers.** Cold employer signup runs through `verify.compute_trust`. Low-trust employers get badge warnings shown to candidates; "avoid"-tier (< 20 or red-flagged) employers are blocked from posting entirely.
- **Warm intros bypass trust gate.** Joy manually flags her LinkedIn network with `employers.warm_intro_by = 'joy'`. These skip the trust check because she vouches personally.
- **No search / no filter UI for employers.** Emploi computes the shortlist. Employer approves/invites, doesn't hunt. This is the AI-first UX. If they reject the shortlist, we regenerate with prompt refinement, NOT expose search.
- **First hiring experience is completely free.** One role, unlimited shortlisted candidates for that role, unlimited invites (hard cap 30 for abuse). Second role requires payment.
- **Founder-led sales for first 20 employers.** Joy pitches; every demo is a product research call. Do not hire a salesperson before this threshold.
- **Direct-to-hiring-manager, NOT agencies.** Agencies were considered and rejected: high fraud risk, brand dilution, worse economics for Emploi's stage. Revisit only if Phase 2 stalls.

### Explicit "we will not build this" list

- **LinkedIn / Indeed / Workday scraping.** LinkedIn blocks bots; Indeed same; Workday has no public API. Attempts to work around these are legally and operationally unsafe. Non-negotiable.
- **LinkedIn Recruiter competitor.** That market is saturated (LinkedIn, Greenhouse, Ashby, Lever, SmartRecruiters, Workday). Distribution advantages we lack. Do not chase.
- **Boolean query builder / advanced search.** Same reason as "no search" above.
- **Bulk outreach.** Interview Marketplace pattern requires per-invite intent from the employer.
- **Message threads inside Emploi.** After accept, employer and candidate move to email/calendar. Emploi is not a communication platform.
- **AI-generated employer outreach.** Employer types their invite note or uses a template. We do not automate messages from employers to candidates — that reads as spam.
- **Skills assessment / tests / reference checks.** Out of scope.
- **Employer-to-employer marketplace.** Never.

### Naming

- **External (candidate-facing / employer-facing):**
  - Product for employers: **Employer Portal**
  - Candidate invite section: **Interview Invites** (`/invites`)
- **Internal shorthand (docs, code):**
  - Employer-facing product: "Placement Engine" (optional; use if wording matters in copy)
  - Candidate invite view: "Opportunity Inbox" (deferred internal rename)
  - Advisor product (deferred): "Cohort Dashboard"

---

## 4. Three Workspaces Vision (Long-Term Context)

This section is context for why Phase 2 is shaped this way. Not for implementation.

- **Career Twin Workspace (Phase 1, live):** professionals build a Career Twin, get tailored applications, use Import-a-Job, track outcomes.
- **Employer Portal (Phase 2, this build):** hiring managers post one free role, see Emploi-curated shortlist, invite candidates through Interview Marketplace.
- **Career Advisor Workspace (Phase 4+, deferred):** bootcamps/universities/NGOs review cohort Career Twins, track placement outcomes, receive alerts when opportunities match their cohorts. Deferred until candidate CAC becomes painful; Halo pilot is a one-off partnership, not the trigger.

All three consume the same underlying data (Career Twins, verified employers, jobs pool, trust engine) but present purpose-built interfaces. Not one-size-fits-all.

**Agency Workspace is explicitly NOT in the vision.** Considered and rejected in favor of direct-to-hiring-manager.

---

## 5. Phase 2 Build

### 5.1 Product Overview

**Who it's for:** in-house hiring managers, founders, or team leads at small-to-mid companies (primarily African corridor, but works for any remote-hiring company). Not agencies. Not corporate TA teams (they use Greenhouse/Ashby already).

**Core loop:**

1. Hiring manager signs in (Google OAuth, same as candidate side — one user account can have both a `career_twins` row AND an `employer_users` row)
2. Onboards their employer: company name, domain (auto-guessed from name, override available)
3. Trust engine runs on the domain (or skipped for warm intros)
4. Posts their first role: pastes a URL from a supported ATS OR pastes raw JD text
5. Emploi extracts the role and generates a ranked shortlist against opted-in Career Twins
6. Hiring manager reviews shortlist (no search, no filters), invites promising candidates with an optional note
7. Candidate receives email + dashboard badge; opens `/invites`; accepts or declines
8. On accept, employer sees the structured Career Twin (email, phone, full skills/experience)
9. Employer messages candidate outside Emploi (email/calendar); when hired, marks role hired
10. Second role requires payment via Paystack

**Sales motion:** Joy pitches her warmest LinkedIn contacts who are hiring. Warm intros get their employer pre-created with `warm_intro_by='joy'` so they skip trust verification. First demo has to be magical — do not start pitching before 500+ opted-in Career Twins are in the pool.

**Freemium philosophy:** first hiring experience is completely free because we're optimizing for learning and proof, not revenue. If they close a hire, the ask for role #2 sells itself. If they don't, we learn why. Either outcome beats churn at "3 invites used."

### 5.2 Sequencing & Timeline

| Week | Work | Gate |
|---|---|---|
| 1-2 | `recruiter_visibility` column + toggle in Settings + wizard polish + Meta ad landing/creative | Wizard end-to-end < 3 min |
| 2-3 | Meta ads soft launch (small budget) + employer schema migrations + `extract_job_from_url` + `extract_single_job` | Meta ad candidate opt-in rate ≥ 30% |
| 3-4 | Employer endpoints (onboarding, roles CRUD, shortlist, invites); candidate endpoints (invites listing/accept/decline); employer dashboard React pages | All new endpoints tested |
| 4-5 | Trust integration in onboarding; freemium gate; Paystack Employer plan code; notify worker invite path; `expire_invites` worker + cron; `emploihq.com/employers` landing | 500+ opted-in Career Twins |
| 5-6 | Joy hand-creates 5 warm-intro employer rows (SQL); pitches 5 warmest LinkedIn contacts; iterates on demos | 5 warm-intro employers onboarded |
| 6-7 | Fix bugs surfaced by demos; open self-serve employer signup with trust gating | Trust flow tested against real employers |
| 7+ | Scale Meta ads on candidate side; watch for signal on deferred items | — |

**Critical ordering rule:** candidate opt-in pool must reach 500+ BEFORE the first employer demo. A demo with 3 weak matches burns a warm intro forever. Ads before employer product prevents this; employer product ready-but-unlaunched is fine.

### 5.3 Data Model

Schema-first. All new tables + additive migrations below.

```sql
-- ────────────────────────────────────────────────────────────
-- NEW TABLES (Phase 2)
-- ────────────────────────────────────────────────────────────

-- One row per registered employer. Auto-computed trust; warm intros bypass.
CREATE TABLE IF NOT EXISTS employers (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name           TEXT NOT NULL,
    company_domain         TEXT,           -- guessed via _derive_company_domain or user override
    trust_score            INTEGER,        -- from verify.compute_trust; NULL for warm intros
    trust_level            TEXT,           -- 'high' | 'medium' | 'low' | 'avoid' | NULL
    warm_intro_by          TEXT,           -- 'joy' etc; NULL for cold signup; skips trust gate
    verified_at            TEXT,           -- datetime; NULL if never verified
    created_at             TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at             TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_employers_domain ON employers(company_domain);
CREATE INDEX IF NOT EXISTS idx_employers_warm   ON employers(warm_intro_by);

-- Which users belong to which employer. v1 = 1 employer per user; teams later.
CREATE TABLE IF NOT EXISTS employer_users (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                TEXT NOT NULL,             -- FK users.id (Google sub)
    employer_id            INTEGER NOT NULL REFERENCES employers(id),
    role                   TEXT NOT NULL DEFAULT 'owner',   -- 'owner' | 'member'
    created_at             TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, employer_id)
);
CREATE INDEX IF NOT EXISTS idx_employer_users_user ON employer_users(user_id);
CREATE INDEX IF NOT EXISTS idx_employer_users_emp  ON employer_users(employer_id);

-- One row per posted role.
CREATE TABLE IF NOT EXISTS employer_roles (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    employer_id              INTEGER NOT NULL REFERENCES employers(id),
    title                    TEXT NOT NULL,
    description              TEXT NOT NULL,           -- JD; HTML-stripped
    location                 TEXT,
    is_remote                INTEGER NOT NULL DEFAULT 0,
    salary_text              TEXT,
    source_url               TEXT,                    -- if pasted; else NULL
    source_ats               TEXT,                    -- greenhouse|lever|ashby|workable|smartrecruiters|raw
    status                   TEXT NOT NULL DEFAULT 'open',  -- 'open' | 'closed' | 'hired'
    invites_sent             INTEGER NOT NULL DEFAULT 0,    -- denormalized abuse counter
    created_by_user_id       TEXT NOT NULL,
    created_at               TEXT NOT NULL DEFAULT (datetime('now')),
    closed_at                TEXT,
    hired_at                 TEXT,
    hired_candidate_user_id  TEXT                     -- set when POST /hire fires
);
CREATE INDEX IF NOT EXISTS idx_employer_roles_emp    ON employer_roles(employer_id);
CREATE INDEX IF NOT EXISTS idx_employer_roles_status ON employer_roles(status);

-- Interview Marketplace state machine.
CREATE TABLE IF NOT EXISTS interview_invites (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    employer_role_id       INTEGER NOT NULL REFERENCES employer_roles(id),
    candidate_user_id      TEXT NOT NULL,             -- FK users.id
    invited_by_user_id     TEXT NOT NULL,             -- FK users.id via employer_users
    fit_score              INTEGER,
    invite_note            TEXT,                      -- optional employer message
    status                 TEXT NOT NULL DEFAULT 'pending',  -- pending|accepted|declined|expired|hired
    responded_at           TEXT,
    decline_reason         TEXT,
    expires_at             TEXT NOT NULL,             -- default now + 14 days
    created_at             TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(employer_role_id, candidate_user_id)
);
CREATE INDEX IF NOT EXISTS idx_invites_role      ON interview_invites(employer_role_id);
CREATE INDEX IF NOT EXISTS idx_invites_candidate ON interview_invites(candidate_user_id);
CREATE INDEX IF NOT EXISTS idx_invites_status    ON interview_invites(status);
CREATE INDEX IF NOT EXISTS idx_invites_expires   ON interview_invites(expires_at);

-- Cached shortlist per role. Prevents re-spending Gemini on repeat views.
CREATE TABLE IF NOT EXISTS role_shortlists (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    employer_role_id       INTEGER NOT NULL REFERENCES employer_roles(id),
    candidate_user_id      TEXT NOT NULL,
    fit_score              INTEGER,
    reason                 TEXT,
    created_at             TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(employer_role_id, candidate_user_id)
);
CREATE INDEX IF NOT EXISTS idx_shortlists_role ON role_shortlists(employer_role_id);
```

**Additive `_migrate` statement:**

```sql
ALTER TABLE career_twins ADD COLUMN recruiter_visibility INTEGER NOT NULL DEFAULT 0;
```

**`clear_user` extension** — when a user deletes their account:

```python
# In db.clear_user:
conn.execute("DELETE FROM interview_invites WHERE candidate_user_id = ?", (user_id,))
conn.execute("DELETE FROM role_shortlists    WHERE candidate_user_id = ?", (user_id,))
# For employer_users: close their employer's open roles, then delete the row
conn.execute("""
    UPDATE employer_roles SET status = 'closed', closed_at = datetime('now')
    WHERE employer_id IN (SELECT employer_id FROM employer_users WHERE user_id = ?)
      AND status = 'open'
""", (user_id,))
conn.execute("DELETE FROM employer_users WHERE user_id = ?", (user_id,))
# employers row stays (audit; if orphaned, that's fine — no active user can access it)
```

**Every new table gets its own test in `test_db.py` covering CRUD + `clear_user` coverage.**

### 5.4 API Endpoints

All employer endpoints authenticated with the same `Depends(auth)` (X-API-Key + X-User-Id). Employer endpoints additionally require the authenticated user to have an `employer_users` row.

**Employer side:**

```
POST   /employer/onboarding
       Body: {company_name: str, company_domain?: str}
       Behavior: creates employers row + employer_users row (role='owner');
         if company_domain not provided, derives via _derive_company_domain;
         if warm_intro_by is NOT set on the row (i.e. cold signup), runs
         verify.verify_employer on the domain and stores trust_score/level;
         if resulting trust_level is 'avoid', deletes the row and returns 403.
       Returns: {employer_id, trust_score, trust_level, warm_intro_by}
       Errors: 409 if user already has an employer_users row; 403 if avoid-tier

GET    /employer
       Returns: {employer: {id, company_name, company_domain, trust_score,
                            trust_level, warm_intro_by, verified_at,
                            free_role_used: bool}}
       Errors: 404 if user has no employer_users row

PATCH  /employer
       Body: {company_name?, company_domain?}
       Behavior: updates the fields; if domain changes, re-runs verify.py
       Returns: {ok: true, trust_score, trust_level}

POST   /employer/roles
       Body: {url?: str, jd_text?: str, title_override?: str}
       Behavior:
         1. Freemium gate: if employer already has ≥ 1 role AND no active paid
            subscription, return 402 with Paystack checkout URL in detail
         2. If url provided: try core.extract_job_from_url(url).
            If it returns {"error": "unsupported_host", ...}, return 422 with detail
            If it returns None and no jd_text, return 422 "couldn't extract"
         3. If jd_text provided (or url extraction failed): call
            core.extract_single_job(model, jd_text). Uses require_model();
            503 if no GEMINI_API_KEY.
         4. Create employer_roles row, source_url + source_ats populated
         5. Async: trigger shortlist generation for this role (see below)
       Returns: {role_id, title, location, is_remote, extracted_from: 'url'|'text'}
       Errors: 422 (validation), 402 (freemium), 503 (no AI), 500 (extraction crash)

GET    /employer/roles
       Query: ?status=open|closed|hired (optional, default all)
       Returns: {roles: [{id, title, status, invites_sent, accepted_count,
                          created_at, unread_responses: int}]}

GET    /employer/roles/{role_id}
       Returns: {role: {id, title, description, location, is_remote,
                         salary_text, source_url, source_ats, status,
                         invites_sent, created_at}}
       Errors: 404 (not your role)

PATCH  /employer/roles/{role_id}
       Body: {title?, description?, location?, is_remote?, salary_text?}
       Behavior: updates. If description changes materially, next
         /shortlist call should regenerate rather than serve cache.
       Returns: {ok: true}

POST   /employer/roles/{role_id}/close
       Behavior: status='closed', closed_at=now. All pending invites for this
         role auto-expire.
       Returns: {ok: true, expired_invites: int}

POST   /employer/roles/{role_id}/hire
       Body: {invite_id: int}
       Behavior: verify invite_id belongs to this role AND status='accepted';
         set role.status='hired', role.hired_at=now, role.hired_candidate_user_id;
         set that invite.status='hired'; auto-expire all other pending invites.
         Emit HireCompleted event (revenue trigger analytics).
       Returns: {ok: true, hired_at, expired_other_invites: int}
       Errors: 422 (invite not accepted); 404 (not your role/invite)

GET    /employer/roles/{role_id}/shortlist
       Query: ?limit=20 (default), ?offset=0
       Behavior: returns cached role_shortlists rows joined with career_twins
         data (only recruiter_visibility=1 candidates). If cache is empty,
         synchronously generates it. Excludes candidates already invited.
       Returns: {shortlist: [{candidate_id, fit_score, reason, headline,
                              skills[], experience_summary, location,
                              already_invited: bool}], total, cache_age: sec}
       Rate limit: 30/min

POST   /employer/roles/{role_id}/shortlist/refresh
       Body: {refinement_note?: str}  -- e.g. "candidates lacked startup exp"
       Behavior: deletes cached shortlist, regenerates. If refinement_note
         provided, injects into the match prompt so the new shortlist responds.
       Returns: 202 {started: true}; poll /shortlist afterward
       Rate limit: 3/hour (Gemini spend)

POST   /employer/roles/{role_id}/invites
       Body: {candidate_user_id: str, invite_note?: str}
       Behavior:
         1. Verify candidate exists AND recruiter_visibility=1
         2. Verify no existing invite for this (role, candidate) pair
         3. Verify role.invites_sent < 30 (abuse cap; if hit, return 429
            with "reasonable limit; contact hello@emploihq.com")
         4. Create interview_invites row with expires_at = now + 14 days,
            status='pending', fit_score copied from role_shortlists
         5. Increment role.invites_sent
         6. Enqueue email notification (via notify worker) + dashboard badge
       Returns: {invite_id, expires_at}
       Errors: 404 (candidate not opted-in), 409 (already invited),
               429 (invite cap reached)

GET    /employer/billing/status
       Returns: {free_role_used: bool, active_subscription: {tier, status,
                current_period_end}, checkout_url: str (if free_role_used and
                no active subscription)}

POST   /employer/billing/checkout
       Body: {tier: 'pay_per_role'|'unlimited'}
       Returns: {authorization_url: str}   -- Paystack redirect
```

**Candidate side:**

```
GET    /invites
       Query: ?status=pending|accepted|declined|expired|hired|all (default pending)
       Returns: {invites: [{id, role: {title, description_preview, location,
                                        is_remote, salary_text},
                             employer: {company_name, trust_score, trust_level,
                                        verified: bool},
                             fit_score, invite_note, status, expires_at,
                             created_at, responded_at}]}

GET    /invites/count
       Returns: {pending: int, all: int}
       Purpose: dashboard badge; cached client-side 60s
       Rate limit: 60/min

GET    /invites/{invite_id}
       Returns: full detail including role.description (not just preview) and
         employer trust evidence
       Errors: 404 (not your invite)

POST   /invites/{invite_id}/accept
       Behavior: verify invite.status='pending' AND expires_at > now;
         set status='accepted', responded_at=now.
         From this moment: employer can query the structured Twin including
         email + phone (unlock event).
       Returns: {ok: true, employer_contact_email: str}
         (also returns the employer's contact email so the candidate can
         reach out first if they want to — keeps agency in candidate's hands)
       Errors: 409 (not pending), 410 (expired)

POST   /invites/{invite_id}/decline
       Body: {reason?: str}  -- optional; nudge but don't require
       Behavior: verify pending; set status='declined', responded_at=now,
         decline_reason=body.reason
       Returns: {ok: true}

PATCH  /career-twin/recruiter-visibility
       Body: {enabled: bool}
       Behavior: sets career_twins.recruiter_visibility for the current user.
         If enabling from off, log a UserOptedInToRecruiterVisibility event
         for cohort analytics.
       Returns: {ok: true, recruiter_visibility: bool}
```

**Admin side (Joy):**

```
POST   /admin/employers
       Auth: X-API-Key only (admin_key_auth)
       Body: {company_name, company_domain, warm_intro_by: 'joy',
              creator_user_id: str, creator_email: str}
       Behavior: creates employer + employer_users row for the specified user.
         Skips verify.py; sets verified_at=now, trust_score=NULL,
         trust_level=NULL, warm_intro_by='joy'.
         If creator doesn't exist in users table yet, creates the users row
         too (so the invite email works before they've signed in).
       Returns: {employer_id, employer_users_id}
       Purpose: Joy's tool for pre-creating warm-intro employers before pitching
```

### 5.5 Core.py Additions

**`extract_job_from_url(url: str, fetch_fn=None) -> dict | None`**

Dispatcher keyed on URL hostname. Returns a job dict in the same shape as `db.upsert_job` fields (`title, company_name, description, location, is_remote, salary_text, apply_url, category, company_domain`). Returns `None` for unknown hosts (caller falls back to text extraction). Returns `{"error": "unsupported_host", "detail": "..."}` for LinkedIn/Indeed (explicit rejection with helpful message).

Supported hosts:

| Host pattern | API endpoint constructed |
|---|---|
| `boards.greenhouse.io/{token}/jobs/{id}` | `boards-api.greenhouse.io/v1/boards/{token}/jobs/{id}` |
| `job-boards.greenhouse.io/{token}/jobs/{id}` | same as above |
| `job-boards.eu.greenhouse.io/{token}/jobs/{id}` | `boards-api.eu.greenhouse.io/v1/boards/{token}/jobs/{id}` |
| `jobs.lever.co/{slug}/{jobId}` | `api.lever.co/v0/postings/{slug}/{jobId}?mode=json` |
| `jobs.ashbyhq.com/{company}/{jobId}` | `api.ashbyhq.com/posting-public/apiPostings/{company}/{jobId}` |
| `apply.workable.com/{account}/j/{shortcode}` | `apply.workable.com/api/v3/accounts/{account}/jobs/{shortcode}` |
| `jobs.smartrecruiters.com/{company}/{jobId}` | `api.smartrecruiters.com/v1/companies/{company}/postings/{jobId}` |
| `linkedin.com/*`, `indeed.com/*` | Returns `{"error": "unsupported_host", "detail": "LinkedIn/Indeed doesn't allow us to read their job pages. Paste the JD text directly, or on the LinkedIn page click 'Apply on Company Site' — if that link goes to Greenhouse/Lever/Ashby, paste THAT URL instead."}` |
| Anything else | Returns None |

Reuse existing `_ingest_greenhouse`, `_ingest_lever`, `_ingest_ashby`, `_ingest_workable`, `_ingest_smartrecruiters` normalization logic — extract into module-level helpers that both the ingest worker and this function can call. Do not duplicate.

**`extract_single_job(model, text: str) -> dict | None`**

Gemini-backed extraction for pasted JD text. Wraps existing `extract_jobs` primitive with a single-job return. Uses the same `parse_json_array` / defensive parsing. Returns `None` for garbage input (never raises).

**`build_role_shortlist_prompt(role: dict, candidates: list[dict], refinement_note: str = "") -> str`**

New function for `/shortlist/refresh`. Mirrors `build_match_prompt` but role-anchored: one role description, many Career Twin summaries, asked to rank the candidates for THIS role. Injects `refinement_note` when present (e.g. "prior shortlist lacked startup experience — weight that heavily"). Preserves the `Fit Score: NN/100` contract.

**`format_invite_email(invite, role, employer, candidate) -> tuple[str, str]`**

Returns `(subject, body)` for the invite notification email. Includes employer name + trust badge, role title + location + remote/onsite, invite note, one-click accept URL (`https://app.emploihq.com/invites/{id}`), 14-day expiration reminder. Body must be safe against injection (escape user-generated `invite_note`).

**`format_employer_contact_view(candidate_twin: dict) -> dict`**

Called after invite accept. Returns the structured Twin fields employers get to see: name, email, phone, headline, skills, experience, education, location, career_goals. Explicitly does NOT include: raw uploaded CV, raw chat history, application history at other employers, tailored_applications generated for other roles. If any field is missing, returns empty string not `None` (avoids `None` rendering).

### 5.6 Worker Changes

**`workers/notify_users.py`** — extend to include interview invites:

```python
# In the run() loop, after the matches digest section is built:
pending_invites = conn.execute("""
    SELECT ii.id, ii.invite_note, ii.fit_score, ii.expires_at,
           er.title AS role_title, er.location AS role_location, er.is_remote,
           e.company_name, e.trust_score, e.trust_level
    FROM interview_invites ii
    JOIN employer_roles er ON er.id = ii.employer_role_id
    JOIN employers e ON e.id = er.employer_id
    WHERE ii.candidate_user_id = ?
      AND ii.status = 'pending'
      AND ii.expires_at > datetime('now')
      AND (ii.responded_at IS NULL OR datetime(ii.created_at) > datetime('now', '-1 days'))
    ORDER BY ii.created_at DESC LIMIT 5
""", (row["user_id"],)).fetchall()

if pending_invites:
    body_parts += ["", "You have new interview invites:"]
    for inv in pending_invites:
        body_parts.append(f"- {inv['company_name']} — {inv['role_title']} "
                          f"({'Remote' if inv['is_remote'] else inv['role_location']}) "
                          f"— trust {inv['trust_level']}")
    body_parts += ["", "Review them: https://app.emploihq.com/invites"]
```

**New worker `workers/expire_invites.py`** — nightly job:

```python
"""Expire pending interview invites whose expires_at has passed."""
def run(db_path):
    conn = db.connect(db_path, check_same_thread=False)
    cur = conn.execute("""
        UPDATE interview_invites
        SET status = 'expired'
        WHERE status = 'pending' AND expires_at < datetime('now')
    """)
    conn.commit()
    result = {"ok": True, "expired": cur.rowcount}
    db.log_event(conn, "ExpireInvitesRun", result)
    return result
```

Register `POST /admin/run/expire-invites` in `api/main.py`. Add nightly cron in `render.yaml` firing `curl -f` against it.

**`workers/verify_employers.py`** — extend to verify `employers.company_domain` too:

```python
# After the existing block that pulls domains from ingested_jobs,
# also pull from employers:
employer_rows = conn.execute("""
    SELECT DISTINCT company_domain, company_name FROM employers
    WHERE company_domain IS NOT NULL AND warm_intro_by IS NULL
""").fetchall()
# Merge into the same targets list; skip the ATS-host filter (employers should
# never have an ATS host as their domain — but keep the filter defensively).
```

**`workers/match_users.py`** — no change for Phase 2 (candidate-side matching is unchanged).

**`workers/spot_check_sources.py`, `workers/heal_job_sources.py`, `workers/backup_db.py`, `workers/ingest_jobs.py`** — no changes.

### 5.7 Frontend Pages (Next.js `web/`)

**Employer side (new):**

- `web/app/(app)/employer/onboarding/page.tsx` — form: company name (required), company domain (optional, auto-guessed on blur from name). Submits `POST /employer/onboarding`. On success, redirect to `/employer`. If backend returns trust_level='avoid', show clear rejection message with `mailto:hello@emploihq.com`.
- `web/app/(app)/employer/page.tsx` — dashboard: employer identity card (trust badge), roles list (with per-role status + invite counts + accepted count + "unread responses" badge), "Post a role" CTA. If `free_role_used=true`, "Post another role" shows Paystack checkout link inline.
- `web/app/(app)/employer/roles/new/page.tsx` — form: URL input + text area. On paste-URL, live-extract preview showing title/location/remote. Submit calls `POST /employer/roles`. Handles 402 (freemium exhausted) inline. Handles 422 (unsupported URL) by highlighting the text-area with a hint.
- `web/app/(app)/employer/roles/[id]/page.tsx` — role detail: full description (collapsed with expand), shortlist below (candidate cards ranked; each with fit score, headline, skills chips, `Invite` button). Right rail: invited candidates list (with status per invite). "Regenerate shortlist" button with refinement-note textarea.
- `web/app/(app)/employer/roles/[id]/hire/page.tsx` — small confirmation flow: which accepted candidate did you hire? Marks role hired.
- `web/app/(app)/employer/billing/page.tsx` — Paystack checkout redirect wrapper. Uses existing billing flow (`/billing/checkout` pattern).

**Candidate side (new + extended):**

- `web/app/(app)/invites/page.tsx` — tabbed view: Pending / Responded (accepted + declined + expired) / History (hired). Cards show role + employer + trust badge + fit score + invite note (if any) + expires-in countdown. Actions: `Accept`, `Decline` (with optional reason modal).
- `web/app/(app)/invites/[id]/page.tsx` — full detail: expanded role description, full employer trust evidence, invite note, actions.
- `web/app/(app)/settings/page.tsx` (extend existing) — add toggle: "Let verified employers discover my Career Twin". Off by default. Copy makes clear that ONLY verified employers can invite, and the candidate must accept before any contact info is shared.
- `web/app/(app)/dashboard/page.tsx` (extend) — top-of-page card: "You have N pending interview invites". Only rendered when `pending > 0`. Fetches `GET /invites/count`.
- `web/components/RecruiterVisibilityBanner.tsx` — one-time nudge for candidates whose twin is complete but visibility is off. Dismissible.

**Public / landing (new):**

- `landing/employers.html` (or `web/app/employers/page.tsx` — depends on landing/app split): copy focused on "post one role, free, first hire on us." Single CTA: "Post your first role." Links into `/employer/onboarding` behind Google sign-in. Includes 2-3 example candidate cards (redacted, illustrative) so the demo happens in the landing itself.

**Sign-up entry & routing (important — do not skip):**

Two-sided products fail silently when the sign-up flow only serves one side. Both sides need a discoverable entry.

- **Primary `/login`** stays candidate-first. Existing Career Twin copy stays. Add a small link at the bottom of the page: **"Hiring? Post a role →"** linking to `/employers`.
- **`/employers`** landing has its own "Post your first role" CTA. Same Google OAuth flow underneath, but the post-auth redirect differs based on intent.
- **Post-auth redirect logic** (server-side, in the NextAuth callback or `(app)/layout.tsx`):

  ```
  if user has employer_users row       → /employer            (returning employer)
  else if intent=employer OR referrer=/employers  → /employer/onboarding  (new employer)
  else if user has career_twins row    → /dashboard           (returning candidate)
  else                                  → /create-career-twin  (new candidate wizard)
  ```

  Intent is preserved through OAuth by adding `?callbackUrl=/employer/onboarding` (or `?intent=employer`) to the sign-in link on `/employers`.

- **A single Google account CAN be both.** The users table has one row per Google sub; whether they have a `career_twins` row, an `employer_users` row, or both determines what surfaces. Someone who's a job seeker today might hire tomorrow.

- **Workspace switcher (v1 minimal):** if a signed-in user has BOTH a `career_twins` row AND an `employer_users` row, the header shows a small dropdown: "Career Twin ↔ Employer Portal". Rare in v1 (nobody has both yet) but zero cost to allow.

- **Copy discipline on `/login`:** the "Hiring? →" link is small and unobtrusive — the candidate flow is the primary funnel. Do not turn `/login` into a two-column "job seeker vs. employer" chooser; that dilutes both. One primary, one secondary.

### 5.8 Freemium Enforcement

**Rule:** every employer gets one free active role. Second role requires an active paid subscription OR successful pay-per-role transaction.

**Implementation:**

```python
def _employer_can_post_new_role(conn, employer_id: int) -> tuple[bool, str]:
    """Returns (allowed, reason)."""
    role_count = conn.execute(
        "SELECT COUNT(*) FROM employer_roles WHERE employer_id = ?",
        (employer_id,)).fetchone()[0]
    if role_count == 0:
        return (True, "")
    sub = db.get_employer_subscription(conn, employer_id)
    if sub and sub.get("status") == "active" and sub.get("tier") in ("pay_per_role", "unlimited"):
        return (True, "")
    return (False, "Your first hiring experience is free. To post another role, "
                   "upgrade at https://app.emploihq.com/employer/billing")
```

`POST /employer/roles` returns 402 with `detail = reason` when `allowed=False`.

**Anti-abuse:** `employer_roles.invites_sent` denormalized column, hard cap at 30. Enforced in `POST /employer/roles/{id}/invites` — returns 429 with a helpful message when hit.

**Pricing (Paystack plans to create):**

- **Employer Pay-Per-Role** — one-time ₦20,000 per additional role. Charge on `POST /employer/billing/checkout?tier=pay_per_role`; on webhook success, unlock exactly one additional role (increment a counter on the employer or use a `employer_role_credits` table if simpler).
- **Employer Unlimited** — ₦100,000/month subscription. Removes the free-role gate entirely. Standard Paystack subscription with webhook lifecycle mirroring the existing candidate-side billing.

Plan codes go in Render env as `PAYSTACK_EMPLOYER_PAYPERROLE_CODE` and `PAYSTACK_EMPLOYER_UNLIMITED_CODE`. `/admin/diagnostics` already surfaces missing config; extend it to check these too.

### 5.9 Trust Gating

**On `POST /employer/onboarding`:**

Two paths depending on `warm_intro_by`:

**Warm intro (Joy's network):** the employer row was pre-created by `POST /admin/employers` with `warm_intro_by='joy'`. The user's onboarding step is skipped (they arrive directly at `/employer` because the row exists). No verify.py call.

**Cold signup:** user submits company_name (+ optional company_domain override). Auto-guess domain via `_derive_company_domain` if not provided. Run `verify.verify_employer(company_name, domain, email, contact)` — use the user's session email as the contact so red-flag/free-email cap logic applies. Persist `trust_score` and `trust_level`.

Behavior by trust level (from `verify.compute_trust`):

| Trust level | Onboarding | Candidate view | Enforcement |
|---|---|---|---|
| `high` (≥ 75) | Allowed | "Verified Employer" green badge | No restriction |
| `medium` (40-74) | Allowed | "Employer trust: medium" amber badge | No restriction |
| `low` (< 40) | Allowed | "Employer trust: low — verify before responding" red badge | Optional Phase 2.5: invites go to a special "review carefully" section on candidate side |
| `avoid` (< 20 or red flags) | **Blocked**: return 403 with "we couldn't verify this employer. Contact hello@emploihq.com" | N/A | No employer row is created |

**Trust re-check:** if employer's `verified_at` is > 30 days old, `workers/verify_employers.py` re-runs verification on the next scheduled run. Same freshness logic as existing employer_trust_records.

### 5.10 Interview Marketplace State Machine

**States** (`interview_invites.status`):

- `pending` — created by employer, candidate hasn't responded, `expires_at` in future
- `accepted` — candidate accepted; employer contact-unlock happens here
- `declined` — candidate declined; employer sees "declined" but no contact info
- `expired` — 14 days passed with no response; treated like declined for employer
- `hired` — terminal, set when employer POSTs `/hire` referencing this invite

**Transitions:**

```
pending ─────accept──▶  accepted ────hire───▶  hired
   │                        │
   │                        └──(other role invites auto-expired on hire)
   │
   ├────decline──▶ declined
   │
   └────(expires_at reached)──▶  expired  [via nightly expire_invites worker]
```

**Rules:**

- Only `pending` invites can be accepted/declined by the candidate. Attempting to accept/decline any other state returns 409.
- Only `accepted` invites can be hired.
- When a role is marked hired, all sibling `pending` invites for that role are auto-expired (mass-update with reason='role_hired').
- Contact unlock happens ONLY on `accepted`. Employer's GET on candidate contact returns 403 for any other state.
- After accept, the candidate still keeps control: they can decline further contact by declining follow-up invites from the same employer, or (Phase 2.5) block the employer entirely.

**What the employer sees for each state on their role detail page:**

- `pending`: candidate name, headline, fit score, "invited [X days ago], expires in [Y]"
- `accepted`: full unlocked contact view + button to mark hired (if this ends up being the hire)
- `declined`: name, "declined [X days ago], reason: [if provided]"
- `expired`: name, "no response — expired"
- `hired`: same as accepted + "HIRED ✓" badge

### 5.11 Naming

- Employer product name in copy: **Employer Portal**
- Internal shorthand (docs only): **Placement Engine**
- Candidate invite section: **Interview Invites** at `/invites`
- Do NOT use "Recruiter Workspace" anywhere in copy (implies desk-time browsing)

---

## 6. Testing Requirements

Every new endpoint, worker, and core function ships with tests in the same commit. Suites must all print `ALL TESTS PASSED ✅` before push.

**New test files:**

- **`test_employer.py`** — new: employer onboarding (warm-intro + cold + avoid-tier reject), roles CRUD, freemium gate (first role allowed, second 402), shortlist generation + caching, invites cap enforcement, `/hire` state transitions, `clear_user` coverage for employer_users
- **`test_invites.py`** — new: candidate invite listing + counts, accept/decline flow, expiration semantics, hired terminal state, employer contact unlock timing (403 before accept, 200 after), `clear_user` wipes candidate invites

**Existing suites extended:**

- **`test_ingest.py`** — add `extract_job_from_url` cases for each of the 5 supported ATSes (with fake_fetch returning ATS-shaped JSON per host), LinkedIn/Indeed rejection with `unsupported_host` error, unknown host returning None, raw text fallback via `extract_single_job`
- **`test_e2e.py`** — `extract_single_job` primitive: fenced JSON, garbage → None, defensive against injection in JD text
- **`test_notify_worker.py`** — invite-notification path: pending invites for a user appear in the digest, cap at 5, `--dry-run` doesn't send but reports count
- **`test_verify_worker.py`** — extends existing to verify employers.company_domain too (with warm_intro_by='joy' skipped)
- **`test_db.py`** — every new table gets CRUD roundtrip + `clear_user` coverage + isolation-between-users
- **`test_api.py`** — every new endpoint's happy path + auth failure + validation failure + status transitions
- **`test_e2e.py`** — `build_role_shortlist_prompt`: contains role description, contains all candidate summaries, includes refinement_note when provided
- **`test_expire_invites.py`** — new: pending invites past expires_at → expired; non-pending untouched; event logged

**Full-suite green list (target after Phase 2):**

```bash
python3 test_e2e.py && python3 test_verify.py && python3 test_db.py \
  && python3 test_api.py && python3 test_ingest.py \
  && python3 test_billing.py && python3 test_landing.py \
  && python3 test_backup_db.py && python3 test_notify_worker.py \
  && python3 test_verify_worker.py && python3 test_spot_check.py \
  && python3 test_heal_sources.py \
  && python3 test_employer.py && python3 test_invites.py \
  && python3 test_expire_invites.py
```

14 suites when done. All offline (fake models, injected DNS/HTTP, mocked Paystack).

**Anti-flake rules:**

- Never use `time.sleep` in tests except where SQLite datetime resolution requires it (existing test_db.py pattern uses `_t.sleep(1.05)` for last_seen_at bumps — acceptable exception)
- Every test that touches `datetime('now', '-N days')` must set the clock via `conn.execute("UPDATE ... SET created_at = datetime('now', '-14 days')")` instead of waiting
- Every test that touches Paystack goes through the `billing.py` injectable HTTP layer; never `requests.post` directly

---

## 7. What NOT to Build (Anti-Scope)

Explicit "we will not do this in Phase 2" list. Any drift toward these is scope creep.

**Employer product:**

- No search/filter UI on employer side
- No boolean query builder
- No candidate database browse (only shortlist per role)
- No bulk invite (one-click-per-candidate is the pattern)
- No message threads inside Emploi (after accept, use email)
- No calendar integration / interview scheduler
- No AI-generated employer outreach messages
- No skills tests, assessments, or reference checks
- No employer team accounts (v1 = 1 user per employer; teams later)
- No ATS integration (Greenhouse Harvest / Ashby authenticated API / etc — Phase 3+)
- No employer-side analytics dashboard (raw counts are fine for v1)
- No custom application forms — employer sees Emploi's Twin view, that's it
- No salary negotiation tools
- No compliance / EEOC forms

**Candidate product:**

- No "browse employers" page (they see roles via invites, not employer profiles)
- No candidate messaging to employers pre-accept (invites are one-directional)
- No auto-apply feature (deferred to future — see appendix)
- No candidate ratings of employers (defer; adds moderation surface)

**Adjacent products:**

- No agency workspace
- No career advisor workspace
- No white-label recruiter product

**Platform / infra:**

- No new database (SQLite continues; Postgres migration only when multi-instance is forced)
- No new AI provider integration (Gemini + Groq fallback continues)
- No new email provider (Brevo continues)
- No mobile app
- No public API for third-party integrations

---

## 8. Launch Checklist

**Before Meta ads run (candidate side polish):**

- [ ] `career_twins.recruiter_visibility` column exists, defaults 0
- [ ] Settings page has clearly-worded toggle: "Let verified employers discover my Career Twin"
- [ ] Toggle copy explicitly names the accept-before-contact promise
- [ ] Wizard end-to-end takes < 3 minutes on a fresh account (measure with a real tester)
- [ ] Dashboard is genuinely useful on day 1 without any invites (ingested-jobs tailored applications work)
- [ ] `RecruiterVisibilityBanner` shows once for complete-twin users with visibility off, dismissible

**Before first warm-intro employer demo:**

- [ ] 500+ opted-in Career Twins in the pool (query: `SELECT COUNT(*) FROM career_twins WHERE recruiter_visibility = 1`)
- [ ] All Phase 2 endpoints deployed and tested against live Paystack
- [ ] `emploihq.com/employers` landing page live with clear CTA
- [ ] Paystack `PAYSTACK_EMPLOYER_PAYPERROLE_CODE` and `PAYSTACK_EMPLOYER_UNLIMITED_CODE` env vars set on Render
- [ ] Joy has manually created warm-intro employer rows for her first 5 pitch targets via `POST /admin/employers`
- [ ] Email template for invite notifications tested end-to-end against real Brevo (not just mocked)
- [ ] `/admin/diagnostics` reports `ready_for_launch: true`

**Before opening self-serve employer signup:**

- [ ] Trust gating tested on 3+ live employers spanning trust levels (create test employers with known-good, known-bad domains)
- [ ] `POST /employer/roles` and `POST /employer/roles/{id}/invites` in `RATE_LIMITS`
- [ ] `avoid`-tier rejection path tested against a red-flag employer
- [ ] Legal review of the employer landing copy ("post a job for free" — no implied service guarantee)
- [ ] `hello@emploihq.com` inbox has a monitored process for dispute resolution
- [ ] Support docs written: "how the invite process works" (for both employer and candidate)
- [ ] `expire_invites` cron running nightly

---

## 9. Deferred Items (with Revisit Triggers)

Each item was considered and explicitly deferred. Do not build any of these in Phase 2. When the trigger fires, revisit and re-scope.

**Programmatic application submission (auto-apply on candidate side)**
- **Approach:** use Greenhouse Job Board API's `POST /v1/boards/{token}/jobs/{id}`, Workable's `POST /accounts/{sub}/jobs/{shortcode}/candidates`, SmartRecruiters' `POST /postings/{id}/candidates`. Coverage ~50% of ingested pool (Lever + Ashby publicly locked out).
- **Revisit when:** candidate NPS shows "applying is painful" as a top complaint OR paid candidate tier launches and this could be the premium feature.
- **Estimated build:** 3-4 weeks (per-ATS handler + retry logic + explicit per-submission consent UI + legal review).

**Authenticated ATS integration for employer side**
- **Approach:** employer connects their Greenhouse Harvest / Ashby / Workable Backend / Lever Data API via API key. Emploi lists their private jobs; Emploi pushes shortlisted candidates back as applications in their ATS.
- **Revisit when:** ≥ 10 paying employers AND their retention depends on "I don't want to leave my ATS."
- **Estimated build:** 6-8 weeks.

**Agency workspace**
- **Approach:** curated 3-5 agencies with KYC + their client trust-verified through verify.py. Interview marketplace pattern shared with employers.
- **Revisit when:** (a) Phase 2 stalls due to hiring managers not having enough role volume, OR (b) an agency explicitly asks and offers to pay upfront for the first cohort.

**Career Advisor workspace (bootcamps, universities, NGOs)**
- **Approach:** Cohort Dashboard for orgs pushing candidates into Emploi and pulling placement outcomes out. Aligned incentive (they want stats to look good).
- **Revisit when:** candidate CAC exceeds ~₦2000 sustained, OR a bootcamp partner asks (Halo is a distribution one-off; doesn't count).

**Interview scheduling / calendar integration**
- **Revisit when:** ≥ 5 candidates or employers explicitly request it in a support conversation.

**Message threads inside Emploi**
- **Revisit when:** never, unless legally required for audit.

**Bulk invite ("invite these 10 candidates")**
- **Revisit when:** a hiring manager complains they click too many times. Trivial to add later.

**Candidate blocks / employer-side moderation ("this employer is spammy")**
- **Revisit when:** first candidate complaint arrives; add block button + reason field.

**Team accounts (multiple employer_users per employer)**
- **Revisit when:** an employer asks to add a colleague. Small addition.

**Multi-language support (French for Francophone Africa)**
- **Revisit when:** we have real Francophone traffic OR a target market pull.

---

## 10. Open Decisions for Joy

Things the executor must not decide unilaterally. Ask before implementing.

1. **Second-role pricing.** Proposed: ₦20,000 per additional role (pay-per-role) OR ₦100,000/month unlimited. Confirm or amend.
2. **Invite expiration window.** Proposed: 14 days. Confirm.
3. **Anti-abuse invite cap.** Proposed: 30 invites per role, hard 429 above. Confirm.
4. **Trust-level "low" behavior.** Proposed: allow posting with badge warning shown to candidates. Alternative: quarantine invites requiring candidate double-opt-in. Confirm.
5. **Warm-intro employer creation UX.** Proposed for v1: Joy uses `POST /admin/employers` via curl from her laptop (no UI). Alternative: build a tiny admin page. v1 curl is simpler.
6. **Employer subscription: pay-per-role first or subscription first?** Proposed: launch with pay-per-role only (cleaner ask), add unlimited subscription after 5+ paying customers.
7. **`close role` reason capture.** Nudge or forced? Proposed: nudge (optional dropdown "hired externally / not hiring / poor matches / other"), do not force.
8. **Invite email template tone.** Proposed: candidate-perspective ("You have a new interview invite"), warm but not overwrought. Confirm or provide alternate copy.
9. **Candidate `/invites/{id}/accept` returns employer contact email.** Proposed yes — keeps agency in candidate's hands (they can reach out first). Confirm.
10. **"Hiring?" link placement on `/login`.** Proposed: small unobtrusive link at bottom of `/login` page linking to `/employers`. Alternative: no link on `/login` at all — employers only arrive via direct `/employers` URL (via Joy's outreach or Meta ad → landing → `/employers`). Softer for candidate funnel but relies on outreach. Confirm.

---

## 11. Appendix: ATS API Reference

For `core.extract_job_from_url` implementation. All endpoints public, no auth required.

### Greenhouse

- **List all jobs (already used by ingest worker):** `GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true`
- **Single job (new):** `GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs/{id}`
- **EU variant:** replace host with `boards-api.eu.greenhouse.io`
- **URL patterns to recognize:** `boards.greenhouse.io/{token}/jobs/{id}`, `job-boards.greenhouse.io/{token}/jobs/{id}`, `job-boards.eu.greenhouse.io/{token}/jobs/{id}`
- **Response:** JSON with `id, title, content (HTML), location.name, absolute_url, departments[].name`
- **Programmatic apply (Phase 3+):** `POST https://boards-api.greenhouse.io/v1/boards/{token}/jobs/{id}` multipart with resume file. Per-employer toggle.

### Lever

- **List all jobs (already used):** `GET https://api.lever.co/v0/postings/{slug}?mode=json`
- **Single job (new):** `GET https://api.lever.co/v0/postings/{slug}/{postingId}?mode=json`
- **URL pattern:** `jobs.lever.co/{slug}/{postingId}`
- **Response:** JSON with `id, text (title), descriptionPlain, categories.location, categories.team, workplaceType, hostedUrl`
- **Programmatic apply:** no clean public path. Uses hosted apply page.

### Ashby

- **List all jobs (already used):** `GET https://api.ashbyhq.com/posting-public/apiPostings/{org}`
- **Single job (new):** `GET https://api.ashbyhq.com/posting-public/apiPostings/{org}/{jobId}`
- **URL pattern:** `jobs.ashbyhq.com/{org}/{jobId}`
- **Response:** varies between top-level list and `{jobs: [...]}`; support both. Fields: `id, title, descriptionHtml, location, jobUrl, department`
- **Programmatic apply:** requires employer's Ashby API key (authenticated API). Not public.

### Workable

- **List all jobs (already used):** `GET https://apply.workable.com/api/v3/accounts/{subdomain}/jobs?limit=100`
- **Single job (new):** `GET https://apply.workable.com/api/v3/accounts/{subdomain}/jobs/{shortcode}`
- **URL pattern:** `apply.workable.com/{subdomain}/j/{shortcode}`
- **Response:** JSON with `id, shortcode, title, state (only 'published' matters), department, url, application_url, location.location_str, location.workplace_type`
- **Programmatic apply:** `POST https://apply.workable.com/api/v3/accounts/{subdomain}/jobs/{shortcode}/candidates` — public if tenant allows.

### SmartRecruiters

- **List all jobs (already used):** `GET https://api.smartrecruiters.com/v1/companies/{identifier}/postings?limit=100`
- **Single job (new):** `GET https://api.smartrecruiters.com/v1/companies/{identifier}/postings/{postingId}`
- **URL pattern:** `jobs.smartrecruiters.com/{identifier}/{postingId}`
- **Response:** JSON with `id, name (title), location.fullLocation, location.remote, department.label, postingUrl, jobAd.sections.jobDescription.text`
- **Programmatic apply:** `POST https://api.smartrecruiters.com/v1/postings/{postingId}/candidates` — public for most postings.

### Explicit rejection list (return `{"error": "unsupported_host", ...}`)

- Any `linkedin.com` URL
- Any `indeed.com` URL
- Any `workday.com` URL (usually per-tenant like `mycompany.wd1.myworkdayjobs.com`)
- Any `taleo.net` URL

Error message template:
> "{host} doesn't allow us to read their job pages. Two options: (1) paste the JD text directly, or (2) on the {host} page, click 'Apply on Company Site' — if that link goes to Greenhouse/Lever/Ashby/Workable/SmartRecruiters, paste THAT URL instead."

Any other unknown host: return `None`. Caller (`POST /employer/roles`) falls back to text extraction if `jd_text` was also provided; otherwise 422 with "we couldn't extract that URL — paste the JD text directly."

---

## End of Spec

The executor should be able to build Phase 2 top-to-bottom from this document plus the existing codebase (`CLAUDE.md`, `HANDOVER.md`, `SPEC.md`). When in doubt, refer to the "Strategic Decisions Locked" section — those are the guardrails that make the product coherent. Everything else is implementation detail.

Ship in ~7 weeks. Kill any scope that isn't in this document without a fresh Joy decision.
