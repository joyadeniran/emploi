"""Emploi persistence — SQLite storage for Career Twins and the application tracker.

Everything is keyed by user_id (Google `sub` claim) so data is never shared
between users. No Streamlit imports; pure stdlib; testable offline.

Design:
- Career Twin data is a JSON blob: the dict is schema-flexible everywhere else
  in the codebase, so the store must not impose columns on it.
- Applications get real columns for the fields the tracker filters/sorts on
  (company, role, status) plus an `extra` JSON blob for everything else.
"""

import json
import sqlite3
from typing import Optional

_SCHEMA = """
-- Users — one row per authenticated Google account. Written by
-- POST /user/session on every session render (the web tier calls it in
-- (app)/layout.tsx after auth()) — idempotent upsert of last_seen_at
-- plus email/name coming from the NextAuth session. Google IdP is the
-- source of truth for credentials; no password hash lives here.
--
-- Historical note: pre-users-table releases stored the user's email in
-- career_twins.data.email as a JSON field. That's PII in a blob any
-- admin querying twins for prompt QA would see. This table replaces
-- that. `workers/notify_users` reads email from users FIRST and falls
-- back to career_twins.data.email for one release; the blob email will
-- be removed in the next twin write cycle.
CREATE TABLE IF NOT EXISTS users (
    id                     TEXT PRIMARY KEY,   -- Google `sub` claim
    email                  TEXT NOT NULL,
    name                   TEXT,
    email_verified         INTEGER NOT NULL DEFAULT 0,
    notifications_enabled  INTEGER NOT NULL DEFAULT 1,
    created_at             TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen_at           TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

CREATE TABLE IF NOT EXISTS career_twins (
    user_id    TEXT PRIMARY KEY,
    data       TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS applications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT NOT NULL,
    company    TEXT,
    role       TEXT,
    status     TEXT,
    extra      TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_applications_user ON applications(user_id);

-- Job sourcing pool — normalised rows from all ingestion sources.
-- source+source_job_id is the dedup key; title+company+description hash
-- is used when a source lacks stable ids.
CREATE TABLE IF NOT EXISTS ingested_jobs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    source         TEXT NOT NULL,
    source_job_id  TEXT NOT NULL,
    title          TEXT,
    company_name   TEXT,
    description    TEXT,
    location       TEXT,
    is_remote      INTEGER NOT NULL DEFAULT 0,
    salary_text    TEXT,
    apply_url      TEXT,
    category       TEXT,
    -- Guessed employer domain from company_name (workers/ingest_jobs._derive_
    -- company_domain). Populated at ingest so verify_employers can trust an
    -- ATS-hosted apply_url without misattributing greenhouse.io / lever.co /
    -- ashbyhq.com / apply.workable.com / jobs.smartrecruiters.com as the
    -- employer. Nullable — a company name that doesn't slugify safely leaves
    -- it NULL and verify_employers falls back to the old apply_url logic.
    company_domain TEXT,
    fetched_at     TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source, source_job_id)
);
CREATE INDEX IF NOT EXISTS idx_jobs_category ON ingested_jobs(category);
CREATE INDEX IF NOT EXISTS idx_jobs_remote   ON ingested_jobs(is_remote);
CREATE INDEX IF NOT EXISTS idx_jobs_fetched  ON ingested_jobs(fetched_at);

-- Cached employer trust verification results (by domain).
CREATE TABLE IF NOT EXISTS employer_trust_records (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name    TEXT,
    domain          TEXT UNIQUE,
    trust_score     INTEGER,
    trust_level     TEXT,
    signals         TEXT NOT NULL DEFAULT '{}',
    evidence        TEXT NOT NULL DEFAULT '[]',
    community_reports INTEGER NOT NULL DEFAULT 0,
    last_checked_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_trust_domain ON employer_trust_records(domain);

-- Pre-computed matching results per user (populated by the matching worker).
CREATE TABLE IF NOT EXISTS matches (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT NOT NULL,
    job_id     INTEGER NOT NULL REFERENCES ingested_jobs(id),
    fit_score  INTEGER,
    reason     TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_matches_user    ON matches(user_id);
CREATE INDEX IF NOT EXISTS idx_matches_job     ON matches(job_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_matches_unique ON matches(user_id, job_id);

-- Job source registry — seeded from data/job_sources.json; DB is source of truth after.
-- ats: greenhouse | lever | ashby | workday | career_page (future)
-- priority: 10=hourly, 7=every 3h, 5=twice daily, 1=daily
CREATE TABLE IF NOT EXISTS job_sources (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    company     TEXT NOT NULL,
    ats         TEXT NOT NULL,
    token       TEXT NOT NULL,
    priority    INTEGER NOT NULL DEFAULT 5,
    category    TEXT,
    region      TEXT,
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(ats, token)
);
CREATE INDEX IF NOT EXISTS idx_sources_active   ON job_sources(active);
CREATE INDEX IF NOT EXISTS idx_sources_priority ON job_sources(priority);

-- Jobs a user bookmarked from matches/browse (per-user, idempotent save).
CREATE TABLE IF NOT EXISTS saved_jobs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT NOT NULL,
    job_id     INTEGER NOT NULL REFERENCES ingested_jobs(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, job_id)
);
CREATE INDEX IF NOT EXISTS idx_saved_user ON saved_jobs(user_id);

-- Billing: one row per user, defaults to free until Paystack activates one.
CREATE TABLE IF NOT EXISTS subscriptions (
    user_id                   TEXT PRIMARY KEY,
    tier                       TEXT NOT NULL DEFAULT 'free',   -- free | pro | max
    status                     TEXT NOT NULL DEFAULT 'active', -- active | past_due | cancelled
    paystack_customer_code     TEXT,
    paystack_subscription_code TEXT,
    paystack_email             TEXT,
    current_period_end         TEXT,
    created_at                 TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at                 TEXT NOT NULL DEFAULT (datetime('now'))
);

-- One row per successfully completed tailored-application generation —
-- the AI-cost-driving action quotas are actually measured against (not
-- "applications", since the skip-draft/direct-apply path costs nothing).
CREATE TABLE IF NOT EXISTS generation_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_generation_log_user_time ON generation_log(user_id, created_at);

-- ─────────────────────────────────────────────────────────────────────────
-- Employer Portal (Phase 2) — Interview Marketplace + pay-per-unlock billing
-- Decisions locked with Joy 2026-07-16 (see PHASE_2_EMPLOYER_PORTAL.md
-- addendum): role #1 is free (contact revealed on candidate ACCEPT, hard cap
-- 10 invites); roles 2+ are free to post but inviting a candidate requires
-- spending one unlock credit (₦1,000 each, packs of min 5) which reveals
-- contact immediately. No employer subscription at launch.
-- ─────────────────────────────────────────────────────────────────────────

-- One row per registered employer. Trust computed by verify.py at onboarding
-- (spec §5.9 mapping, in code — never by an LLM); admin can vouch afterwards.
CREATE TABLE IF NOT EXISTS employers (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name           TEXT NOT NULL,
    company_domain         TEXT,           -- guessed via _derive_company_domain or user override
    trust_score            INTEGER,        -- from verify.compute_trust; NULL until verified
    trust_level            TEXT,           -- 'high' | 'medium' | 'low' | 'avoid' | NULL
    warm_intro_by          TEXT,           -- set by admin vouch AFTER signup; NULL = cold
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

-- One row per posted role. is_free is set at creation time: the employer's
-- first-ever role gets 1 (accept-gated contact, 10-invite cap); later roles
-- get 0 (unlock-gated invites). Explicit column, never inferred from MIN(id).
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
    is_free                  INTEGER NOT NULL DEFAULT 0,
    invites_sent             INTEGER NOT NULL DEFAULT 0,    -- denormalized abuse counter
    close_reason             TEXT,                    -- optional nudge on close
    created_by_user_id       TEXT NOT NULL,
    last_viewed_at           TEXT,                    -- employer's last open of role detail (unread badge)
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
    notified               INTEGER NOT NULL DEFAULT 0,  -- rode a digest email
    notified_at            TEXT,
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

-- Unlock-credit ledger — the ONLY record of credits. Balance = SUM(delta).
-- 'purchase' rows carry the Paystack reference (UNIQUE so webhook replays
-- can't double-credit); 'unlock' rows are the -1 spends; 'admin_grant' for
-- manual comps. Never a denormalized counter that can drift.
CREATE TABLE IF NOT EXISTS employer_credit_ledger (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    employer_id         INTEGER NOT NULL REFERENCES employers(id),
    delta               INTEGER NOT NULL,             -- +N purchase / -1 unlock
    reason              TEXT NOT NULL,                -- purchase|unlock|admin_grant|refund
    paystack_reference  TEXT UNIQUE,                  -- NULL for non-purchase rows
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_credit_ledger_emp ON employer_credit_ledger(employer_id);

-- One row per paid candidate unlock on a paid role. Contact is revealed by
-- this row's existence (paid roles) or by an ACCEPTED invite (free role).
CREATE TABLE IF NOT EXISTS candidate_unlocks (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    employer_role_id    INTEGER NOT NULL REFERENCES employer_roles(id),
    candidate_user_id   TEXT NOT NULL,
    unlocked_by_user_id TEXT NOT NULL,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(employer_role_id, candidate_user_id)
);
CREATE INDEX IF NOT EXISTS idx_unlocks_role ON candidate_unlocks(employer_role_id);
CREATE INDEX IF NOT EXISTS idx_unlocks_candidate ON candidate_unlocks(candidate_user_id);

-- Structured audit / analytics events (stdout now; queried later).
CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT,
    type       TEXT NOT NULL,
    payload    TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_events_user ON events(user_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);
"""

