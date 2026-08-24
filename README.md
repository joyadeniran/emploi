# Emploi

> Your Career Twin for a safer, more focused job search.

Emploi helps professionals turn their real experience into better job-search decisions and tailored applications. A Career Twin is built from a CV, ranked opportunities are matched against it, employer trust signals are shown before applying, and every generated document is grounded in the candidate's own history.

**Live product:** [app.emploihq.com](https://app.emploihq.com)
**Marketing site:** [emploihq.com](https://emploihq.com)

## OpenAI Build Week submission

**Track:** Apps for Your Life

### Why Emploi

Job seekers, especially those applying through informal sources, have to solve two difficult problems at once: finding roles worth their time and avoiding scams. Most tools optimize only for volume. Emploi makes the decision process safer and more honest:

- It creates a structured Career Twin from the candidate's CV and keeps it editable.
- It matches roles with an explainable fit score rather than pretending every role is a perfect fit.
- It evaluates employer trust with deterministic signals: contact-domain quality, DNS/MX records, public-site reachability, company/domain consistency, known scam language, and a shared blocklist/allowlist.
- It prepares tailored cover letters and CVs without inventing experience, then leaves the final application decision with the person.

Trust is **risk reduction, not a guarantee**. A score never replaces judgment: candidates are always warned not to pay fees or provide bank or identity details as part of an application.

### How Codex and GPT-5.6 were used

GPT-5.6 was used through Codex as the development partner for this challenge—not as a hidden replacement for the product's user-facing AI runtime. Emploi's runtime application-generation model remains explicitly configured on the server; this distinction keeps the submission honest and reproducible.

Codex accelerated the project by:

1. **Understanding the existing system.** It traced the Next.js dashboard, FastAPI dispatch layer, Python core, SQLite schema, job-ingestion workers, and static landing site before proposing changes.
2. **Building a more useful operations surface.** It implemented the responsive admin shell, sidebar navigation, and complete job-source CRUD workflow. This included identifying and fixing a subtle correctness issue: editing a source previously upserted by `(ats, token)` instead of updating the selected source ID.
3. **Protecting behaviour with tests.** It added API regressions for editing and deleting job sources, then ran the offline core, verification, database, API, and landing suites plus the Next.js lint/build checks.
4. **Bringing the public story in line with the product.** It audited the three Hostinger pages, added canonical/social metadata, updated pricing to the live Free / Pro / Max tiers, and changed absolute "verified" language to the product's evidence-based “company checked” posture.

Key product decisions remained human-directed: candidates retain final control over applications; trust scoring is deterministic code rather than a model opinion; and generated documents may not fabricate experience.

> **Devpost note:** add the `/feedback` Session ID for the Codex session in which the majority of the project was built to the required Devpost field. Do not put a secret, API key, or private session link in this repository.

## What it does

| Capability | What happens |
|---|---|
| Career Twin | Upload a text-based CV PDF and create an editable, structured profile. |
| Job discovery | Browse ingested roles, import job sheets, paste a job URL, or add a job description. |
| Honest matching | Rank roles against skills, experience, goals, location, and work preferences. |
| Scam protection | Show named employer signals and a deterministic trust level before a candidate applies. |
| Application studio | Generate a tailored cover letter and CV, review it, then export PDF or DOCX. |
| Application tracking | Track the outcome of every application. |
| Employer portal | Employers can post roles, shortlist opted-in candidates, invite them, and manage unlock credits. |
| Operations | Owner-only admin portal for health checks, worker controls, source management, trust alerts, users, and employer credits. |

## Architecture

```text
emploihq.com                 Static HTML marketing site (Hostinger)
        │
app.emploihq.com             Next.js 16 + NextAuth dashboard (Vercel)
        │  server-to-server: X-API-Key + X-User-Id
emploi-api.onrender.com      FastAPI API (Render)
        │
core.py · verify.py · db.py  AI workflow, deterministic trust engine, SQLite
```

- `web/` — Next.js dashboard and server-side API proxies. It contains presentation and authentication, not duplicate Python business logic.
- `api/main.py` — FastAPI validation and dispatch layer.
- `core.py` — CV extraction, matching, application/CV generation, exports, and defensive model-output parsing.
- `verify.py` — deterministic employer trust scoring; an LLM never assigns a trust score.
- `db.py` — SQLite schema and all persistence operations.
- `workers/` — ingestion, matching, verification, notifications, expiry, and backup jobs.
- `landing/` — exactly three static files for Hostinger: `index.html`, `privacy.html`, and `terms.html`.

## Run locally

### Prerequisites

- Python 3.12 recommended
- Node.js 20+
- A Gemini API key for AI-powered flows (the test suite does not need one)

### 1. Install and verify the Python service

```bash
python3 -m pip install -r requirements.txt
python3 test_e2e.py && python3 test_verify.py && python3 test_db.py && python3 test_api.py && python3 test_landing.py
```

Run the API in a second terminal:

```bash
export EMPLOI_API_KEY=local-dev-key
export GEMINI_API_KEY=your-gemini-key   # optional: AI endpoints return a clear 503 without it
export EMPLOI_DB_PATH=emploi.sqlite3
python3 -m uvicorn api.main:app --port 8000
```

### 2. Run the dashboard

Create `web/.env.local` (never commit it):

```bash
AUTH_SECRET=replace-with-a-long-random-local-secret
AUTH_DEV_LOGIN=true
EMPLOI_API_URL=http://localhost:8000
EMPLOI_API_KEY=local-dev-key
```

Then start Next.js:

```bash
cd web
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Development login is intentionally disabled in production builds. For Google OAuth, add the Google variables described in [`docs/engineering/09-deployment.md`](docs/engineering/09-deployment.md).

### 3. Optional: run the legacy chat interface

```bash
python3 -m streamlit run app.py
```

This is useful for exercising the original chat-first workflow; the production dashboard lives in `web/`.

### 4. Preview the static landing site

```bash
python3 -m http.server 8080 --directory landing
```

Open [http://localhost:8080](http://localhost:8080). On Hostinger, upload only the three HTML files from `landing/` to `public_html/`; keep `app.emploihq.com` on Vercel.

## Sample data and judge-friendly testing

- The automated test suite is offline and uses fake model responses and in-memory SQLite—no accounts, card, or API key required.
- `data/manual_jobs/example.json` is a small manual-job example.
- `data/job_sources.json` provides source-registry seed data. Optional Jooble and Adzuna connectors remain harmless when their environment keys are absent.
- Use a text-based CV PDF. Image-only/scanned PDFs are detected and handled gracefully, but OCR is not part of this version.

For a quick product walkthrough: create a Career Twin, browse or import a role, inspect the trust signals, generate a draft, and open the Applications page to track it.

## Quality checks

```bash
# Offline product checks
python3 test_e2e.py && python3 test_verify.py && python3 test_db.py && python3 test_api.py && python3 test_landing.py

# Dashboard checks
cd web && npm run lint && npm run build
```

The tests deliberately enforce the product guardrails: defensive model parsing, no fabricated candidate experience, deterministic trust-score caps, correct job-source CRUD, safe exports, and valid static-site links.

## Deployment

| Surface | Host | Notes |
|---|---|---|
| Marketing and legal pages | Hostinger | `landing/index.html`, `landing/privacy.html`, `landing/terms.html` |
| Product dashboard | Vercel | `app.emploihq.com` |
| API + SQLite disk | Render | `render.yaml` provisions the service and persistent disk |

Set production secrets in the host dashboards, never in source control. See [`docs/engineering/09-deployment.md`](docs/engineering/09-deployment.md) for the current environment matrix and rollout order.

## Safety and privacy

- Emploi does not auto-submit job applications.
- Generated material must be reviewed by the candidate before sending.
- Employer trust checks use public signals and can be incomplete; never pay a fee to apply or share banking/identity details.
- Recruiter visibility is opt-in; raw CVs and private chat history are not exposed through the discovery surface.

## License

See [LICENSE](LICENSE). Prompt-rubric attribution is retained where applicable.
