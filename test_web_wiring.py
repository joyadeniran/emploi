"""Offline checks that the Next.js tier (web/) is actually wired to the API.

The bug class this catches: an API endpoint that every doc-comment claims is
called on every authenticated render, but which has ZERO callers in web/.
Nothing else in the suite can see that — the Python side is correct in
isolation, and the web tier has no runtime test — so the failure only shows up
in production as missing data.

Concretely, `POST /user/session` was never called by anything. The `users`
table therefore stayed empty forever, which silently broke:
  * the employer's Applicants list (contact column joined from `users`),
  * the notify worker's employer digest (`poster_email` from `users`, no
    fallback -> every poster skipped as "no email"),
  * `get_employer_owner_email` on invite accept,
  * `PATCH /user/notifications` (409 for every user).

Static source assertions only. No network, no node, no build. Stdlib only.
"""
import os
import re
import sys

FAILURES = []


def check(label, cond):
    status = "PASS" if cond else "FAIL"
    print(f"{status} - {label}")
    if not cond:
        FAILURES.append(label)


ROOT = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(ROOT, "web")


def read(*parts):
    path = os.path.join(WEB, *parts)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read()


def walk_sources():
    """Every hand-written .ts/.tsx under web/, excluding node_modules."""
    for dirpath, dirnames, filenames in os.walk(WEB):
        dirnames[:] = [d for d in dirnames
                       if d not in ("node_modules", ".next", "design-sync-stubs")]
        for name in filenames:
            if name.endswith((".ts", ".tsx")):
                path = os.path.join(dirpath, name)
                with open(path, encoding="utf-8") as f:
                    yield os.path.relpath(path, WEB), f.read()


check("web/ directory exists", os.path.isdir(WEB))
if not os.path.isdir(WEB):
    print("\nSOME TESTS FAILED ❌")
    sys.exit(1)

SOURCES = dict(walk_sources())


# ---------------------------------------------------------------------------
# 1. The users table gets populated (regression: it never did)
# ---------------------------------------------------------------------------

# The single helper that performs the upsert. Everything else calls it, so the
# throttle and the never-throw contract live in exactly one place.
api_lib = read("lib", "api.ts")
check("lib/api.ts exists", api_lib is not None)
api_lib = api_lib or ""

check("lib/api.ts exports ensureUserSession",
      re.search(r"export\s+async\s+function\s+ensureUserSession", api_lib) is not None)
check("ensureUserSession posts to /user/session",
      "/user/session" in api_lib)
check("ensureUserSession sends the session email",
      re.search(r"email", api_lib) is not None
      and "JSON.stringify" in api_lib)

# The regression itself: at least one caller anywhere in web/.
callers = [p for p, src in SOURCES.items()
           if "ensureUserSession(" in src and p != os.path.join("lib", "api.ts")]
check("ensureUserSession has at least one caller in web/", len(callers) > 0)

# Each entry point that must establish identity. A candidate who arrives from a
# shared job link, signs in, and applies never renders EITHER app layout — so
# the public apply route has to establish the row itself, or the employer sees
# an applicant with no name and no email.
for label, parts in (
    ("candidate app layout", ("app", "(app)", "layout.tsx")),
    ("employer layout", ("app", "(employer)", "layout.tsx")),
    ("public apply route", ("app", "api", "public", "roles", "[id]", "apply", "route.ts")),
):
    src = read(*parts)
    check(f"{label} exists", src is not None)
    check(f"{label} establishes the user session",
          src is not None and "ensureUserSession" in src)

# The upsert must never be able to break the page or block an application.
_ensure_body = api_lib.split("export async function ensureUserSession", 1)[-1]
check("ensureUserSession swallows its own failures (never throws)",
      "catch" in _ensure_body.split("\n}\n", 1)[0])