_APP_COLUMNS = ("company", "role", "status")


def _migrate(conn) -> None:
    """Additive migrations; each statement is safe when run repeatedly."""
    for statement in (
        "ALTER TABLE matches ADD COLUMN notified INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE matches ADD COLUMN notified_at TEXT",
        # Guessed employer domain — see the column comment in ingested_jobs.
        # Existing rows self-heal on the next ingest run since upsert_job
        # overwrites the field. Left NULL for rows the ingest hasn't touched
        # yet, which verify_employers must tolerate.
        "ALTER TABLE ingested_jobs ADD COLUMN company_domain TEXT",
        # Outcome tracking: optional user note + audit timestamp so the notify
        # worker can find applications that are still `applied` with no user
        # update after N days and include a "how did it go?" nudge. Both are
        # nullable — `applied` rows written before this migration correctly
        # show up as "no outcome yet" for the nudge query.
        "ALTER TABLE applications ADD COLUMN outcome_notes TEXT",
        "ALTER TABLE applications ADD COLUMN outcome_updated_at TEXT",
        # Phase 2 (Employer Portal): candidate opt-in for recruiter
        # visibility. Default OFF is a locked product decision — a candidate
        # is invisible to every employer until they flip the Settings toggle.
        "ALTER TABLE career_twins ADD COLUMN recruiter_visibility INTEGER NOT NULL DEFAULT 0",
    ):
        try:
            conn.execute(statement)
        except sqlite3.OperationalError:
            pass

    # One-time correction, not an ALTER. Before domain-control verification
    # existed, a cold signup could reach trust_level 'high' purely from signals
    # about a domain it merely TYPED — which rendered a "Verified employer"
    # badge to candidates (see verify.employer_portal_level). Those rows are
    # now unreachable but already stored, and workers/verify_employers skips
    # domains whose trust record is fresh (max_age_days=7), so they would keep
    # the false badge for up to a week. Downgrade them here instead.
    #
    # SELF-DISABLING: the moment the domain_verified column lands (the
    # domain-verification spec), this becomes a no-op — so it can never
    # re-downgrade an employer who has genuinely proven control. Vouched
    # employers are untouched: an admin vouch is real evidence.
    # Probe with a read first: connect() runs on every worker/API start and
    # they share one SQLite file on the Render Disk, so the steady state must
    # not take a write lock it doesn't need.
    employer_cols = {row["name"] for row in conn.execute("PRAGMA table_info(employers)")}
    if employer_cols and "domain_verified" not in employer_cols:
        if conn.execute("SELECT 1 FROM employers WHERE trust_level = 'high' "
                        "AND warm_intro_by IS NULL LIMIT 1").fetchone():
            conn.execute("UPDATE employers SET trust_level = 'medium' "
                         "WHERE trust_level = 'high' AND warm_intro_by IS NULL")
    conn.commit()


def connect(path: str, check_same_thread: bool = True) -> sqlite3.Connection:
    """Open (or create) the database and ensure the schema exists.

    Pass check_same_thread=False when the connection is shared across threads
    (Streamlit runs session code in worker threads and a cached connection
    crosses them; sqlite serializes writes internally).
    """
    # Workers and the API share the Render Disk. Wait briefly for the other
    # writer instead of turning ordinary SQLite serialization into a 500.
    conn = sqlite3.connect(path, check_same_thread=check_same_thread, timeout=30)
    conn.row_factory = sqlite3.Row
    # migrate legacy `profiles` table before schema creation so the
    # CREATE TABLE IF NOT EXISTS career_twins becomes a no-op after the rename
    try:
        conn.execute("ALTER TABLE profiles RENAME TO career_twins")
        conn.commit()
    except Exception:
        pass  # already renamed, or old table never existed
    conn.executescript(_SCHEMA)
    _migrate(conn)
    return conn


# ---------------------------------------------------------------------------
# Users — session-backed identity, source of truth for email + notifications
# ---------------------------------------------------------------------------

