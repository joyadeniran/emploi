# 💼 Emploi

An AI job application **agent**. One chat: drop your CV, paste a job description, get a tailored application back.

## Quick start

```bash
python3 -m pip install -r requirements.txt
python3 -m streamlit run app.py
```

Paste your Gemini API key in the sidebar (free key: https://ai.google.dev/gemini-api/docs/api-key), or set `GEMINI_API_KEY` as an environment variable.

## How to use (everything happens in the chat)

- 📎 **Drop your CV (PDF)** — Emploi reads it and builds your full profile automatically (edit any field in the sidebar)
- 📋 **Drop a CSV/Excel job sheet** — it auto-detects the job-description and company columns
- ✨ **Paste a job description** — get a tailored cover letter, CV bullets, and fit score; download as PDF, Word, or text
- ⚡ Type **`batch 5`** — apply across your loaded job sheet, ranked best fit first
- 📊 Type **`tracker`** — see and export everything you've generated
- 💬 Ask anything else — it answers as a career coach with your profile in context

A **reviewer pass** (second Gemini call that critiques and tightens the draft) is on by default — toggle in the sidebar; it doubles API calls per job.

## Employer verification (scam protection)

Every matched job gets a trust score (0–100) computed **in code, not by AI**, from real evidence: free-mail vs corporate contact domain, DNS + mail records, live website, company-name/domain consistency, and a scam-pattern lexicon (fee requests, WhatsApp-only contact, crypto salaries, unrealistic pay). Gemini's only role is one narrow judgment: does the fetched homepage describe a real business consistent with the role. Any red flag caps the score at 35; missing contact info means "unverified", never a guess. Chat: automatic on **match**, warning on **apply**, full evidence via **verify 2** or **verify info@company.com**.

Honest limits (v1): no WHOIS/domain-age lookup, no LinkedIn/Glassdoor checks (blocked to automation), and a scammer with a real website and clean posting can still pass — the score reduces risk, it isn't a guarantee. Verified-employer results are cached per session. A **shared blacklist/whitelist** now ships in `data/blacklist.json`: blacklisted domains cap trust at 10 (Avoid); whitelisted domains get a boost but never override red flags.

## Testing

Core logic (intent routing, CV extraction, reviewer pass, batch ranking, PDF/DOCX export, PDF-text roundtrip) is covered offline with a fake Gemini model — no API key needed:

```bash
python3 test_e2e.py     # core: prompts, routing, extraction, exports
python3 test_verify.py  # verification engine: all signals + scoring paths, offline
python3 test_db.py      # persistence scaffold, in-memory SQLite
```

CI runs all three suites on every push (`.github/workflows/test.yml`).

## Architecture

- `core.py` — all logic, UI-free and fully tested: prompts, intent detection, CV → profile extraction, generation, batch ranking, exports
- `app.py` — Streamlit chat interface (thin layer over core)
- `skills/` — markdown prompt modules injected into every Gemini call:
  - `writing_style.md` — hard rules that kill AI-sounding cover letters (no clichés, forward-looking framing, the "interview backtrack test" against overclaiming)
  - `evaluation.md` — five-dimension fit rubric (skills 30% / experience 25% / culture 15% / career alignment 30% + location gate) with honest-scoring rules
  - `interview_prep.md` — STAR-based interview preparation from the candidate's real experience (chat command: `interview`)

Edit a skill file and every subsequent generation uses it — no code changes needed. Rubric and style rules adapted from [MadsLorentzen/ai-job-search](https://github.com/MadsLorentzen/ai-job-search) (MIT).

## Startup folders

- `db.py` — SQLite persistence (profiles + tracker, keyed by user). Active only for signed-in users; anonymous sessions stay in-memory so a shared deployment can never leak one user's CV to another.
- `data/blacklist.json` — shared employer blacklist/whitelist (ships empty)
- `docs/` — privacy policy + terms **drafts for legal review** (NDPA/GDPR aware)
- `business/` — one-pager and unit-economics model (`unit-economics.xlsx`, live formulas)
- `landing/` — static landing page (`index.html`), deployable to any static host
- `.env.example`, `LICENSE`, `.github/workflows/test.yml` — env template, proprietary license (with MIT attribution for adapted skill prompts), CI

## Notes

- Anonymous data is session-only — closing the tab clears it. With Google Sign-In configured (see DEPLOY.md), signed-in users keep their profile and tracker across sessions.
- Scanned/image-only CV PDFs can't be read (no OCR yet) — export a text-based PDF
