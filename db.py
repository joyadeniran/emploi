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
    conn.commit()