def upsert_user(conn, user_id: str, email: str, name: Optional[str] = None,
                email_verified: bool = False) -> None:
    """Idempotent upsert of a user's session-derived identity.

    The web tier calls this on every render of an authenticated route
    (`(app)/layout.tsx`) so `last_seen_at` reflects real activity. Only
    email/name/email_verified are written from the session — notifications_
    enabled and created_at are preserved once set, so a returning user
    keeps their preference.
    """
    if not user_id:
        raise ValueError("user_id required")
    if not email:
        raise ValueError("email required (Google session must carry one)")
    existing = conn.execute("SELECT 1 FROM users WHERE id = ?",
                            (user_id,)).fetchone()
    if existing:
        conn.execute(
            "UPDATE users SET email = ?, name = COALESCE(?, name), "
            "email_verified = ?, last_seen_at = datetime('now') WHERE id = ?",
            (email, name, 1 if email_verified else 0, user_id))
    else:
        conn.execute(
            "INSERT INTO users (id, email, name, email_verified) "
            "VALUES (?, ?, ?, ?)",
            (user_id, email, name, 1 if email_verified else 0))
    conn.commit()


def get_user(conn, user_id: str) -> Optional[dict]:
    """Return the user row or None. Booleans are returned as Python bools."""
    row = conn.execute("SELECT * FROM users WHERE id = ?",
                       (user_id,)).fetchone()
    if not row:
        return None
    out = dict(row)
    out["email_verified"] = bool(out.get("email_verified"))
    out["notifications_enabled"] = bool(out.get("notifications_enabled", 1))
    return out


def set_notifications_enabled(conn, user_id: str, enabled: bool) -> bool:
    """Flip the user's email-digest opt-in. Returns True on success, False
    if the user row doesn't exist (caller should upsert_user first, which
    the /user/session endpoint does on every render)."""
    cur = conn.execute(
        "UPDATE users SET notifications_enabled = ?, last_seen_at = datetime('now') "
        "WHERE id = ?", (1 if enabled else 0, user_id))
    conn.commit()
    return cur.rowcount > 0


def save_career_twin(conn, user_id: str, data: dict) -> None:
    """Upsert the user's Career Twin as a JSON blob."""
    if not isinstance(data, dict):
        raise TypeError("career twin data must be a dict")
    conn.execute(
        "INSERT INTO career_twins (user_id, data, updated_at) "
        "VALUES (?, ?, datetime('now')) "
        "ON CONFLICT(user_id) DO UPDATE SET data=excluded.data, "
        "updated_at=excluded.updated_at",
        (user_id, json.dumps(data)))
    conn.commit()


def load_career_twin(conn, user_id: str) -> dict:
    """Return the user's Career Twin dict, or {} if absent. Never raises."""
    row = conn.execute(
        "SELECT data FROM career_twins WHERE user_id = ?", (user_id,)).fetchone()
    if not row:
        return {}
    try:
        data = json.loads(row["data"])
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Backward-compat aliases — remove once all callers are updated
# ---------------------------------------------------------------------------
def save_profile(conn, user_id: str, profile: dict) -> None:
    save_career_twin(conn, user_id, profile)


def load_profile(conn, user_id: str) -> dict:
    return load_career_twin(conn, user_id)


# ---------------------------------------------------------------------------
# Applications tracker
# ---------------------------------------------------------------------------

def add_application(conn, user_id: str, app: dict) -> int:
    """Insert a tracker entry. Known fields become columns; the rest goes to
    the `extra` JSON blob. Returns the new row id."""
    if not isinstance(app, dict):
        raise TypeError("application must be a dict")
    extra = {k: v for k, v in app.items() if k not in _APP_COLUMNS}
    cur = conn.execute(
        "INSERT INTO applications (user_id, company, role, status, extra) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, app.get("company"), app.get("role"), app.get("status"),
         json.dumps(extra)))
    conn.commit()
    return cur.lastrowid


def list_applications(conn, user_id: str) -> list:
    """All tracker entries for a user, newest first, as flat dicts."""
    rows = conn.execute(
        "SELECT * FROM applications WHERE user_id = ? "
        "ORDER BY id DESC", (user_id,)).fetchall()
    out = []
    for r in rows:
        # Get columns dynamically so migrations that add new columns
        # (outcome_notes / outcome_updated_at) surface in the list without
        # a hand edit here. `extra` JSON still merges last so user-facing
        # keys override any DB-column shadow (backwards compat).
        item = dict(r)
        extra_json = item.pop("extra", None)
        try:
            if extra_json:
                item.update(json.loads(extra_json) or {})
        except Exception:
            pass
        out.append(item)
    return out


def count_applications_this_month(conn, user_id: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM applications WHERE user_id = ? "
        "AND strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')",
        (user_id,)).fetchone()[0]


def update_application_status(conn, app_id: int, status: str,
                              outcome_notes: Optional[str] = None) -> None:
    """Set a new status + audit the outcome update timestamp.

    Any transition off 'applied' counts as an outcome update — it's the
    signal for `list_applications_needing_outcome_nudge` to stop nudging
    the user. `outcome_notes` is optional free-text from the user (e.g.
    "recruiter said Q1"); a None value is preserved so the notes column
    can be cleared by passing empty string separately.
    """
    if outcome_notes is not None:
        conn.execute(
            "UPDATE applications SET status = ?, outcome_notes = ?, "
            "outcome_updated_at = datetime('now') WHERE id = ?",
            (status, outcome_notes, app_id))
    else:
        conn.execute(
            "UPDATE applications SET status = ?, "
            "outcome_updated_at = datetime('now') WHERE id = ?",
            (status, app_id))
    conn.commit()


def list_applications_needing_outcome_nudge(conn, user_id: str,
                                            days: int = 14,
                                            limit: int = 5) -> list:
    """Applications still marked `applied` more than `days` ago that have
    never had an outcome update. Used by the notify worker to add "how did
    it go?" prompts to the digest. Capped so the digest doesn't feel like
    homework (default 5 per user)."""
    rows = conn.execute(
        "SELECT id, company, role, created_at FROM applications "
        "WHERE user_id = ? "
        "AND status = 'applied' "
        "AND outcome_updated_at IS NULL "
        "AND created_at <= datetime('now', ? || ' days') "
        "ORDER BY created_at ASC LIMIT ?",
        (user_id, f"-{int(days)}", int(limit))).fetchall()
    return [dict(r) for r in rows]


