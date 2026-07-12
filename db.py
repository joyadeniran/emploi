"""Emploi persistence scaffold — SQLite storage for profiles and the tracker.

Wired into app.py ONLY for signed-in users (Google OIDC via st.login). Anonymous
sessions stay in-memory: SQLite on a shared deployment is global, and persisting
without user identity would leak one user's CV to the next visitor. Everything
here is keyed by user_id (Google `sub` claim) for exactly that reason.

Design notes:
- Profiles are stored as JSON blobs: the profile is a schema-flexible dict
  everywhere else in the codebase, so the store must not impose columns on it.
- Applications get real columns for the fields the tracker filters/sorts on
  (company, role, status) plus an `extra` JSON blob for everything else.
- No Streamlit imports; pure stdlib; fully testable offline (see test_db.py).
"""

import json
import sqlite3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
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
    conn.executescript(_SCHEMA)
    return conn


def save_profile(conn, user_id: str, profile: dict) -> None:
    """Upsert the user's profile as a JSON blob."""
    if not isinstance(profile, dict):
        raise TypeError("profile must be a dict")
    conn.execute(
        "INSERT INTO profiles (user_id, data, updated_at) "
        "VALUES (?, ?, datetime('now')) "
        "ON CONFLICT(user_id) DO UPDATE SET data=excluded.data, "
        "updated_at=excluded.updated_at",
        (user_id, json.dumps(profile)))
    conn.commit()


def load_profile(conn, user_id: str) -> dict:
    """Return the user's profile, or {} if absent/unreadable. Never raises."""
    row = conn.execute(
        "SELECT data FROM profiles WHERE user_id = ?", (user_id,)).fetchone()
    if not row:
        return {}
    try:
        data = json.loads(row["data"])
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


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
    """Delete everything stored for one user (their right under NDPA/GDPR).
    Backs the app's 'Clear all data' button for signed-in users."""
    conn.execute("DELETE FROM profiles WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM applications WHERE user_id = ?", (user_id,))
    conn.commit()
