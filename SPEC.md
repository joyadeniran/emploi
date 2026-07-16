# Emploi — Engineering Specification

**Version:** 2.0 · July 2026 · supersedes the v1 Streamlit-only spec

The specification is an AI-native document set under [`docs/engineering/`](docs/engineering/) — written so a coding agent (or engineer) can build any part of Emploi from it plus the repo. `CLAUDE.md` remains the canonical rulebook; where they disagree, the repo + CLAUDE.md win, then fix the spec.

| Section | Covers |
|---|---|
| [01 — Overview](docs/engineering/01-overview.md) | Purpose, vision, non-negotiable invariants, goals/non-goals, success criteria, architecture map |
| [02 — Tech Stack](docs/engineering/02-stack.md) | As-built stack, approved-when-needed additions, hosting |
| [03 — Database](docs/engineering/03-database.md) | Schema (as built + planned), access rules, Postgres migration path |
| [04 — API](docs/engineering/04-api.md) | Every endpoint with contracts, auth model, degradation behavior |
| [05 — Services & Workers](docs/engineering/05-services-and-workers.md) | Logical services, the four background workers, error/logging policy |
| [06 — AI Layer](docs/engineering/06-ai-layer.md) | Models, skills/prompts, function surface, coupled contracts, injection posture, cost |
| [07 — Frontend](docs/engineering/07-ui.md) | Design system, pages, components, data flow, UX conventions |
| [08 — Auth & Security](docs/engineering/08-auth-and-security.md) | Google OAuth, service auth, secrets, security checklists |
| [09 — Testing, Deployment & Roadmap](docs/engineering/09-deployment.md) | Suites/CI, local + production topology, launch checklist, v1→v3 roadmap |
| [10 — Billing](docs/engineering/10-billing.md) | Paystack integration, Free/Pro/Max tiers, quota enforcement, webhook lifecycle, deployment checklist |
| [11 — Employer Portal](docs/engineering/11-employer-portal.md) | Interview Marketplace, pay-per-unlock billing, trust gating, invite state machine, admin dashboard |

## System in one paragraph

A candidate signs in with Google at **app.emploihq.com** (`web/`, Next.js 16), uploads a CV, and gets a **Career Twin** — a living profile extracted by Gemini. The dashboard shows verified, honestly-scored job matches; one click creates a tracked application backed by the FastAPI service (`api/`) over the UI-free Python core (`core.py` generation/matching, `verify.py` deterministic trust engine, `db.py` persistence). Trust scores are computed in code from named signals — never by an LLM — and every generated document is grounded strictly in the candidate's real experience. The static landing site (`landing/`) sells it at **emploihq.com**; the Streamlit app (`app.py`) remains as the chat product and future internal admin console. Emploi is a brand of Crost Limited (RC 9526947), Nigeria.
