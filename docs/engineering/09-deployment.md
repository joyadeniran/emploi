# 09 — Testing, Deployment & Roadmap

## Testing discipline (non-negotiable, from CLAUDE.md)

- Plain `check(label, cond)` scripts, no pytest. Offline always: fake models, injected DNS/HTTP, in-memory SQLite.
- Every behavior change ships with a test in the same commit; bug fixes get a regression test reproducing the report.
- Suites: `test_e2e.py` (core), `test_verify.py` (trust), `test_db.py` (persistence), `test_api.py` (API), `test_landing.py` (marketing link/copy audit). Web tier: `npm run build && npm run lint` is the current gate; add Playwright E2E when auth flows stabilize.
- CI (`.github/workflows/test.yml`) runs all five suites on push/PR.

## Local development (full stack)

```bash
# 1. Python deps + suites
python3 -m pip install -r requirements.txt
python3 test_e2e.py && python3 test_verify.py && python3 test_db.py && python3 test_api.py && python3 test_landing.py

# 2. API (port 8000) — GEMINI_API_KEY optional (AI endpoints 503 without it)
python3 -m uvicorn api.main:app --port 8000

# 3. Dashboard (port 3000) — .env.local: AUTH_SECRET, AUTH_DEV_LOGIN=true, EMPLOI_API_URL=http://localhost:8000
cd web && npm install && npm run dev

# 4. (optional) legacy Streamlit chat / future admin
python3 -m streamlit run app.py            # port 8501

# landing/ is static — open landing/index.html (its CTAs point at :3000 locally)
```

## Production topology

| Tier | Host | Domain | Env |
|---|---|---|---|
| landing/ | any static host | emploihq.com | — |
| web/ | Vercel | app.emploihq.com | AUTH_SECRET, AUTH_URL, GOOGLE_CLIENT_ID/SECRET, EMPLOI_API_URL, EMPLOI_API_KEY |
| api/ | Render web service | private (or api.emploihq.com, key-gated) | EMPLOI_API_KEY, EMPLOI_DB_PATH (Render Disk), GEMINI_API_KEY |
| app.py | Render (admin) | internal | GEMINI_API_KEY, auth secrets |

Deployment order: API → verify `/health` shows `{"ai": true, "auth": true}` → web with matching `EMPLOI_API_KEY` → smoke test trust check + application CRUD → landing.

**Deployed 2026-07-12** on a paid Render plan: web live at app.emploihq.com (Vercel), api at emploi-api.onrender.com with a 1 GB Render Disk mounted at `/var/data` for `EMPLOI_DB_PATH` (`render.yaml` disk block is active — the DB path 500s if the mount is missing). Landing is headed for Hostinger shared hosting (static HTML is fine there). Streamlit cannot run on Vercel/Netlify. If ever back on free tier: instances sleep (~15 min idle) and the filesystem is ephemeral without the disk.

## Migrations & backups

- SQLite schema is created idempotently by `db.py` on connect (additive changes only; destructive changes need a migration script + backup step).
- Backups: copy the SQLite file on deploy (Render Disk snapshot); revisit with Postgres (managed backups) — that migration is triggered by multi-instance needs, not calendar.

## Launch checklist

- [x] Google OAuth client created; redirect URIs for app.emploihq.com + localhost (still in Testing mode — whitelist test users, then publish the consent screen)
- [x] `EMPLOI_API_KEY` set on BOTH tiers (API refuses to be open in prod)
- [ ] `AUTH_DEV_LOGIN` absent in production env
- [ ] Rate limiting added to API (08-auth-and-security.md)
- [x] app.emploihq.com DNS live; HTTPS verified — emploihq.com landing still pending (Hostinger)
- [ ] Privacy/Terms pages reachable from app footer as well as landing
- [x] CI green; CHANGELOG entry for the release

## Roadmap

- **v1 — Candidates (now):** everything above; then job-ingestion worker → real matches on the dashboard; CV upload in web; generation endpoint with quota guards; Settings page with data deletion.
- **v1.x — Ops:** turn `app.py` into the internal admin console (trust review queue, prompt testing, ingestion monitoring); PostHog; Brevo notifications.
- **v2 — Recruiters:** shortlisting workspace over verified, interview-ready candidates (sidebar section already reserved).
- **v3 — Employers:** verified-employer program; the trust ledger becomes the network moat.

## Acceptance criteria

- A fresh clone reaches a working full stack using only this file.
- `curl $API/health` returns `{"ok": true, "ai": true, "auth": true}` in production.
- The launch checklist is fully ticked before real users are invited.
