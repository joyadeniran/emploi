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
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source        TEXT NOT NULL,
    source_job_id TEXT NOT NULL,
    title         TEXT,
    company_name  TEXT,
    description   TEXT,
    location      TEXT,
    is_remote     INTEGER NOT NULL DEFAULT 0,
    salary_text   TEXT,
    apply_url     TEXT,
    category      TEXT,
    fetched_at    TEXT NOT NULL DEFAULT (datetime('now')),
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


def connect(path: str, check_same_thread: bool = True) -> sqlite3.Connection:
    """Open (or create) the database and ensure the schema exists.

    Pass check_same_thread=False when the connection is shared across threads
    (Streamlit runs session code in worker threads and a cached connection
    crosses them; sqlite serializes writes internally).
    """
    conn = sqlite3.connect(path, check_same_thread=check_same_thread)
    conn.row_factory = sqlite3.Row
    # migrate legacy `profiles` table before schema creation so the
    # CREATE TABLE IF NOT EXISTS career_twins becomes a no-op after the rename
    try:
        conn.execute("ALTER TABLE profiles RENAME TO career_twins")
        conn.commit()
    except Exception:
        pass  # already renamed, or old table never existed
    conn.executescript(_SCHEMA)
    return conn


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
        item = {"id": r["id"], "company": r["company"], "role": r["role"],
                "status": r["status"], "created_at": r["created_at"]}
        try:
            item.update(json.loads(r["extra"]) or {})
        except Exception:
            pass
        out.append(item)
    return out


def update_application_status(conn, app_id: int, status: str) -> None:
    conn.execute("UPDATE applications SET status = ? WHERE id = ?",
                 (status, app_id))
    conn.commit()


def clear_user(conn, user_id: str) -> None:
    """Delete everything stored for one user (right under NDPA/GDPR)."""
    conn.execute("DELETE FROM career_twins WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM applications WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM matches WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM events WHERE user_id = ?", (user_id,))
    conn.commit()


# ---------------------------------------------------------------------------
# Job sourcing — ingested_jobs
# ---------------------------------------------------------------------------

def upsert_job(conn, source: str, source_job_id: str, fields: dict) -> int:
    """Insert or replace a job row. Returns the row id (new or existing)."""
    allowed = {"title", "company_name", "description", "location",
               "is_remote", "salary_text", "apply_url", "category"}
    data = {k: v for k, v in fields.items() if k in allowed}
    cur = conn.execute(
        "INSERT INTO ingested_jobs "
        "(source, source_job_id, title, company_name, description, location, "
        " is_remote, salary_text, apply_url, category, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now')) "
        "ON CONFLICT(source, source_job_id) DO UPDATE SET "
        "  title=excluded.title, company_name=excluded.company_name, "
        "  description=excluded.description, location=excluded.location, "
        "  is_remote=excluded.is_remote, salary_text=excluded.salary_text, "
        "  apply_url=excluded.apply_url, category=excluded.category, "
        "  fetched_at=excluded.fetched_at",
        (source, source_job_id,
         data.get("title"), data.get("company_name"), data.get("description"),
         data.get("location"), int(bool(data.get("is_remote"))),
         data.get("salary_text"), data.get("apply_url"), data.get("category")))
    conn.commit()
    if cur.lastrowid:
        return cur.lastrowid
    row = conn.execute(
        "SELECT id FROM ingested_jobs WHERE source=? AND source_job_id=?",
        (source, source_job_id)).fetchone()
    return row["id"] if row else -1


def list_jobs(conn, *, remote_only: bool = False, category: Optional[str] = None,
              limit: int = 100, offset: int = 0) -> list:
    """Return ingested jobs, newest first. Filters are optional."""
    clauses, params = [], []
    if remote_only:
        clauses.append("is_remote = 1")
    if category:
        clauses.append("category = ?")
        params.append(category)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM ingested_jobs {where} "
        f"ORDER BY fetched_at DESC LIMIT ? OFFSET ?",
        (*params, limit, offset)).fetchall()
    return [dict(r) for r in rows]


def count_jobs(conn, *, remote_only: bool = False,
               category: Optional[str] = None) -> int:
    clauses, params = [], []
    if remote_only:
        clauses.append("is_remote = 1")
    if category:
        clauses.append("category = ?")
        params.append(category)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
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


def list_matches(conn, user_id: str, *, limit: int = 50) -> list:
    """Return a user's matches, best fit first, with job detail joined."""
    rows = conn.execute(
        "SELECT m.id, m.fit_score, m.reason, m.created_at, "
        "       j.id AS job_id, j.title, j.company_name, j.location, "
        "       j.is_remote, j.salary_text, j.apply_url, j.category, "
        "       j.source "
        "FROM matches m JOIN ingested_jobs j ON m.job_id = j.id "
        "WHERE m.user_id = ? ORDER BY m.fit_score DESC LIMIT ?",
        (user_id, limit)).fetchall()
    return [dict(r) for r in rows]


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
