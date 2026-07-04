# Deploying Emploi

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
