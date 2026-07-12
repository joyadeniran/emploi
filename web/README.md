# Emploi Dashboard (web/)

The Next.js SaaS frontend for Emploi — the Career Twin dashboard that will live
at **app.emploihq.com**. Google sign-in gates everything; the design system
matches the emploihq.com landing page (purple Career Twin brand).

## Run locally

```bash
cd web
npm install
npm run dev        # http://localhost:3000
```

`.env.local` needs `AUTH_SECRET` (generate: `openssl rand -base64 32`). With
`AUTH_DEV_LOGIN=true` (dev only) a "Continue with demo account" button appears
on /login so the signed-in dashboard can be tested before Google OAuth is
configured. See `.env.example` for the Google credential setup.

## Structure

- `auth.ts` — NextAuth v5: Google provider (production) + gated dev login.
  Route protection lives in `app/(app)/layout.tsx` (Next 16 deprecates
  middleware; per-layout `auth()` + redirect is the supported pattern here).
- `app/login` — sign-in page. `app/(app)/*` — protected dashboard routes.
- `components/` — AppShell (sidebar drawer + topbar), match cards, rings, bot.
- `lib/data.ts` — typed demo data. **This is the seam for the FastAPI backend**
  (wrapping the repo's `core.py`/`verify.py`): replace each export with a fetch
  and the UI follows.

## Status

Dashboard Home, Job Matches, Applications (filterable) and Trust Check are
built; Messages, Saved, Interview Prep, Insights, Career Twin and Recruiter
Workspace are consistent placeholders. All data is demo data until the API
backend lands.
