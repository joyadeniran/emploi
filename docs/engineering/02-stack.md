# 02 — Tech Stack

**Rule:** prefer what is already in the repo. Introduce a new dependency only when a feature is impossible or materially worse without it, and record the decision in CHANGELOG.md.

## As built (July 2026)

| Layer | Choice | Notes |
|---|---|---|
| Frontend | Next.js 16, React 19, Tailwind v4, TypeScript | `web/`. App Router. **Next 16 gotcha:** `middleware.ts` is deprecated (renamed `proxy.ts`, discouraged) — auth guards live in layouts. Read `node_modules/next/dist/docs/` before writing Next code. |
| UI icons | lucide-react | No component library yet; hand-rolled design system (see 07-ui.md). shadcn/ui is an approved future addition. |
| Backend | FastAPI (Python) | `api/`. Thin dispatch only. |
| Core logic | Python 3.9+ (`core.py`, `verify.py`, `db.py`) | UI-free, importable, offline-testable. |
| Database | SQLite (`db.py`) | Single-file, keyed by user id. Migration path: Supabase Postgres when the API needs >1 instance or managed backups. Keep all SQL inside `db.py` so the swap is one file. |
| Auth | NextAuth v5 + Google OAuth | Web tier only. API trusts the web tier via shared secret (see 08-auth.md). |
| AI | Google Gemini 2.5 Flash (default), 2.5 Pro (selectable) | Via `google-generativeai`. Always passed in as a duck-typed `model`; never constructed inside core logic. |
| Prompts | `skills/*.md` markdown modules | Versioned in git; injected at runtime; editable without code changes. |
| Legacy/admin UI | Streamlit (`app.py`) | Working candidate chat app; becomes the internal ops console. |
| Marketing | Static HTML (`landing/`) | Zero dependencies; any static host. |
| CI | GitHub Actions | Runs all offline suites on push/PR. |

## Approved-when-needed (not yet used)

| Need | Choice | Trigger |
|---|---|---|
| Managed Postgres + storage | Supabase | Multi-instance API, resume file storage, or RLS needs |
| Email | Resend | Notification worker (14-notifications in 05-services.md) |
| Analytics | PostHog | Post-launch funnel measurement |
| Embeddings/search | Gemini Embedding + pgvector | Matching v2 |
| Queue/cron | Render Cron Jobs first; a real queue only if cron is insufficient | Job ingestion worker |
| Payments | Paystack (target market) | Pro billing |

## Hosting

- `web/` → **Vercel** (`app.emploihq.com`)
- `api/` → **Render** web service (private; see render.yaml)
- `landing/` → any static host (`emploihq.com`)
- `app.py` (admin) → Render, behind auth

## Acceptance criteria

- `npm run build` and `npm run lint` pass in `web/`.
- `python3 test_e2e.py && python3 test_verify.py && python3 test_db.py && python3 test_api.py && python3 test_landing.py` all print ALL TESTS PASSED with no network.
- No dependency exists in `package.json`/`requirements.txt` that no code imports.
