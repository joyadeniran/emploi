# Emploi — Changelog

All notable changes to this project. Format loosely follows [Keep a Changelog](https://keepachangelog.com); dates are when the work shipped.

## [Unreleased]
Planned: fresh-listings agent (job APIs + monitored sources), persistent storage (SQLite), shared employer blacklist/whitelist, WHOIS domain-age check, OCR for scanned CVs, curator partner pilot (Halo), BYOK option for users.

## [0.7.0] — 2026-07-04 — Conversational memory + profile self-updates
### Added
- Chat is now context-aware: the last 8 messages ride along with every conversational turn.
- The agent can update the profile from conversation — "I want senior marketing roles" updates the goals field (only known profile keys accepted; the reply confirms what changed). Structured `{"reply", "profile_updates"}` protocol with graceful fallback to plain text.
- Friendly quota errors: 429s now explain the free-tier limit (20 requests/day) and the retry window instead of dumping the raw API error; all handler error paths use the same formatter.

## [0.6.1] — 2026-07-04
### Changed
- Cover-letter downloads no longer include the Fit Evaluation section — downloads contain only sendable content; the evaluation stays on-screen (a user could otherwise have attached the gaps analysis to a real application). Handles both current and legacy section headers.

## [0.6.0] — 2026-07-04 — Full tailored CV generation
### Added
- Every application now produces a COMPLETE ready-to-send CV (not just bullet suggestions), downloadable as PDF/Word/text alongside the cover letter.
- `skills/cv_template.md`: CV structure, relevance-weighted content selection (cut lowest-value bullets first, posting-relevant content survives regardless of recency), ground-truth-only rules with "(stretch — verify)" marking.
- Sidebar shows API-call cost per application (3 with reviewer pass, 2 without).

## [0.5.2] — 2026-07-04
### Fixed
- PDF/Word downloads dumped raw markdown (`##`, `**`, `*` bullets, `|` tables) and mangled ₦ into `?`. Exports now render markdown properly: bold headers, real bullets, formatted table rows, currency-safe text. Regression tests do a full PDF→text roundtrip asserting no markdown tokens survive.

## [0.5.1] — 2026-07-04
### Fixed
- Slash-prefixed commands (`/verify`, `/apply 2`, `/batch 3`, `/tracker`) were falling through to the career-chat handler; the intent router now strips a leading `/`. Regression tests added (suite: 60 checks).

## [0.5.0] — 2026-07-04 — Employer verification (scam protection)
### Added
- `verify.py`: deterministic trust engine. Score (0–100) computed in code from named evidence: free-mail vs corporate contact domain, DNS + MX records, live website, company-name/domain consistency, scam-pattern lexicon (fee requests, WhatsApp-only contact, crypto salaries, unrealistic pay). Any red flag caps the score at 35; no contact info caps at 40 ("unverified", never guessed).
- Gemini's only verification role: one narrow judgment on fetched homepage content (consistent / inconsistent / unclear); errors degrade to "unknown".
- Trust column (🟢🟡🟠🔴) in match results; automatic verification + low-trust warning on `apply`; `verify 2` / `verify info@company.com` shows full evidence. Per-session domain cache (network probed once per employer).
- `test_verify.py`: 27 offline checks with injected DNS/HTTP/LLM fakes covering every scoring path.
- New deps: `requests`, `dnspython`. Job extraction now also captures the contact field.
### Known limits (documented in README)
- No WHOIS/domain-age, no LinkedIn/Glassdoor checks; a scammer with a real website can still pass. Risk reduction, not a guarantee.

## [0.4.0] — 2026-07-04 — Skills system (prompt IP port)
### Added
- `skills/` folder: markdown prompt modules injected into every Gemini call, editable without code changes. Adapted from [MadsLorentzen/ai-job-search](https://github.com/MadsLorentzen/ai-job-search) (MIT).
  - `writing_style.md` — hard anti-cliché rules, forward-looking cover-letter framing, "interview backtrack test" against overclaiming (stretchy CV bullets get flagged "(stretch — verify)").
  - `evaluation.md` — five-dimension weighted fit rubric (skills 30 / experience 25 / culture 15 / career alignment 30 + location gate), verdict thresholds, honest-scoring rules (must name gaps; warns when experience match < 50).
  - `interview_prep.md` — STAR prep from the candidate's real experience, tough-question answers, questions to ask, roleplay mode.
- `interview` chat command (`interview`, `interview 2`, `interview Acme`).
- Reviewer pass now enforces the style guide and re-checks over-generous fit scores.

## [0.3.0] — 2026-07-04 — Smarter documents + server-side key
### Added
- PDF classification: every uploaded PDF is classified (CV / job listings / other) before processing — job-listing PDFs no longer get mangled by the CV parser.
- Job extraction from listing PDFs (e.g. Halo hiring sheets) → ranked matching against the profile in one call (fit score + reason per job) → `apply 1` / `apply <company>`.
- `match` command for ranked matching over any loaded job source.
- API key resolved server-side from `GEMINI_API_KEY` env var or Streamlit secrets; users never see a key field in production (sidebar input remains as dev-mode fallback). Shared-key model for the pilot; BYOK later.
### Fixed
- Company-column detection for terse sheet headers ("co", "org").

## [0.2.0] — 2026-07-04 — Agent chat UI + CV auto-fill
### Changed
- Replaced the tab-based UI with a single chat interface; an intent router dispatches uploads and commands (CV PDF → profile, sheet → jobs, pasted JD → generate, `batch N`, `tracker`, free text → career coach with profile context).
### Added
- CV PDF upload → Gemini extracts the full profile automatically (no manual form); editable in sidebar.
- `core.py` split from `app.py` (all logic UI-free and testable).
- Deploy files: `render.yaml` (Render blueprint), `Dockerfile` (Cloud Run-ready), `DEPLOY.md`.
### Fixed
- fpdf2 multi-line rendering bug (cursor position after `multi_cell`).

## [0.1.0] — 2026-07-04 — Initial release
- Named **Emploi** (checked: no existing AI job tool with the name; note: collides with generic French usage).
- Streamlit app: profile form, CSV/Excel job-list import, Gemini-tailored cover letter + CV bullets + fit score, application tracker with CSV export.
- Reviewer pass (second Gemini call critiques and tightens drafts; original draft preserved).
- Batch mode across imported job sheets, ranked by fit.
- PDF / Word (.docx) / text downloads.
- Offline test suite with a fake Gemini model (no API key needed).
