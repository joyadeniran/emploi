---
name: emploi
description: Working context for the Emploi codebase — architecture map, deploy topology, env matrix, test commands, and the invariants that must hold before shipping. Use when developing, debugging, or deploying any Emploi tier.
---

# Emploi — project skill

AI job-application agent for remote job seekers, starting in Africa. Brand of Crost Limited (RC 9526947). Differentiator: deterministic employer trust verification (scam protection).

## Three-tier architecture

| Tier | Code | Host | URL |
|---|---|---|---|
| Landing (static) | `landing/` | Hostinger shared (planned) | emploihq.com |
| Dashboard (Next.js 16 + NextAuth v5) | `web/` | Vercel | app.emploihq.com |
| API (FastAPI, thin dispatch) | `api/` | Render (paid) | emploi-api.onrender.com |
| Legacy chat app (Streamlit) | `app.py` | Render | internal/admin |

All business logic lives in `core.py` / `verify.py` / `db.py` at repo root — `api/main.py` and `app.py` are dispatch-only. `web/` never duplicates Python logic; it calls the API through the server-only client `web/lib/api.ts`.

## Auth chain

Browser → NextAuth v5 (Google OAuth; JWT session) → Next.js route handlers → FastAPI with `X-API-Key` (shared secret `EMPLOI_API_KEY`) + `X-User-Id` (Google `sub`). The API is never called from the browser. Dev-only demo login via `AUTH_DEV_LOGIN=true` (disabled automatically in production builds). Google OAuth is in Testing mode — only whitelisted test users can sign in until the consent screen is published.

## Env matrix

| Var | Web (Vercel) | API (Render) |
|---|---|---|
| `AUTH_SECRET`, `AUTH_URL` | ✅ | — |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | ✅ | — |
| `EMPLOI_API_URL` | ✅ (Render URL) | — |
| `EMPLOI_API_KEY` | ✅ | ✅ must match exactly |
| `GEMINI_API_KEY` | ❌ never | ✅ |
| `EMPLOI_DB_PATH` | — | `/var/data/emploi.sqlite3` (1 GB Render Disk mounted at `/var/data`) |

Local secrets: `web/.env.local`, root `.env`, `.streamlit/secrets.toml` — all gitignored, never commit.

## Commands

```bash
python3 -m pip install -r requirements.txt        # never bare `pip`
python3 test_e2e.py && python3 test_verify.py && python3 test_db.py && python3 test_api.py && python3 test_landing.py
python3 -m uvicorn api.main:app --port 8000       # API
cd web && npm run dev                             # dashboard (localhost:3000)
python3 -m streamlit run app.py                   # legacy chat app
```

All five suites must print `ALL TESTS PASSED` before any commit. Tests are plain scripts with `check(label, cond)` — no pytest, always offline (fake models, injected `dns_fn`/`mx_fn`/`fetch_fn`).

## Invariants (full list in CLAUDE.md — these are the ones people trip on)

- Trust scores computed in code (`verify.compute_trust`), never by an LLM. Red flags cap at 35; no contact caps at 40; failed probes = absent signals, never fabricated.
- Every Gemini model object is duck-typed and injected (`model.generate_content(prompt).text`); never call `genai` inside core/verify.
- Gemini JSON goes through `parse_profile_json` / `parse_json_array` — never `json.loads(resp.text)`.
- Generated applications must end with `Fit Score: NN/100` (`FIT_RE` contract).
- Never fabricate candidate experience; stretch bullets are marked "(stretch — verify)".
- `skills/*.md` at repo root are the product's Gemini prompt modules (writing_style, evaluation, interview_prep, cv_template) — behavior tuning goes there, not in code. Tests assert marker phrases from them.
- CHANGELOG.md gets an entry for EVERY shipped change; keep `docs/engineering/09-deployment.md` in sync with live topology.

## Deploy runbook

1. Push to `main` — Vercel auto-deploys `web/` (root directory is `web`); Render syncs from `render.yaml` (Blueprint).
2. Verify API: `curl https://emploi-api.onrender.com/health` → expect `{"ai": true, "auth": true}`.
3. Smoke test at app.emploihq.com: trust check + application CRUD (sample-data banner on /applications means the API is unreachable or erroring).
4. Append CHANGELOG entry.

### Known production gotchas

- `/api/applications` 500 → check the Render disk is mounted at `/var/data` (missing mount makes `db.connect()` raise) and `EMPLOI_API_KEY` matches on both tiers.
- NextAuth "Server error … configuration" page → `AUTH_SECRET`/`AUTH_URL`/Google vars missing on Vercel; redeploy after adding env vars (they don't apply to existing deployments).
- Google sign-in blocked → user not in OAuth Test users list (Google Cloud Console → Google Auth Platform → Audience).
- fpdf2: `multi_cell` needs `new_x="LMARGIN", new_y="NEXT"`; empty lines via `pdf.ln(6)`.
- Next 16: no `middleware.ts` — route protection lives in the `(app)` layout via `auth()` + redirect. Read `web/node_modules/next/dist/docs/` before writing Next.js code; APIs differ from training data.