def clear_user(conn, user_id: str) -> None:
    """Delete everything stored for one user (right under NDPA/GDPR)."""
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.execute("DELETE FROM career_twins WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM applications WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM matches WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM saved_jobs WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM subscriptions WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM generation_log WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM events WHERE user_id = ?", (user_id,))
    # Phase 2 — candidate-side employer-portal rows are personal data:
    conn.execute("DELETE FROM interview_invites WHERE candidate_user_id = ?", (user_id,))
    conn.execute("DELETE FROM role_shortlists WHERE candidate_user_id = ?", (user_id,))
    conn.execute("DELETE FROM candidate_unlocks WHERE candidate_user_id = ?", (user_id,))
    # Employer-side membership: close their employer's open roles, then drop
    # the membership row. The employers row itself stays (audit; an orphaned
    # employer has no active user who can access it). Credits are NOT
    # refunded on account deletion — documented in the terms.
    conn.execute(
        "UPDATE employer_roles SET status = 'closed', closed_at = datetime('now') "
        "WHERE employer_id IN (SELECT employer_id FROM employer_users WHERE user_id = ?) "
        "  AND status = 'open'", (user_id,))
    conn.execute("DELETE FROM employer_users WHERE user_id = ?", (user_id,))
    conn.commit()


# ---------------------------------------------------------------------------
# Billing — subscription state + generation quota usage
# ---------------------------------------------------------------------------

def get_subscription(conn, user_id: str) -> dict:
    """A user's billing state. Every user is implicitly 'free' until a row
    exists — never fabricate a paid tier for a user we've never billed."""
    row = conn.execute("SELECT * FROM subscriptions WHERE user_id = ?",
                       (user_id,)).fetchone()
    if row:
        return dict(row)
    return {"user_id": user_id, "tier": "free", "status": "active",
           "paystack_customer_code": None, "paystack_subscription_code": None,
           "paystack_email": None, "current_period_end": None}


def upsert_subscription(conn, user_id: str, **fields) -> None:
    """Create or update a user's billing row. Only known columns are
    written; unspecified fields keep their existing value."""
    existing = conn.execute("SELECT 1 FROM subscriptions WHERE user_id = ?",
                            (user_id,)).fetchone()
    allowed = {"tier", "status", "paystack_customer_code",
              "paystack_subscription_code", "paystack_email",
              "current_period_end"}
    fields = {k: v for k, v in fields.items() if k in allowed}
    if existing:
        if fields:
            sets = ", ".join(f"{k} = ?" for k in fields)
            conn.execute(
                f"UPDATE subscriptions SET {sets}, updated_at = datetime('now') "
                f"WHERE user_id = ?", (*fields.values(), user_id))
    else:
        cols = ["user_id"] + list(fields.keys())
        placeholders = ", ".join(["?"] * len(cols))
        conn.execute(
            f"INSERT INTO subscriptions ({', '.join(cols)}) VALUES ({placeholders})",
            (user_id, *fields.values()))
    conn.commit()


def log_generation(conn, user_id: str) -> None:
    """Record one completed tailored-application generation against the
    user's monthly quota. Called only on a SUCCESSFUL job — a failed or
    aborted generation must never count against the user."""
    conn.execute("INSERT INTO generation_log (user_id) VALUES (?)", (user_id,))
    conn.commit()


def count_generations_this_month(conn, user_id: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM generation_log WHERE user_id = ? "
        "AND strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')",
        (user_id,)).fetchone()
    return row["n"] if row else 0


# ---------------------------------------------------------------------------
# Saved jobs — per-user bookmarks over ingested_jobs
# ---------------------------------------------------------------------------

def save_job(conn, user_id: str, job_id: int) -> bool:
    """Bookmark a job for a user. Idempotent. Returns False when the job
    doesn't exist (never creates a dangling bookmark)."""
    exists = conn.execute("SELECT 1 FROM ingested_jobs WHERE id = ?",
                          (job_id,)).fetchone()
    if not exists:
        return False
    conn.execute("INSERT OR IGNORE INTO saved_jobs (user_id, job_id) VALUES (?, ?)",
                 (user_id, job_id))
    conn.commit()
    return True


def unsave_job(conn, user_id: str, job_id: int) -> bool:
    """Remove a bookmark. Returns True if one existed."""
    cur = conn.execute("DELETE FROM saved_jobs WHERE user_id = ? AND job_id = ?",
                       (user_id, job_id))
    conn.commit()
    return cur.rowcount > 0


def list_saved_jobs(conn, user_id: str, *, limit: int = 100) -> list:
    """A user's saved jobs, newest bookmark first, with job detail joined."""
    rows = conn.execute(
        "SELECT s.created_at AS saved_at, j.* "
        "FROM saved_jobs s JOIN ingested_jobs j ON s.job_id = j.id "
        "WHERE s.user_id = ? ORDER BY s.id DESC LIMIT ?",
        (user_id, limit)).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Job sourcing — ingested_jobs
# ---------------------------------------------------------------------------

def upsert_job(conn, source: str, source_job_id: str, fields: dict) -> int:
    """Insert or replace a job row. Returns the row id (new or existing)."""
    allowed = {"title", "company_name", "description", "location",
               "is_remote", "salary_text", "apply_url", "category",
               "company_domain"}
    data = {k: v for k, v in fields.items() if k in allowed}
    cur = conn.execute(
        "INSERT INTO ingested_jobs "
        "(source, source_job_id, title, company_name, description, location, "
        " is_remote, salary_text, apply_url, category, company_domain, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now')) "
        "ON CONFLICT(source, source_job_id) DO UPDATE SET "
        "  title=excluded.title, company_name=excluded.company_name, "
        "  description=excluded.description, location=excluded.location, "
        "  is_remote=excluded.is_remote, salary_text=excluded.salary_text, "
        "  apply_url=excluded.apply_url, category=excluded.category, "
        "  company_domain=excluded.company_domain, "
        "  fetched_at=excluded.fetched_at",
        (source, source_job_id,
         data.get("title"), data.get("company_name"), data.get("description"),
         data.get("location"), int(bool(data.get("is_remote"))),
         data.get("salary_text"), data.get("apply_url"), data.get("category"),
         data.get("company_domain")))
    conn.commit()
    if cur.lastrowid:
        return cur.lastrowid
    row = conn.execute(
        "SELECT id FROM ingested_jobs WHERE source=? AND source_job_id=?",
        (source, source_job_id)).fetchone()
    return row["id"] if row else -1


def _job_filters(remote_only: bool, category: Optional[str], q: Optional[str]):
    clauses, params = [], []
    if remote_only:
        clauses.append("is_remote = 1")
    if category:
        clauses.append("category = ?")
        params.append(category)
    if q:
        # Escape LIKE wildcards so a user typing "%" doesn't match everything.
        needle = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        clauses.append("(title LIKE ? ESCAPE '\\' OR company_name LIKE ? ESCAPE '\\' "
                       "OR description LIKE ? ESCAPE '\\')")
        params.extend([f"%{needle}%"] * 3)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


