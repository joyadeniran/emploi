"""Offline tests for the persistence scaffold. Run: python3 test_db.py
Uses in-memory SQLite only — no files, no network."""

import sys

from db import (connect, save_profile, load_profile, add_application,
                list_applications, update_application_status, clear_user)


def check(label, cond):
    print(("PASS" if cond else "FAIL"), "-", label)
    return cond


ok = True
conn = connect(":memory:")

# 1. Profile roundtrip
profile = {"name": "Ada", "skills": "Python, SQL", "goals": "remote data roles"}
save_profile(conn, "user-1", profile)
ok &= check("profile roundtrip", load_profile(conn, "user-1") == profile)

# 2. Save is an upsert
save_profile(conn, "user-1", {"name": "Ada Obi"})
ok &= check("second save overwrites", load_profile(conn, "user-1") == {"name": "Ada Obi"})

# 3. Unknown user -> empty dict, never raises
ok &= check("unknown user -> {}", load_profile(conn, "nobody") == {})

# 4. Users are isolated
save_profile(conn, "user-2", {"name": "Bola"})
ok &= check("users isolated",
            load_profile(conn, "user-1") == {"name": "Ada Obi"}
            and load_profile(conn, "user-2") == {"name": "Bola"})

# 5. Applications: insert + list (newest first)
a1 = add_application(conn, "user-1", {"company": "Acme", "role": "Analyst",
                                      "status": "Generated", "fit_score": 78})
a2 = add_application(conn, "user-1", {"company": "Halo", "role": "VA",
                                      "status": "Sent", "notes": "via curator"})
apps = list_applications(conn, "user-1")
ok &= check("two applications listed, newest first",
            len(apps) == 2 and apps[0]["company"] == "Halo")
ok &= check("row ids returned and present", a1 != a2 and apps[1]["id"] == a1)
ok &= check("extra fields preserved (notes, fit_score)",
            apps[0]["notes"] == "via curator" and apps[1]["fit_score"] == 78)

# 6. Applications are per-user
ok &= check("other user sees no applications", list_applications(conn, "user-2") == [])

# 7. Status update
update_application_status(conn, a1, "Interview")
apps = list_applications(conn, "user-1")
ok &= check("status update sticks",
            [a for a in apps if a["id"] == a1][0]["status"] == "Interview")

# 8. Defensive: non-dict profile rejected, DB untouched
try:
    save_profile(conn, "user-1", "not a dict")
    bad = False
except (TypeError, ValueError):
    bad = True
ok &= check("non-dict profile raises, existing data intact",
            bad and load_profile(conn, "user-1") == {"name": "Ada Obi"})

# 9. clear_user wipes only that user (privacy: "Clear all data" when signed in)
clear_user(conn, "user-1")
ok &= check("clear_user removes profile and applications",
            load_profile(conn, "user-1") == {} and list_applications(conn, "user-1") == [])
ok &= check("clear_user leaves other users untouched",
            load_profile(conn, "user-2") == {"name": "Bola"})

# 10. Cross-thread use (Streamlit shares one cached connection across session threads)
import tempfile as _tf, os as _os2, threading
_dbfile = _tf.NamedTemporaryFile(suffix=".sqlite3", delete=False).name
tconn = connect(_dbfile, check_same_thread=False)
err = []
def _work():
    try:
        save_profile(tconn, "t-user", {"name": "Thread"})
    except Exception as e:
        err.append(e)
t = threading.Thread(target=_work); t.start(); t.join()
ok &= check("connection usable from another thread when check_same_thread=False",
            not err and load_profile(tconn, "t-user") == {"name": "Thread"})
tconn.close(); _os2.unlink(_dbfile)

print("\n" + ("ALL TESTS PASSED ✅" if ok else "SOME TESTS FAILED ❌"))
sys.exit(0 if ok else 1)
