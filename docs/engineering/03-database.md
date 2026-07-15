# 03 — Database

**Current engine:** SQLite via `db.py` (the only file allowed to contain SQL). **Target:** Postgres when multi-instance or file storage demands it — the schema below is written to survive that migration.

## As-built schema (db.py, v0.12+)

Seven tables. Everything user-owned is keyed by `user_id` (Google `sub` claim).

```sql
CREATE TABLE career_twins (              -- renamed from profiles (migration in connect())
    user_id    TEXT PRIMARY KEY,          -- Google `sub` claim (stable), else email
    data       TEXT NOT NULL,             -- Career Twin JSON blob (schema-flexible; includes email)
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE applications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT NOT NULL,
    company    TEXT,
    role       TEXT,
    status     TEXT,                      -- applied|interview|offer|rejected|withdrawn
    extra      TEXT NOT NULL DEFAULT '{}',-- JSON: fit_score, source, next_step...
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_applications_user ON applications(user_id);

-- Normalised job pool written by Worker 1 (ingest_jobs.py).
CREATE TABLE ingested_jobs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source        TEXT NOT NULL,          -- greenhouse | lever | ashby
    source_job_id TEXT NOT NULL,
    title TEXT, company_name TEXT, description TEXT, location TEXT,
    is_remote     INTEGER NOT NULL DEFAULT 0,
    salary_text TEXT, apply_url TEXT, category TEXT,
    fetched_at    TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source, source_job_id)         -- dedup key across repeat runs
);
-- indexes: category, is_remote, fetched_at

-- Cached employer trust results, refreshed by Worker 2 (verify_employers.py).
CREATE TABLE employer_trust_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT,
    domain       TEXT UNIQUE,
    trust_score  INTEGER,                 -- computed in code (verify.py), never by an LLM
    trust_level  TEXT,
    signals      TEXT NOT NULL DEFAULT '{}',
    evidence     TEXT NOT NULL DEFAULT '[]',
    community_reports INTEGER NOT NULL DEFAULT 0,
    last_checked_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Pre-computed rankings written by Worker 3 (match_users.py).
CREATE TABLE matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT NOT NULL,
    job_id     INTEGER NOT NULL REFERENCES ingested_jobs(id),
    fit_score  INTEGER,
    reason     TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    notified    INTEGER NOT NULL DEFAULT 0,  -- additive ALTER migration; Worker 4
    notified_at TEXT
);
CREATE UNIQUE INDEX idx_matches_unique ON matches(user_id, job_id);  -- anti-join idempotency

-- Source registry — seeded once from data/job_sources.json; DB is source of
-- truth after (manage via /admin/job-sources, not the JSON).
CREATE TABLE job_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT NOT NULL,
    ats     TEXT NOT NULL,                -- greenhouse | lever | ashby | career_page (idle)
    token   TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 5,  -- 10=hourly, 7=3h, 5=twice daily, 1=daily
    category TEXT, region TEXT,
    active  INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(ats, token)
);

-- Structured audit / analytics events (worker runs, deletions, ...).
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT, type TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Billing tier per user. No row = free tier (implicit-free pattern).
-- Never fabricate a paid tier; paid status only comes from Paystack webhooks.
CREATE TABLE subscriptions (
    user_id                  TEXT PRIMARY KEY,
    tier                     TEXT NOT NULL DEFAULT 'free',   -- free | pro | max
    status                   TEXT NOT NULL DEFAULT 'active', -- active | past_due | canceled
    paystack_customer_code   TEXT,
    paystack_subscription_code TEXT,
    paystack_email           TEXT,
    current_period_end       TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- One row per successful AI draft completion. Quota metric for billing.
-- Counting successful AI calls (not applications — skip-draft costs nothing).
CREATE TABLE generation_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_generation_log_user_time
    ON generation_log(user_id, created_at);
```

Design choices, deliberate:
- **Career Twin is a JSON blob**, not columns — the extracted shape evolves with the prompt. Only key it by user.
- **`extra` JSON on applications** — known fields are columns (filter/sort), everything else rides along. `list_applications()` flattens extra into the returned dicts.
- **Status set** is enforced at the API layer (`api/main.py StatusIn`), not by a CHECK constraint.
- **Additive migrations only** — new columns arrive via `ALTER TABLE ... ADD COLUMN` guarded in `connect()` (see `notified`); never destructive.
- **`sqlite3.connect(..., timeout=30)`** so API/worker write contention queues instead of erroring.

## Access rules

- Every user query filters by `user_id`. There are no cross-user reads. The PATCH ownership check in `api/main.py` is the pattern: verify `user_id` owns the row before mutating.
- `db.clear_user()` implements the NDPA/GDPR deletion right and deletes from **every** user-keyed table (`career_twins`, `applications`, `matches`, `events`, `saved_jobs`, `subscriptions`, `generation_log`). Any new table with a `user_id` column must be added there in the same commit.
- `ingested_jobs`, `employer_trust_records`, `job_sources` are shared (not user-keyed); only workers and admin endpoints write them.

## Backups

Worker 5 (`workers/backup_db.py`, nightly Render cron) snapshots the file with SQLite's online backup API, integrity-checks it, and uploads to Cloudflare R2 (`R2_*` env vars). A missing configuration is a loud non-zero exit, never a silent skip.

## Migration to Postgres (when triggered)

1. Types: `TEXT` JSON blobs → `jsonb`; `INTEGER PRIMARY KEY` → `bigint generated always as identity`; timestamps → `timestamptz`.
2. Keep `db.py`'s function signatures identical; swap the implementation (or add `db_pg.py` behind the same interface).
3. Enable RLS: candidates read/write only their own rows; trust records and ingested jobs readable by all authenticated users, writable only by workers.

## Acceptance criteria

- `python3 test_db.py` and `python3 test_api.py` pass offline (in-memory SQLite).
- No SQL exists outside `db.py`, the workers, and `api/main.py`'s ownership checks.
- Deleting a user removes every row keyed to them.

## Edge cases

- Malformed `extra` JSON → `list_applications` skips it silently (never raises).
- Two writes from different threads → sqlite serializes; `check_same_thread=False` is required for shared connections (Streamlit/uvicorn threads); the 30s busy timeout absorbs worker/API contention.

## Future extensions

- Soft-delete + retention window before hard delete.
- `resumes` table + object storage when raw file retention is approved (privacy policy must be updated first).