def list_jobs(conn, *, remote_only: bool = False, category: Optional[str] = None,
              q: Optional[str] = None, limit: int = 100, offset: int = 0) -> list:
    """Return ingested jobs, newest first. Filters (including free-text `q`
    over title/company/description) are optional."""
    where, params = _job_filters(remote_only, category, q)
    rows = conn.execute(
        f"SELECT * FROM ingested_jobs {where} "
        f"ORDER BY fetched_at DESC LIMIT ? OFFSET ?",
        (*params, limit, offset)).fetchall()
    return [dict(r) for r in rows]


def count_jobs(conn, *, remote_only: bool = False,
               category: Optional[str] = None, q: Optional[str] = None) -> int:
    where, params = _job_filters(remote_only, category, q)
    row = conn.execute(f"SELECT COUNT(*) AS n FROM ingested_jobs {where}",
                       params).fetchone()
    return row["n"] if row else 0


# ---------------------------------------------------------------------------
# Employer trust cache — employer_trust_records
# ---------------------------------------------------------------------------

def upsert_trust_record(conn, domain: str, company_name: str,
                        result: dict) -> None:
    """Persist a verify_employer() result keyed by domain."""
    conn.execute(
        "INSERT INTO employer_trust_records "
        "(domain, company_name, trust_score, trust_level, signals, evidence, last_checked_at) "
        "VALUES (?, ?, ?, ?, ?, ?, datetime('now')) "
        "ON CONFLICT(domain) DO UPDATE SET "
        "  company_name=excluded.company_name, "
        "  trust_score=excluded.trust_score, "
        "  trust_level=excluded.trust_level, "
        "  signals=excluded.signals, "
        "  evidence=excluded.evidence, "
        "  last_checked_at=excluded.last_checked_at",
        (domain, company_name,
         result.get("score"), result.get("level"),
         json.dumps(result.get("signals", {})),
         json.dumps(result.get("evidence", []))))
    conn.commit()


def get_trust_record(conn, domain: str) -> Optional[dict]:
    """Return a cached trust record or None."""
    row = conn.execute(
        "SELECT * FROM employer_trust_records WHERE domain = ?",
        (domain,)).fetchone()
    if not row:
        return None
    r = dict(row)
    try:
        r["signals"] = json.loads(r["signals"])
    except Exception:
        r["signals"] = {}
    try:
        r["evidence"] = json.loads(r["evidence"])
    except Exception:
        r["evidence"] = []
    return r


# ---------------------------------------------------------------------------
# Matches — pre-computed per-user fit rankings
# ---------------------------------------------------------------------------

def upsert_match(conn, user_id: str, job_id: int,
                 fit_score: int, reason: str = "") -> None:
    """Insert or update a match row for a user+job pair."""
    conn.execute(
        "INSERT INTO matches (user_id, job_id, fit_score, reason, created_at) "
        "VALUES (?, ?, ?, ?, datetime('now')) "
        "ON CONFLICT(user_id, job_id) DO UPDATE SET "
        "  fit_score=excluded.fit_score, reason=excluded.reason, "
        "  created_at=excluded.created_at",
        (user_id, job_id, fit_score, reason))
    conn.commit()


def list_matches(conn, user_id: str, *, limit: int = 20, offset: int = 0) -> list:
    """Return a user's matches, best fit first, with job detail joined."""
    rows = conn.execute(
        "SELECT m.id, m.fit_score, m.reason, m.created_at, "
        "       j.id AS job_id, j.title, j.company_name, j.description, j.location, "
        "       j.is_remote, j.salary_text, j.apply_url, j.category, "
        "       j.source "
        "FROM matches m JOIN ingested_jobs j ON m.job_id = j.id "
        "WHERE m.user_id = ? ORDER BY m.fit_score DESC LIMIT ? OFFSET ?",
        (user_id, limit, offset)).fetchall()
    return [dict(r) for r in rows]


def count_matches(conn, user_id: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM matches m JOIN ingested_jobs j ON m.job_id = j.id WHERE m.user_id = ?",
        (user_id,)).fetchone()[0]


# ---------------------------------------------------------------------------
# Employer Portal (Phase 2) — employers, roles, invites, shortlists, credits
# ---------------------------------------------------------------------------

def create_employer(conn, company_name: str, company_domain: Optional[str],
                    created_by_user_id: str, trust_score: Optional[int] = None,
                    trust_level: Optional[str] = None) -> int:
    """Create an employer plus the creating user's owner membership row.
    Returns the employer id. Caller must have verified the user has no
    existing membership (get_employer_for_user) — v1 is one employer/user."""
    cur = conn.execute(
        "INSERT INTO employers (company_name, company_domain, trust_score, "
        "trust_level, verified_at) VALUES (?, ?, ?, ?, "
        "CASE WHEN ? IS NULL THEN NULL ELSE datetime('now') END)",
        (company_name, company_domain, trust_score, trust_level, trust_score))
    employer_id = cur.lastrowid
    conn.execute(
        "INSERT INTO employer_users (user_id, employer_id, role) VALUES (?, ?, 'owner')",
        (created_by_user_id, employer_id))
    conn.commit()
    return employer_id


def get_employer(conn, employer_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM employers WHERE id = ?",
                       (employer_id,)).fetchone()
    return dict(row) if row else None


def get_employer_for_user(conn, user_id: str) -> Optional[dict]:
    """The employer a user belongs to (v1: at most one), or None."""
    row = conn.execute(
        "SELECT e.*, eu.role AS membership_role FROM employer_users eu "
        "JOIN employers e ON e.id = eu.employer_id WHERE eu.user_id = ? "
        "ORDER BY eu.id LIMIT 1", (user_id,)).fetchone()
    return dict(row) if row else None


def update_employer(conn, employer_id: int, **fields) -> None:
    """Update employer identity/trust fields. Unknown keys dropped."""
    allowed = {"company_name", "company_domain", "trust_score", "trust_level",
               "verified_at", "warm_intro_by"}
    fields = {k: v for k, v in fields.items() if k in allowed}
    if not fields:
        return
    sets = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(
        f"UPDATE employers SET {sets}, updated_at = datetime('now') WHERE id = ?",
        (*fields.values(), employer_id))
    conn.commit()


def set_employer_trust(conn, employer_id: int, score: Optional[int],
                       level: Optional[str]) -> None:
    conn.execute(
        "UPDATE employers SET trust_score = ?, trust_level = ?, "
        "verified_at = datetime('now'), updated_at = datetime('now') WHERE id = ?",
        (score, level, employer_id))
    conn.commit()


def vouch_employer(conn, employer_id: int, vouched_by: str) -> bool:
    """Admin vouch — marks the employer personally vouched for. Clears any
    trust restriction downstream (the level stays recorded for honesty).
    Returns False when the employer doesn't exist."""
    cur = conn.execute(
        "UPDATE employers SET warm_intro_by = ?, updated_at = datetime('now') "
        "WHERE id = ?", (vouched_by, employer_id))
    conn.commit()
    return cur.rowcount > 0


