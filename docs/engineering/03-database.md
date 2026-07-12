# 03 — Database

**Current engine:** SQLite via `db.py` (the only file allowed to contain SQL). **Target:** Supabase Postgres when multi-instance or file storage demands it — the schema below is written to survive that migration.

## As-built schema (db.py)

```sql
CREATE TABLE profiles (
    user_id    TEXT PRIMARY KEY,      -- Google `sub` claim (stable), else email
    data       TEXT NOT NULL,         -- profile JSON blob (schema-flexible)
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE applications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT NOT NULL,
    company    TEXT,
    role       TEXT,
    status     TEXT,                  -- applied|interview|offer|rejected|withdrawn
    extra      TEXT NOT NULL DEFAULT '{}',  -- JSON: fit_score, source, next_step...
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_applications_user ON applications(user_id);
```

Design choices, deliberate:
- **Profile is a JSON blob**, not columns — the extracted-profile shape evolves with the prompt. Only key it by user.
- **`extra` JSON on applications** — known fields are columns (filter/sort), everything else rides along. `list_applications()` flattens extra into the returned dicts.
- **Status set** is enforced at the API layer (`api/main.py StatusIn`), not by a CHECK constraint, so adding a status is a one-line change + test.

## Access rules

- Every query filters by `user_id`. There are no cross-user reads. The PATCH ownership check in `api/main.py` is the pattern: verify `user_id` owns the row before mutating.
- `db.clear_user()` implements the NDPA/GDPR deletion right and must delete from **every** table that gains a `user_id` column in the future.

## Planned tables (build when the feature lands, not before)

```sql
-- employer trust records: compounding verification results
employer_trust_records(id, company_name, domain UNIQUE, trust_score,
                       signals JSON, community_reports INT, last_checked_at)

-- ingested jobs: normalized pool from ingestion workers
ingested_jobs(id, source, source_job_id, title, company_name, description,
              location, is_remote, salary_text, apply_url, category,
              fetched_at, UNIQUE(source, source_job_id))

-- matches: cached ranking output per user
matches(id, user_id, job_id, fit_score, reason, created_at)

-- events: analytics/audit log (see 17-logging in 08-auth.md/05-services.md)
events(id, user_id, type, payload JSON, created_at)
```

## Migration to Postgres (when triggered)

1. Types: `TEXT` JSON blobs → `jsonb`; `INTEGER PRIMARY KEY` → `bigint generated always as identity`; timestamps → `timestamptz`.
2. Keep `db.py`'s function signatures identical; swap the implementation (or add `db_pg.py` behind the same interface).
3. Enable RLS: candidates read/write only their own rows; trust records and ingested jobs readable by all authenticated users, writable only by workers.

## Acceptance criteria

- `python3 test_db.py` and `python3 test_api.py` pass offline (in-memory SQLite).
- No SQL exists outside `db.py` (grep check: `grep -rn "SELECT\|INSERT\|UPDATE " --include="*.py" .` hits only `db.py` and `api/main.py`'s ownership check).
- Deleting a user removes every row keyed to them.

## Edge cases

- Malformed `extra` JSON → `list_applications` skips it silently (never raises).
- Two writes from different threads → sqlite serializes; `check_same_thread=False` is required for shared connections (Streamlit/uvicorn threads).

## Future extensions

- Soft-delete + retention window before hard delete.
- `resumes` table + Supabase Storage when raw file retention is approved (privacy policy must be updated first).
