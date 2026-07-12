# Deploying Emploi

## Google Sign-In (multi-user)

Auth is optional: with no `[auth]` section in secrets, the app runs anonymous
and session-only (nothing persisted). To enable it:

1. Google Cloud Console → APIs & Services → **OAuth consent screen**: configure
   (External), add your app name and support email.
2. **Credentials → Create credentials → OAuth client ID → Web application.**
   Authorized redirect URI: `https://YOUR-APP-URL/oauth2callback`
   (add `http://localhost:8501/oauth2callback` for local dev).
3. Copy `.streamlit/secrets.example.toml` to `.streamlit/secrets.toml`
   (gitignored) and fill in `client_id`, `client_secret`, a random
   `cookie_secret`, and your `redirect_uri`. On Render/Cloud Run, set these
   as secret files or env-mounted secrets — never commit them.
4. Signed-in users get persistent profiles and trackers (SQLite via `db.py`;
   path from `EMPLOI_DB_PATH`, default `emploi.sqlite3`). "Clear all data"
   deletes their stored data too.

Note on Render free tier: the filesystem is ephemeral — the SQLite file is
lost on redeploy/restart. Fine for a pilot; attach a Render Disk ($1/mo) or
move to Cloud Run + Cloud SQL/Litestream before real users depend on it.

## Render (free — recommended to start)

1. Push this folder to a GitHub repo:
   ```bash
   cd ~/Documents/emploi
   git init && git add . && git commit -m "Emploi v1"
   gh repo create emploi --private --source=. --push
   ```
   (or create the repo on github.com and `git remote add` + `git push`)
2. Go to https://dashboard.render.com → New → **Blueprint** → connect the repo. Render reads `render.yaml` automatically.
3. When prompted, set the `GEMINI_API_KEY` environment variable (it's marked `sync: false`, so it's entered once in the dashboard and never lives in the repo).
4. Deploy. Your app is at `https://emploi.onrender.com` (or similar).

Free-tier caveat: the service sleeps after ~15 min of inactivity; the next visitor waits ~30–60 s while it wakes. Fine for a pilot; $7/mo removes it.

## Google Cloud Run (free tier, later)

The included `Dockerfile` works as-is:

```bash
gcloud run deploy emploi --source . --region europe-west1 \
  --allow-unauthenticated --set-env-vars GEMINI_API_KEY=YOUR_KEY
```

Scale-to-zero, generous free quota, faster cold starts than Render free.

## Not suitable

- **Vercel / Netlify** — serverless; can't run Streamlit's persistent server.
- **Hostinger shared hosting** — PHP/static only; no long-running Python processes (their VPS plans could, but that's paid and manual).

## Before inviting users

- Set `GEMINI_API_KEY` server-side only (already handled — the key field never renders when the env var exists).
- Remember data is per-session and in-memory: each user gets their own state, and it's gone when they close the tab. Fine for a pilot; add a database before anything bigger.
- Watch Gemini quota: one application = 2 calls with reviewer pass on; a `batch 10` = 20.

## The SaaS stack (v0.11+): dashboard + API

The product now has three deployable tiers (full detail: `docs/engineering/09-deployment.md`):

| Tier | Host | Domain |
|---|---|---|
| `landing/` (static) | Vercel/Netlify/any static host | emploihq.com |
| `web/` (Next.js dashboard) | Vercel | app.emploihq.com |
| `api/` (FastAPI) | Render (`render.yaml` service `emploi-api`) | private / api.emploihq.com |

**Order:** deploy the API first, confirm `GET /health` returns
`{"ok": true, "ai": true, "auth": true}`, then deploy `web/` on Vercel with:

```
AUTH_SECRET=...                # openssl rand -base64 32
AUTH_URL=https://app.emploihq.com
GOOGLE_CLIENT_ID=... GOOGLE_CLIENT_SECRET=...
EMPLOI_API_URL=https://<the-api-host>
EMPLOI_API_KEY=...             # must equal the API service's EMPLOI_API_KEY
```

Google OAuth redirect URI for the dashboard:
`https://app.emploihq.com/api/auth/callback/google`
(plus `http://localhost:3000/api/auth/callback/google` for dev).

Do NOT set `AUTH_DEV_LOGIN` in production. The API refuses nothing when
`EMPLOI_API_KEY` is unset (open dev mode) — always set it in production.
SQLite on Render free tier is ephemeral: attach a Render Disk (uncomment the
disk block in `render.yaml`) before real user data matters.