def get_employer_owner_email(conn, employer_id: int) -> Optional[str]:
    """The owner member's email (from users) — returned to a candidate on
    accept so they can reach out first."""
    row = conn.execute(
        "SELECT u.email FROM employer_users eu JOIN users u ON u.id = eu.user_id "
        "WHERE eu.employer_id = ? AND eu.role = 'owner' ORDER BY eu.id LIMIT 1",
        (employer_id,)).fetchone()
    return row["email"] if row else None


# ---- roles ----

_ROLE_FIELDS = {"title", "description", "location", "is_remote", "salary_text",
                "source_url", "source_ats"}


def create_role(conn, employer_id: int, created_by_user_id: str,
                fields: dict) -> dict:
    """Insert a role. The employer's FIRST-ever role is marked is_free=1
    (accept-gated contact, 10-invite hard cap); every later role is
    unlock-gated. Returns {"id", "is_free"}."""
    data = {k: fields.get(k) for k in _ROLE_FIELDS}
    prior = conn.execute(
        "SELECT COUNT(*) FROM employer_roles WHERE employer_id = ?",
        (employer_id,)).fetchone()[0]
    is_free = 1 if prior == 0 else 0
    cur = conn.execute(
        "INSERT INTO employer_roles (employer_id, title, description, location, "
        "is_remote, salary_text, source_url, source_ats, is_free, created_by_user_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (employer_id, data.get("title") or "", data.get("description") or "",
         data.get("location"), int(bool(data.get("is_remote"))),
         data.get("salary_text"), data.get("source_url"), data.get("source_ats"),
         is_free, created_by_user_id))
    conn.commit()
    return {"id": cur.lastrowid, "is_free": bool(is_free)}


def get_role(conn, role_id: int, employer_id: Optional[int] = None) -> Optional[dict]:
    """Fetch a role; when employer_id is given the row must belong to that
    employer (ownership check for the API — 404 otherwise)."""
    if employer_id is None:
        row = conn.execute("SELECT * FROM employer_roles WHERE id = ?",
                           (role_id,)).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM employer_roles WHERE id = ? AND employer_id = ?",
            (role_id, employer_id)).fetchone()
    return dict(row) if row else None


def list_roles(conn, employer_id: int, status: Optional[str] = None) -> list:
    """An employer's roles, newest first, with response counts. unread_responses
    counts accepts/declines newer than the role's last_viewed_at."""
    clauses, params = ["r.employer_id = ?"], [employer_id]
    if status:
        clauses.append("r.status = ?")
        params.append(status)
    rows = conn.execute(
        "SELECT r.*, "
        " (SELECT COUNT(*) FROM interview_invites i WHERE i.employer_role_id = r.id "
        "   AND i.status IN ('accepted','hired')) AS accepted_count, "
        " (SELECT COUNT(*) FROM interview_invites i WHERE i.employer_role_id = r.id "
        "   AND i.responded_at IS NOT NULL "
        "   AND (r.last_viewed_at IS NULL OR i.responded_at > r.last_viewed_at)) "
        "   AS unread_responses "
        f"FROM employer_roles r WHERE {' AND '.join(clauses)} "
        "ORDER BY r.id DESC", params).fetchall()
    return [dict(r) for r in rows]


def update_role(conn, role_id: int, **fields) -> None:
    allowed = {"title", "description", "location", "is_remote", "salary_text"}
    fields = {k: v for k, v in fields.items() if k in allowed}
    if not fields:
        return
    if "is_remote" in fields:
        fields["is_remote"] = int(bool(fields["is_remote"]))
    sets = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE employer_roles SET {sets} WHERE id = ?",
                 (*fields.values(), role_id))
    conn.commit()


def touch_role_viewed(conn, role_id: int) -> None:
    conn.execute("UPDATE employer_roles SET last_viewed_at = datetime('now') "
                 "WHERE id = ?", (role_id,))
    conn.commit()


def close_role(conn, role_id: int, reason: Optional[str] = None) -> int:
    """Close a role; auto-expire its pending invites. Returns expired count."""
    conn.execute(
        "UPDATE employer_roles SET status = 'closed', closed_at = datetime('now'), "
        "close_reason = ? WHERE id = ?", (reason, role_id))
    cur = conn.execute(
        "UPDATE interview_invites SET status = 'expired' "
        "WHERE employer_role_id = ? AND status = 'pending'", (role_id,))
    conn.commit()
    return cur.rowcount


def hire_candidate(conn, role_id: int, invite_id: int) -> dict:
    """Terminal hire transition. The invite must belong to the role and be
    'accepted'. Marks role hired, invite hired, auto-expires sibling pending
    invites. Returns {"ok": bool, "error": str|None, "expired_others": int}."""
    invite = conn.execute(
        "SELECT * FROM interview_invites WHERE id = ? AND employer_role_id = ?",
        (invite_id, role_id)).fetchone()
    if not invite:
        return {"ok": False, "error": "not_found", "expired_others": 0}
    if invite["status"] != "accepted":
        return {"ok": False, "error": "not_accepted", "expired_others": 0}
    conn.execute(
        "UPDATE employer_roles SET status = 'hired', hired_at = datetime('now'), "
        "hired_candidate_user_id = ? WHERE id = ?",
        (invite["candidate_user_id"], role_id))
    conn.execute("UPDATE interview_invites SET status = 'hired' WHERE id = ?",
                 (invite_id,))
    cur = conn.execute(
        "UPDATE interview_invites SET status = 'expired' "
        "WHERE employer_role_id = ? AND status = 'pending' AND id != ?",
        (role_id, invite_id))
    conn.commit()
    return {"ok": True, "error": None, "expired_others": cur.rowcount}


# ---- shortlists ----

def replace_shortlist(conn, role_id: int, rows: list) -> int:
    """Replace the cached shortlist for a role. rows: [{candidate_user_id,
    fit_score, reason}]. Returns rows written."""
    conn.execute("DELETE FROM role_shortlists WHERE employer_role_id = ?",
                 (role_id,))
    written = 0
    for r in rows:
        if not r.get("candidate_user_id"):
            continue
        conn.execute(
            "INSERT OR IGNORE INTO role_shortlists "
            "(employer_role_id, candidate_user_id, fit_score, reason) "
            "VALUES (?, ?, ?, ?)",
            (role_id, r["candidate_user_id"], r.get("fit_score"),
             r.get("reason", "")))
        written += 1
    conn.commit()
    return written


