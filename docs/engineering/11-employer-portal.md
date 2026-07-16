# 11 — Employer Portal (Phase 2)

Shipped 2026-07-16. Canonical decision record: `PHASE_2_EMPLOYER_PORTAL.md`
(read the addendum at the top — it supersedes parts of the spec body).

## Model in one paragraph

Emploi is a two-sided Interview Marketplace. Candidates opt in to employer
discovery (`career_twins.recruiter_visibility`, default OFF). Employers sign
up cold via Google, get trust-checked at onboarding
(`verify.employer_portal_level`: high ≥75 / medium 40–74 / low <40 badge /
avoid <20-or-red-flags = blocked 403, dead-DNS caps at low), post roles by
pasting an ATS URL (`core.extract_job_from_url`, 5 ATSes) or JD text
(`core.extract_single_job`), and get a cached Gemini-ranked shortlist of
opted-in Career Twins (`core.rank_candidates_for_role`, one model call, cache
in `role_shortlists`). **Role #1 is free**: up to 10 invites
(`core.INVITE_CAP_FREE_ROLE`), contact revealed only when the candidate
ACCEPTS. **Roles 2+**: free to post, but each invite requires unlocking the
candidate — 1 credit = ₦1,000 (`core.UNLOCK_PRICE_NGN`), packs of min 5
(`core.MIN_UNLOCK_PACK`) via one-time Paystack checkout — and an unlock
reveals contact immediately. Joy vouches employers she knows post-signup
(`POST /admin/employers/{id}/vouch`) from the Next.js `/admin` dashboard.

## Load-bearing invariants

1. **Opt-in gates everything.** No `recruiter_visibility=1`, no shortlist
   presence, no invite, no unlock. Opting out hides a candidate from cached
   shortlists immediately (the visibility join happens at read time).
2. **Contact-reveal rule** (`api.main._contact_visible`): free role →
   invite status ∈ {accepted, hired}; paid role → `candidate_unlocks` row
   exists. Employers only ever see `core.format_employer_contact_view` —
   never the raw CV, chat history, or application history.
3. **Credits are a ledger, never a counter.** Balance =
   `SUM(employer_credit_ledger.delta)`. Purchases carry a UNIQUE Paystack
   reference (webhook replays no-op); unlocks are UNIQUE per
   (role, candidate) (no double-spend). Both enforced by the schema.
4. **Trust is computed in code** (`verify.compute_trust` →
   `employer_portal_level`), avoid-tier rows are never created, and the
   candidate-side scoring points/caps are untouched by Phase 2.
5. **Invite state machine**: pending → accepted → hired; pending → declined;
   pending → expired (14 days, nightly `workers/expire_invites.py`; role
   close and hire also auto-expire pending siblings). Only pending invites
   can be responded to; only accepted invites can be hired.
6. **Free-role determination is explicit**: `employer_roles.is_free` is set
   at creation (first-ever role for the employer), never inferred later.

## Endpoints (all thin dispatch)

Employer: `POST /employer/onboarding`, `GET|PATCH /employer`,
`POST|GET /employer/roles`, `GET|PATCH /employer/roles/{id}`,
`POST .../close`, `POST .../hire`, `GET .../shortlist`,
`POST .../shortlist/refresh` (202), `POST .../invites`,
`POST .../unlocks`, `GET|POST /employer/billing/{status,checkout,verify}`.
Candidate: `GET /invites`, `GET /invites/count`, `GET /invites/{id}`,
`POST /invites/{id}/{accept,decline}`,
`GET|PATCH /career-twin/recruiter-visibility`.
Admin (X-API-Key): `GET /admin/metrics`, `POST /admin/employers/{id}/vouch`,
`POST /admin/run/expire-invites`.

## Error contract cheat-sheet

402 = needs unlock credits (invite/unlock on paid role) · 403 = avoid-tier
onboarding block · 404 = not yours / not opted in · 409 = duplicate
invite / not pending / already onboarded / role not open · 410 = invite
expired · 429 = free-role 10-invite cap.

## Tests

`test_employer.py`, `test_invites.py`, `test_expire_invites.py` plus
extensions in db/e2e/ingest/verify/api/notify/verify-worker suites. All
offline. 15 suites total — see CLAUDE.md Commands.
