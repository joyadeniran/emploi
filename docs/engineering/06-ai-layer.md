# 06 — AI Layer

**Rule zero:** no prompt lives inside business logic. Prompt text belongs in `skills/*.md` (behavior modules, editable without code) or in `build_*_prompt()` functions in `core.py`/`verify.py` (structural scaffolding). Everything is versioned in git.

## Models

- Default `gemini-2.5-flash`; `gemini-2.5-pro` selectable. Model name comes from env/UI — never hardcoded in logic.
- **Duck-typing invariant:** every function takes `model` with `.generate_content(prompt) → obj.text`. Tests pass `FakeModel`. Never import/configure `genai` inside `core.py`/`verify.py` — model construction happens at the edges (`api/main.py get_model`, `app.py`).

## Skills (prompt modules)

| File | Injected into | Load-bearing markers (tests assert these) |
|---|---|---|
| `skills/writing_style.md` | generation + review | "NO em-dashes"; interview backtrack test; "(stretch — verify)" marking |
| `skills/evaluation.md` | generation, review, matching | weighted rubric ("weight 30%"); must name gaps; location gate |
| `skills/interview_prep.md` | interview prep | STAR from real experience |
| `skills/cv_template.md` | CV generation | relevance-weighted selection; ground-truth-only |

`load_skill(name)` reads and caches. Rewriting a skill means keeping or deliberately updating the marker phrases **and their tests together**.

## AI functions (the complete surface)

| Function | Purpose | Output contract |
|---|---|---|
| `extract_profile(model, cv_text)` | CV → profile dict | JSON via `parse_profile_json`; `{}` on garbage |
| `classify_document(model, text)` | cv / listings / other | one word; guards the CV parser from job PDFs |
| `extract_jobs(model, text)` | listings text → job dicts | array via `parse_json_array` |
| `match_jobs(model, profile, jobs)` | ranked fit scores + reasons | array; scores honest per evaluation skill |
| `generate_application(model, ...)` | cover letter + evaluation | MUST end `Fit Score: NN/100` (regex `FIT_RE`) |
| `generate_cv(model, ...)` | complete tailored CV | ground-truth-only |
| `prepare_interview(model, ...)` | STAR prep | from real experience |
| `chat_turn(model, profile, q, history)` | career chat | `{"reply","profile_updates"}` JSON, plain-text fallback, only known profile keys applied |
| `verify.check_site_content(model, ...)` | site consistency | consistent/inconsistent/None ONLY — never a score |

## Coupled contracts (change all pieces together, or none)

- **Fit score:** `build_prompt` output format ↔ `FIT_RE` ↔ `parse_fit_score` ↔ `build_review_prompt` structure rule ↔ tests.
- **JSON parsing:** model output may include ```json fences and prose — always `_extract_json` helpers, never `json.loads(resp.text)`.
- **Reviewer pass** doubles API calls per application — any UI exposing generation must disclose call counts.

## Prompt-injection posture

Candidate CVs and job postings are untrusted input embedded in prompts. Mitigations: outputs are parsed against strict contracts (JSON extractors, fit-score regex) and rendered as text (never executed); trust scores are computed in code so a malicious posting cannot talk the model into "this employer is safe"; profile updates from chat accept only known keys. When adding a new AI function, define its output contract first and parse defensively.

## Cost model

~$0.02/application (3 calls with reviewer pass) — see `business/unit-economics.xlsx`. Free tier: 20 req/day → friendly 429 messages are mandatory on every handler path.

## Acceptance criteria

- `test_e2e.py` passes with `FakeModel` — no network.
- Prompt regression: built prompts contain the skill marker phrases.
- Grepping `core.py`/`verify.py` for `genai` returns nothing.

## Future extensions

- Prompt versioning metadata (skill file header: version + changelog line).
- Embedding-based pre-filter before `match_jobs` (Gemini Embedding + pgvector) to cut LLM calls per matching run.