def list_shortlist(conn, role_id: int, *, limit: int = 20,
                   offset: int = 0) -> list:
    """Cached shortlist rows joined with twin data, best fit first. Only
    candidates who are STILL opted in (recruiter_visibility=1) are returned —
    an opt-out after caching must hide them immediately. Each row carries
    already_invited / unlocked flags."""
    rows = conn.execute(
        "SELECT s.candidate_user_id, s.fit_score, s.reason, s.created_at, "
        "       ct.data AS twin_data, "
        "       EXISTS(SELECT 1 FROM interview_invites i "
        "              WHERE i.employer_role_id = s.employer_role_id "
        "                AND i.candidate_user_id = s.candidate_user_id) AS already_invited, "
        "       EXISTS(SELECT 1 FROM candidate_unlocks cu "
        "              WHERE cu.employer_role_id = s.employer_role_id "
        "                AND cu.candidate_user_id = s.candidate_user_id) AS unlocked "
        "FROM role_shortlists s "
        "JOIN career_twins ct ON ct.user_id = s.candidate_user_id "
        "WHERE s.employer_role_id = ? AND ct.recruiter_visibility = 1 "
        "ORDER BY s.fit_score DESC LIMIT ? OFFSET ?",
        (role_id, limit, offset)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["twin"] = json.loads(d.pop("twin_data") or "{}")
        except Exception:
            d["twin"] = {}
        d["already_invited"] = bool(d["already_invited"])
        d["unlocked"] = bool(d["unlocked"])
        out.append(d)
    return out


def count_shortlist(conn, role_id: int) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM role_shortlists s "
        "JOIN career_twins ct ON ct.user_id = s.candidate_user_id "
        "WHERE s.employer_role_id = ? AND ct.recruiter_visibility = 1",
        (role_id,)).fetchone()[0]


def clear_shortlist(conn, role_id: int) -> None:
    conn.execute("DELETE FROM role_shortlists WHERE employer_role_id = ?",
                 (role_id,))
    conn.commit()


def shortlist_cache_age_seconds(conn, role_id: int) -> Optional[int]:
    row = conn.execute(
        "SELECT CAST((julianday('now') - julianday(MAX(created_at))) * 86400 AS INTEGER) "
        "FROM role_shortlists WHERE employer_role_id = ?", (role_id,)).fetchone()
    return row[0] if row and row[0] is not None else None


# ---- interview invites ----

def create_invite(conn, role_id: int, candidate_user_id: str,
                  invited_by_user_id: str, fit_score: Optional[int] = None,
                  invite_note: Optional[str] = None,
                  expires_days: int = 14) -> Optional[int]:
    """Create a pending invite and bump the role's invites_sent counter.
    Returns the invite id, or None when an invite already exists for this
    (role, candidate) pair."""
    existing = conn.execute(
        "SELECT 1 FROM interview_invites WHERE employer_role_id = ? "
        "AND candidate_user_id = ?", (role_id, candidate_user_id)).fetchone()
    if existing:
        return None
    cur = conn.execute(
        "INSERT INTO interview_invites (employer_role_id, candidate_user_id, "
        "invited_by_user_id, fit_score, invite_note, expires_at) "
        "VALUES (?, ?, ?, ?, ?, datetime('now', ? || ' days'))",
        (role_id, candidate_user_id, invited_by_user_id, fit_score,
         invite_note, f"+{int(expires_days)}"))
    conn.execute(
        "UPDATE employer_roles SET invites_sent = invites_sent + 1 WHERE id = ?",
        (role_id,))
    conn.commit()
    return cur.lastrowid


def get_invite(conn, invite_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM interview_invites WHERE id = ?",
                       (invite_id,)).fetchone()
    return dict(row) if row else None


def get_invite_detail(conn, invite_id: int) -> Optional[dict]:
    """Invite joined with role + employer (for both candidate and employer
    views). Caller enforces who may see it."""
    row = conn.execute(
        "SELECT i.*, r.title AS role_title, r.description AS role_description, "
        "       r.location AS role_location, r.is_remote AS role_is_remote, "
        "       r.salary_text AS role_salary_text, r.is_free AS role_is_free, "
        "       r.employer_id, e.company_name, e.company_domain, "
        "       e.trust_score, e.trust_level, e.warm_intro_by, e.verified_at "
        "FROM interview_invites i "
        "JOIN employer_roles r ON r.id = i.employer_role_id "
        "JOIN employers e ON e.id = r.employer_id "
        "WHERE i.id = ?", (invite_id,)).fetchone()
    return dict(row) if row else None


def list_candidate_invites(conn, candidate_user_id: str,
                           status: Optional[str] = None) -> list:
    clauses, params = ["i.candidate_user_id = ?"], [candidate_user_id]
    if status and status != "all":
        clauses.append("i.status = ?")
        params.append(status)
    rows = conn.execute(
        "SELECT i.*, r.title AS role_title, r.description AS role_description, "
        "       r.location AS role_location, r.is_remote AS role_is_remote, "
        "       r.salary_text AS role_salary_text, "
        "       e.company_name, e.trust_score, e.trust_level, e.warm_intro_by, "
        "       e.verified_at "
        "FROM interview_invites i "
        "JOIN employer_roles r ON r.id = i.employer_role_id "
        "JOIN employers e ON e.id = r.employer_id "
        f"WHERE {' AND '.join(clauses)} ORDER BY i.id DESC", params).fetchall()
    return [dict(r) for r in rows]


def count_candidate_invites(conn, candidate_user_id: str) -> dict:
    row = conn.execute(
        "SELECT COUNT(*) AS total, "
        "SUM(CASE WHEN status = 'pending' AND expires_at > datetime('now') "
        "THEN 1 ELSE 0 END) AS pending "
        "FROM interview_invites WHERE candidate_user_id = ?",
        (candidate_user_id,)).fetchone()
    return {"pending": row["pending"] or 0, "all": row["total"] or 0}


def list_role_invites(conn, role_id: int) -> list:
    """All invites for a role (employer's right-rail view), newest first,
    with the candidate's twin data joined for name/headline rendering."""
    rows = conn.execute(
        "SELECT i.*, ct.data AS twin_data FROM interview_invites i "
        "LEFT JOIN career_twins ct ON ct.user_id = i.candidate_user_id "
        "WHERE i.employer_role_id = ? ORDER BY i.id DESC", (role_id,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["twin"] = json.loads(d.pop("twin_data") or "{}")
        except Exception:
            d["twin"] = {}
        out.append(d)
    return out


def respond_invite(conn, invite_id: int, accept: bool,
                   decline_reason: Optional[str] = None) -> str:
    """Candidate response. Only 'pending' invites transition; accepting an
    invite past expires_at returns 'expired' (and marks it so). Returns
    'ok' | 'not_pending' | 'expired'."""
    invite = get_invite(conn, invite_id)
    if not invite or invite["status"] != "pending":
        return "not_pending"
    expired = conn.execute(
        "SELECT datetime(?) <= datetime('now')", (invite["expires_at"],)).fetchone()[0]
    if expired:
        conn.execute("UPDATE interview_invites SET status = 'expired' WHERE id = ?",
                     (invite_id,))
        conn.commit()
        return "expired"
    conn.execute(
        "UPDATE interview_invites SET status = ?, responded_at = datetime('now'), "
        "decline_reason = ? WHERE id = ?",
        ("accepted" if accept else "declined",
         None if accept else decline_reason, invite_id))
    conn.commit()
    return "ok"


# ---- unlock credits (pay-per-unlock billing) ----

def add_credits(conn, employer_id: int, delta: int, reason: str,
                paystack_reference: Optional[str] = None) -> bool:
    """Append a ledger row. Returns False when the Paystack reference was
    already credited (webhook replay) — never double-credits."""
    try:
        conn.execute(
            "INSERT INTO employer_credit_ledger (employer_id, delta, reason, "
            "paystack_reference) VALUES (?, ?, ?, ?)",
            (employer_id, delta, reason, paystack_reference))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def credit_balance(conn, employer_id: int) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(delta), 0) FROM employer_credit_ledger "
        "WHERE employer_id = ?", (employer_id,)).fetchone()
    return int(row[0])