# ---------------------------------------------------------------------------
# 2. Employer sign-in returns the poster to the page they asked for
# ---------------------------------------------------------------------------
# ClientRedirectToLogin appends ?callbackUrl=<path>; the candidate /login page
# honours it. The employer page ignored it and hardcoded /employer, so every
# deep link (a bookmarked /employer/roles/3) silently dumped the poster on the
# dashboard — which reads as "my session didn't persist".

emp_login = read("app", "employer", "login", "page.tsx")
check("employer login page exists", emp_login is not None)
emp_login = emp_login or ""
check("employer login reads searchParams", "searchParams" in emp_login)
check("employer login reads callbackUrl", "callbackUrl" in emp_login)
check("employer login only honours same-site paths",
      "safeCallbackPath" in emp_login)
check("employer login signs in to the requested target (not a hardcoded path)",
      re.search(r'signIn\(\s*"google"\s*,\s*\{\s*redirectTo:\s*target\s*\}', emp_login)
      is not None)
check("employer login redirects an already-signed-in poster to the target",
      re.search(r"if\s*\(session\?\.user\)\s*redirect\(target\)", emp_login) is not None)

# The candidate page must keep working the same way (guard against a regression
# that "fixes" one page by breaking the other).
cand_login = read("app", "login", "page.tsx") or ""
check("candidate login still honours callbackUrl",
      "callbackUrl" in cand_login and "redirectTo: target" in cand_login)
check("candidate login sanitises callbackUrl too",
      "safeCallbackPath" in cand_login)

# Open-redirect guard. `startsWith("/")` alone lets "//evil.com" through — a
# browser reads that as a protocol-relative absolute URL and leaves the site,
# turning the sign-in page into a phishing primitive.
safe_redirect = read("lib", "safeRedirect.ts")
check("lib/safeRedirect.ts exists", safe_redirect is not None)
safe_redirect = safe_redirect or ""
check("safeCallbackPath is exported",
      "export function safeCallbackPath" in safe_redirect)
check("safeCallbackPath rejects protocol-relative //host",
      'startsWith("//")' in safe_redirect)
check("safeCallbackPath rejects the backslash variant /\\host",
      r'startsWith("/\\")' in safe_redirect)
check("safeCallbackPath requires a rooted path",
      'startsWith("/")' in safe_redirect)
check("neither login page hand-rolls the callbackUrl check any more",
      'callbackUrl?.startsWith("/")' not in emp_login
      and 'callbackUrl?.startsWith("/")' not in cand_login)


# ---------------------------------------------------------------------------
# 3. The Applicants list never lies about being empty
# ---------------------------------------------------------------------------
# The role page swallowed every applicants-fetch error and fell through to the
# "No direct applicants yet" empty state. An employer whose applicants failed
# to load was told, in product copy, that nobody had applied.

role_page = read("app", "(employer)", "employer", "roles", "[id]", "page.tsx")
check("employer role detail page exists", role_page is not None)
role_page = role_page or ""

check("role page tracks an applicants-fetch error",
      re.search(r"applicantsError", role_page) is not None)
check("role page renders the applicants error instead of the empty state",
      re.search(r"applicantsError\s*\?", role_page) is not None)
check("role page no longer swallows the applicants fetch silently",
      re.search(r"catch\s*\{\s*/\*\s*leave empty\s*\*/\s*\}", role_page) is None)
check("role page keeps a genuine empty state for zero applicants",
      "No direct applicants yet" in role_page)


# ---------------------------------------------------------------------------
# 4. Guard the contract the whole thing rests on
# ---------------------------------------------------------------------------
# apiFetch is the only place the shared secret and X-User-Id are attached; a
# refactor that drops either turns every employer call into a 401.
check("apiFetch still sends X-API-Key", '"X-API-Key"' in api_lib)
check("apiFetch still asserts and forwards the user id", '"X-User-Id"' in api_lib)
check("lib/api.ts is server-only", 'import "server-only"' in api_lib)


print()
if FAILURES:
    print(f"{len(FAILURES)} CHECK(S) FAILED ❌")
    for f in FAILURES:
        print(f"  - {f}")
    sys.exit(1)
print("ALL TESTS PASSED ✅")
