# 01 — Overview

**Emploi Engineering Specification v1.0** · July 2026 · Living document — update alongside CHANGELOG.md on every architectural change.

This spec explains **how to build Emploi**, not what it is. A coding agent (Claude Code, Cursor, Codex, Gemini CLI) should be able to build any section from this document plus the repo. Where the repo and this spec disagree, the repo + `CLAUDE.md` win — then fix the spec.

## Purpose

Emploi is an AI job-application platform: a candidate's **Career Twin** (living profile built from their CV) finds opportunities, verifies every employer for scam signals, and prepares honest, tailored applications.

## Vision

Career Twins that work while you sleep — matching, verifying, applying, preparing — for every professional. **Starting in Africa, built for the world.**

## Non-negotiable product invariants

These override any feature request. They are enforced by tests and by `CLAUDE.md`:

1. **Trust scores are computed in code, never by an LLM.** `verify.compute_trust()` maps named signals to points. Red flags cap at 35; no contact caps at 40. Failed probes are "unverified", never fabricated.
2. **Never fabricate candidate experience.** Every generation prompt carries a ground-truth constraint; stretchy content is marked "(stretch — verify)".
3. **Business logic lives in the Python core** (`core.py`, `verify.py`, `db.py`), never in UI tiers. The API tier is thin dispatch; the web tier is presentation.
4. **All model objects are duck-typed** (`model.generate_content(prompt).text`); tests inject fakes; no live network or API keys in tests.

## Goals (v1 — candidates)

- Sign in with Google, upload a CV, get a Career Twin profile.
- Verified, honestly-scored job matches; one-click tailored applications.
- Application tracker with status pipeline.
- Trust Check as a standalone, visible feature (the moat).

## Non-goals (v1)

- Recruiter/employer products (v2/v3 — see 09-deployment.md roadmap).
- Auto-submitting applications to employers on the candidate's behalf.
- Payments (pricing is displayed; billing is deferred).
- Mobile apps.

## Success criteria

- A new user goes sign-in → CV upload → first tailored application in under 5 minutes.
- Zero fabricated CV content in generated documents (spot-check discipline + prompt regression tests).
- Trust engine flags 100% of the scam-lexicon patterns in `verify.py` with a score ≤ 35.
- All test suites green in CI on every push.

## Current architecture (as built)

```
emploi/
├── web/          Next.js 16 SaaS dashboard (app.emploihq.com) — presentation only
├── api/          FastAPI service — thin HTTP layer over the Python core
├── core.py       ALL generation/matching/parsing logic (UI-free)
├── verify.py     Deterministic trust engine (all I/O injectable)
├── db.py         SQLite persistence (profiles, applications)
├── app.py        Streamlit chat app — legacy candidate UI, future admin console
├── skills/       Prompt modules (markdown) injected into Gemini calls
├── landing/      Static marketing site (emploihq.com)
├── docs/engineering/   this spec
└── test_*.py     Offline suites (e2e, verify, db, api, landing)
```

Target evolution (do not restructure preemptively): `web` → Vercel, `api` → Render, `app.py` becomes the internal admin console, SQLite → Postgres (Supabase) when multi-instance deployment demands it.

## Acceptance criteria for this document set

- Every section ends with acceptance criteria a coding agent can test against.
- No section contradicts `CLAUDE.md` or a passing test.
- A reader can run the full stack locally from 09-deployment.md alone.
