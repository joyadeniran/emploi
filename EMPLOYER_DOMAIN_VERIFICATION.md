# Spec — Employer domain-control verification

Status: **proposed, not built.** Written 2026-07-17 after the stopgap shipped.
Owner decision needed on §6 before implementation starts.

## 1. Why

`verify.verify_employer` scores a **domain**. Nothing has ever proved the person
who typed that domain has any relationship to it. Demonstrated on the real
scorer:

```
Gmail signup → onboard as "Paystack" / paystack.com
→ verify_employer(paystack.com) → score 90 → level "high"
→ candidates saw: "✅ Verified employer"
```

The badge was the lure for exactly the scam this product exists to prevent, and
the first role is free, so abuse cost nothing.

The root cause is recorded at `api/main.py:1135`: the spec's original free-mail
trust cap was dropped *because* Google-only auth means every employer signs up
with a personal Gmail. That removed the only signal tying a human to a company.

**The gap is proof of affiliation, not credentials.** Passwords would not have
closed it. See the auth analysis in the PR discussion; the summary is that
`users.id` **is** the Google `sub` (`db.py:30`) and is the FK across ~12 tables,
so a second auth method means either duplicate accounts with orphaned Career
Twins, or re-keying every table. Domain verification needs none of that.

## 2. What shipped already (the stopgap)

- `verify.employer_portal_level(..., domain_verified=False)` — **`high` is
  unreachable without proven domain control.** Defaults to safe, so every
  caller (onboarding, the refresh worker) is capped by default. Cold signups
  cap at `medium`; the score is still stored truthfully.
- Admin vouch (`warm_intro_by`) remains the one path to a verified badge, and
  is unaffected.
- One-time backfill in `db._migrate` downgrades pre-existing cold `high` rows
  (`verify_employers` skips fresh domains for 7 days, so they would otherwise
  keep a false badge for a week). **Self-disabling**: it no-ops the moment the
  `domain_verified` column below exists.
- Employer dashboard explains why they aren't verified yet.

**This spec replaces the cap's default with real evidence.**

## 3. Design

After Google sign-in, at (or after) onboarding, the employer proves control of
the claimed domain by receiving a code at an address **at that domain**.

```
onboarding (company_name + company_domain)
  → verify_employer(domain)             # unchanged: is the domain legitimate?
  → avoid → 403, no row                 # unchanged
  → row created, level capped at medium # today's behaviour
  → POST /employer/verify-domain/start  { email: "joy@supplya.shop" }
      - MUST match the employer's company_domain (exact host, case-folded)
      - reject free-mail + disposable domains (gmail/yahoo/outlook/proton…)
      - 6-digit code, single-use, 15-min expiry, hashed at rest
      - sent via Brevo (already wired for digests)
  → POST /employer/verify-domain/confirm { code }
      - on success: employers.domain_verified = 1, domain_verified_at = now
      - re-run employer_portal_level(..., domain_verified=True) → may reach high
```

Why a code to the domain and not DNS TXT: the target employers are African/Asian
SMEs, often without DNS access (`joy@supplya.shop` is likely a hosting-panel
mailbox). Email-to-domain is the lowest-friction proof they can actually
complete. Offer **DNS TXT as a fallback** for employers on domains with no
mailbox (`_emploi-verify.<domain>` = token) — same `domain_verified` outcome.

## 4. Schema

```sql
ALTER TABLE employers ADD COLUMN domain_verified INTEGER NOT NULL DEFAULT 0;
ALTER TABLE employers ADD COLUMN domain_verified_at TEXT;
ALTER TABLE employers ADD COLUMN domain_verified_email TEXT;  -- audit: who proved it

CREATE TABLE IF NOT EXISTS domain_verification_codes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    employer_id  INTEGER NOT NULL REFERENCES employers(id),
    email        TEXT NOT NULL,
    code_hash    TEXT NOT NULL,        -- never store the code itself
    attempts     INTEGER NOT NULL DEFAULT 0,
    consumed_at  TEXT,
    expires_at   TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
```

Adding `domain_verified` **auto-retires the backfill** in `db._migrate` — that
is deliberate. Delete the backfill block in the same PR for clarity.

## 5. Guards (each needs a test)

| Risk | Guard |
|---|---|
| Brute-forcing a 6-digit code | max 5 attempts per code, then invalidate; rate-limit `/verify-domain/*` (5 per hour per user, `RATE_LIMITS` pattern) |
| Free-mail as "proof" | allow-list check: the address host must equal `company_domain`; reject known free-mail/disposable hosts |
| Code interception via replay | single-use (`consumed_at`), 15-min expiry, hashed at rest |
| Claiming a domain another employer already verified | `UNIQUE` on `company_domain WHERE domain_verified = 1`; second claimant → 409 and a support path (teams are a v1.x item) |
| Verified employer later turns malicious | the refresh worker still re-levels; red flags → `avoid` still wins over `domain_verified` |
| Employer changes `company_domain` after verifying | `PATCH /employer` must reset `domain_verified = 0` and re-cap the level (there is already a re-verify-on-domain-change path to hook) |

## 6. Open decisions — **Joy**

1. **How hard does this gate invites?** Options:
   - (a) **Badge-only** (softest): unverified employers still invite; they just
     never show "Verified employer". No conversion hit. Scammer can still
     invite 10 candidates for free — but with an amber "Trust: medium" chip.
   - (b) **Gate the free role** (recommended): unverified employers can post and
     see their shortlist, but **cannot send invites** until verified. Kills the
     free-abuse path, and asks for the effort only when there is obvious value
     (they have a shortlist in hand and want to contact it).
   - (c) **Gate onboarding** (hardest): verify before an employer row exists.
     Maximum safety, worst funnel — they bounce before seeing any value.
2. **Should a `medium` (unverified) employer's invite carry the never-pay-a-fee
   warning?** Today only `low` does. Post-stopgap every cold employer is
   `medium`, so this decides whether ~every invite carries a scam warning.
   Leaning yes until verification exists, then drop it for verified ones.
3. **Do vouched employers skip domain verification?** Leaning yes — the vouch is
   stronger evidence (Joy knows them personally).

## 7. Out of scope

Auth changes. If employer sign-in coverage ever becomes a measured problem, the
answer is magic links (NextAuth Email provider), not passwords — and that needs
the canonical-user-id migration first, which is its own spec. Instrument
`/employer/login` drop-off before deciding anything there.

## 8. Tests to write

- Happy path: start → code → confirm → `domain_verified = 1` → level may reach `high`.
- Address host ≠ `company_domain` → 422; free-mail host → 422.
- Wrong code 5× → invalidated; expired code → 410; reused code → 410.
- Second employer verifying an already-verified domain → 409.
- `PATCH /employer` changing the domain resets `domain_verified` and re-caps.
- Red flags still force `avoid` even when `domain_verified = 1`.
- Candidate-facing: verified employer → `verified: true`; unverified → `false`
  (extends the regression in `test_invites.py`).