def create_unlock(conn, role_id: int, employer_id: int,
                  candidate_user_id: str, unlocked_by_user_id: str) -> str:
    """Spend one credit to unlock a candidate on a paid role. Atomic within
    this connection. Returns 'ok' | 'exists' | 'no_credits'."""
    existing = conn.execute(
        "SELECT 1 FROM candidate_unlocks WHERE employer_role_id = ? "
        "AND candidate_user_id = ?", (role_id, candidate_user_id)).fetchone()
    if existing:
        return "exists"
    if credit_balance(conn, employer_id) < 1:
        return "no_credits"
    conn.execute(
        "INSERT INTO candidate_unlocks (employer_role_id, candidate_user_id, "
        "unlocked_by_user_id) VALUES (?, ?, ?)",
        (role_id, candidate_user_id, unlocked_by_user_id))
    conn.execute(
        "INSERT INTO employer_credit_ledger (employer_id, delta, reason) "
        "VALUES (?, -1, 'unlock')", (employer_id,))
    conn.commit()
    return "ok"


def is_unlocked(conn, role_id: int, candidate_user_id: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM candidate_unlocks WHERE employer_role_id = ? "
        "AND candidate_user_id = ?", (role_id, candidate_user_id)).fetchone() is not None


# ---- recruiter visibility (candidate opt-in) ----

def set_recruiter_visibility(conn, user_id: str, enabled: bool) -> bool:
    """Flip the candidate's opt-in. Returns False when no twin row exists
    (nothing to make discoverable)."""
    cur = conn.execute(
        "UPDATE career_twins SET recruiter_visibility = ? WHERE user_id = ?",
        (1 if enabled else 0, user_id))
    conn.commit()
    return cur.rowcount > 0


def get_recruiter_visibility(conn, user_id: str) -> bool:
    row = conn.execute(
        "SELECT recruiter_visibility FROM career_twins WHERE user_id = ?",
        (user_id,)).fetchone()
    return bool(row["recruiter_visibility"]) if row else False


def list_visible_twins(conn, *, limit: int = 500) -> list:
    """Opted-in candidates for shortlist generation: [{user_id, twin}]."""
    rows = conn.execute(
        "SELECT user_id, data FROM career_twins "
        "WHERE recruiter_visibility = 1 LIMIT ?", (limit,)).fetchall()
    out = []
    for r in rows:
        try:
            twin = json.loads(r["data"])
        except Exception:
            twin = {}
        if isinstance(twin, dict):
            out.append({"user_id": r["user_id"], "twin": twin})
    return out


# ---------------------------------------------------------------------------
# Events — structured audit log
# ---------------------------------------------------------------------------

def log_event(conn, event_type: str, payload: dict,
              user_id: Optional[str] = None) -> None:
    """Append a structured event. Never raises — logging must not break callers."""
    try:
        conn.execute(
            "INSERT INTO events (user_id, type, payload) VALUES (?, ?, ?)",
            (user_id, event_type, json.dumps(payload)))
        conn.commit()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Job source registry — job_sources table
# ---------------------------------------------------------------------------

def seed_job_sources(conn, sources_path: str) -> int:
    """Seed the job_sources table from a JSON file if the table is empty.

    Returns the number of rows inserted (0 if already seeded or file missing).
    The DB is the source of truth after first seed — the file is not re-read.
    """
    existing = conn.execute("SELECT COUNT(*) AS n FROM job_sources").fetchone()["n"]
    if existing > 0:
        return 0
    try:
        data = json.loads(open(sources_path).read())
    except Exception:
        return 0
    inserted = 0
    for category, entries in data.items():
        if category.startswith("_"):
            continue
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get("token"):
                continue
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO job_sources "
                    "(company, ats, token, priority, category, region, active) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (entry.get("company", ""),
                     entry.get("ats", "greenhouse"),
                     entry["token"],
                     int(entry.get("priority", 5)),
                     category,
                     entry.get("region", "global"),
                     1 if entry.get("active", True) else 0))
                inserted += 1
            except Exception:
                pass
    conn.commit()
    return inserted


def list_job_sources(conn, *, active_only: bool = False,
                     ats: Optional[str] = None) -> list:
    """Return job source records, highest priority first."""
    clauses, params = [], []
    if active_only:
        clauses.append("active = 1")
    if ats:
        clauses.append("ats = ?")
        params.append(ats)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM job_sources {where} ORDER BY priority DESC, company ASC",
        params).fetchall()
    return [dict(r) for r in rows]


def upsert_job_source(conn, company: str, ats: str, token: str,
                      priority: int = 5, category: Optional[str] = None,
                      region: Optional[str] = None, active: bool = True) -> int:
    """Insert or update a job source record. Returns the row id."""
    cur = conn.execute(
        "INSERT INTO job_sources (company, ats, token, priority, category, region, active, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now')) "
        "ON CONFLICT(ats, token) DO UPDATE SET "
        "  company=excluded.company, priority=excluded.priority, "
        "  category=excluded.category, region=excluded.region, "
        "  active=excluded.active, updated_at=excluded.updated_at",
        (company, ats, token, priority, category, region, 1 if active else 0))
    conn.commit()
    if cur.lastrowid:
        return cur.lastrowid
    row = conn.execute("SELECT id FROM job_sources WHERE ats=? AND token=?",
                       (ats, token)).fetchone()
    return row["id"] if row else -1


def set_job_source_active(conn, source_id: int, active: bool) -> bool:
    """Enable or disable a job source. Returns True if the row existed."""
    cur = conn.execute(
        "UPDATE job_sources SET active=?, updated_at=datetime('now') WHERE id=?",
        (1 if active else 0, source_id))
    conn.commit()
    return cur.rowcount > 0


def get_job_source(conn, source_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM job_sources WHERE id=?",
                       (source_id,)).fetchone()
    return dict(row) if row else None
