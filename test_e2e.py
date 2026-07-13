"""End-to-end test of Emploi core logic with a fake Gemini model.
Run: python3 test_e2e.py
"""

import sys

from core import (batch_generate, build_cv_prompt, build_interview_prompt,
                  build_match_prompt, build_prompt, build_review_prompt,
                  classify_document, detect_intent, extract_jobs,
                  extract_profile, generate_application, generate_cv,
                  guess_columns, load_skill, make_docx, make_pdf, match_jobs,
                  parse_fit_score, parse_json_array, parse_profile_json,
                  pdf_to_text, resolve_job)

PROFILE = {
    "name": "Joy Adeniran", "title": "Product Engineer",
    "location": "Remote (Lagos)", "experience": "Built Supplya, a B2B BNPL platform...",
    "skills": "Python, React, Node, product strategy",
    "education": "BSc Computer Science", "goals": "Remote senior product/eng roles",
}

CANNED = """## Cover Letter
Dear Hiring Manager, I am excited to apply...

## CV Bullet Points
- Built a B2B BNPL platform serving informal retailers
- Led cross-functional product delivery

## Fit Score
Fit Score: {score}/100 — strong overlap on product + Python."""

PROFILE_JSON = """Here is the profile:
```json
{"name": "Joy Adeniran", "title": "Product Engineer", "location": "Lagos",
 "experience": "Supplya, Eduwalls", "skills": "Python, React",
 "education": "BSc CS", "goals": ""}
```"""


class FakeModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate_content(self, prompt):
        self.calls.append(prompt)
        text = self.responses.pop(0) if self.responses else CANNED.format(score=50)
        class R: pass
        r = R(); r.text = text
        return r


def check(label, cond):
    print(("PASS" if cond else "FAIL"), "-", label)
    return cond


ok = True

# 1. Fit score parsing
ok &= check("parse_fit_score extracts 78", parse_fit_score("blah Fit Score: 78/100 x") == 78)
ok &= check("parse_fit_score handles missing", parse_fit_score("no score here") is None)
ok &= check("parse_fit_score rejects >100", parse_fit_score("Fit Score: 300/100") is None)

# 2. Prompt building + skills injection
ok &= check("skill files load", all(len(load_skill(s)) > 200 for s in
            ["writing_style", "evaluation", "interview_prep"]))
p = build_prompt(PROFILE, "We need a Python engineer", "Acme")
ok &= check("prompt contains profile + JD + company",
            "Joy Adeniran" in p and "Python engineer" in p and "Acme" in p)
ok &= check("generation prompt embeds style guide + rubric",
            "NO em-dashes" in p and "weight 30%" in p)
rp = build_review_prompt(PROFILE, "JD text", "draft text")
ok &= check("review prompt embeds draft", "draft text" in rp)
ok &= check("review prompt enforces style guide", "NO em-dashes" in rp)
mp = build_match_prompt(PROFILE, [{"company": "Acme", "title": "VA", "description": "x"}])
ok &= check("match prompt embeds rubric", "weight 30%" in mp)
ip = build_interview_prompt(PROFILE, "JD here", "Acme")
ok &= check("interview prompt embeds skill + profile",
            "STAR" in ip and "Joy Adeniran" in ip and "JD here" in ip)
cp = build_cv_prompt(PROFILE, "JD here", "Acme")
ok &= check("cv prompt embeds cv skill + style + profile + JD",
            "Relevance-weighted" in cp and "NO em-dashes" in cp
            and "Joy Adeniran" in cp and "JD here" in cp)
m = FakeModel(["# Joy Adeniran\n## Professional Summary\nMarketing leader..."])
ok &= check("generate_cv returns model text", "Professional Summary" in generate_cv(m, PROFILE, "JD"))

# 3. Single generation, no review (1 API call)
m = FakeModel([CANNED.format(score=70)])
app = generate_application(m, PROFILE, "JD", "Acme", review=False)
ok &= check("no-review = 1 model call", len(m.calls) == 1)
ok &= check("fit score parsed (70)", app["fit_score"] == 70)
ok &= check("company recorded", app["company"] == "Acme")

# 4. Reviewer pass (2 API calls, draft kept)
m = FakeModel([CANNED.format(score=60), CANNED.format(score=85)])
app = generate_application(m, PROFILE, "JD", "Acme", review=True)
ok &= check("review = 2 model calls", len(m.calls) == 2)
ok &= check("final fit score from reviewed version (85)", app["fit_score"] == 85)
ok &= check("original draft preserved", "60/100" in app["draft"])

# 5. Batch mode: ranking + limit + skip empty JDs
jobs = [
    {"jd": "Role A description with details", "co": "Alpha"},
    {"jd": "", "co": "EmptyCo"},
    {"jd": "Role B description with details", "co": "Beta"},
    {"jd": "Role C description with details", "co": "Gamma"},
]
m = FakeModel([CANNED.format(score=40), CANNED.format(score=90)])
results = batch_generate(m, PROFILE, jobs, "jd", "co", review=False, limit=3)
ok &= check("batch skips empty JD + respects limit", len(results) == 2)
ok &= check("batch ranked best-first", results[0]["company"] == "Beta"
            and results[0]["fit_score"] == 90)

# 6. Column guessing
jd_col, co_col = guess_columns(jobs)
ok &= check("guess_columns finds longest text col", jd_col == "jd")
ok &= check("guess_columns finds company col", co_col == "co")

# 7. CV profile extraction (fenced JSON tolerated)
prof = parse_profile_json(PROFILE_JSON)
ok &= check("profile JSON parsed from fenced output", prof.get("name") == "Joy Adeniran")
ok &= check("profile has all keys as strings",
            all(isinstance(prof.get(k), str) for k in PROFILE))
m = FakeModel([PROFILE_JSON])
prof2 = extract_profile(m, "CV TEXT HERE")
ok &= check("extract_profile sends CV text to model", "CV TEXT HERE" in m.calls[0])
ok &= check("extract_profile returns profile", prof2.get("skills") == "Python, React")
ok &= check("parse_profile_json handles garbage", parse_profile_json("not json") == {})

# 7b. Document classification + job extraction + matching
ok &= check("classify: CV", classify_document(FakeModel(["CV"]), "x") == "cv")
ok &= check("classify: JOBS", classify_document(FakeModel(["JOBS"]), "x") == "jobs")
ok &= check("classify: junk -> other", classify_document(FakeModel(["banana"]), "x") == "other")

JOBS_JSON = """```json
[{"company": "Acme", "title": "VA", "description": "Remote VA role, apply via email"},
 {"company": "Globex", "title": "Writer", "description": "Content writer, remote"},
 {"company": "NoDesc", "title": "x", "description": ""}]
```"""
jobs_x = extract_jobs(FakeModel([JOBS_JSON]), "doc")
ok &= check("extract_jobs parses + drops empty descriptions", len(jobs_x) == 2
            and jobs_x[0]["company"] == "Acme")

MATCH_JSON = '[{"index": 0, "fit_score": 45, "reason": "meh"}, {"index": 1, "fit_score": 91, "reason": "great"}]'
ranked = match_jobs(FakeModel([MATCH_JSON]), PROFILE, jobs_x)
ok &= check("match_jobs ranks best-first", ranked[0]["company"] == "Globex"
            and ranked[0]["fit_score"] == 91)
ok &= check("match_jobs keeps reasons", ranked[0]["reason"] == "great")

ok &= check("resolve_job by number", resolve_job("1", ranked)["company"] == "Globex")
ok &= check("resolve_job by '#2'", resolve_job("#2", ranked)["company"] == "Acme")
ok &= check("resolve_job by company name", resolve_job("acme", ranked)["company"] == "Acme")
ok &= check("resolve_job miss -> None", resolve_job("zzz", ranked) is None)
ok &= check("parse_json_array handles garbage", parse_json_array("nope") == [])

# 7c. Conversational chat turn: context + profile updates
from core import chat_turn
CHAT_JSON = '{"reply": "Great goal, noted!", "profile_updates": {"goals": "Senior Marketing Manager roles", "bogus_key": "x", "title": ""}}'
reply, updates = chat_turn(FakeModel([CHAT_JSON]), PROFILE, "I want senior marketing roles", "user: hi")
ok &= check("chat_turn parses reply", reply == "Great goal, noted!")
ok &= check("chat_turn keeps only valid non-empty profile keys",
            updates == {"goals": "Senior Marketing Manager roles"})
reply, updates = chat_turn(FakeModel(["plain text answer, no JSON"]), PROFILE, "hi")
ok &= check("chat_turn falls back to raw text", reply.startswith("plain text") and updates == {})
m = FakeModel([CHAT_JSON])
chat_turn(m, PROFILE, "question", "user: earlier\nassistant: earlier reply")
ok &= check("chat prompt includes history + question",
            "earlier reply" in m.calls[0] and "question" in m.calls[0])

# 8. Intent routing
ok &= check("pdf upload -> process_pdf", detect_intent("", has_pdf=True)[0] == "process_pdf")
ok &= check("'apply 2' -> apply('2')", detect_intent("apply 2") == ("apply", "2"))
ok &= check("'apply to Acme' -> apply('Acme')", detect_intent("apply to Acme") == ("apply", "Acme"))
ok &= check("'find a match' -> match", detect_intent("find a match")[0] == "match")
ok &= check("'/verify email' -> verify",
            detect_intent("/verify holla@suplya.shop") == ("verify", "holla@suplya.shop"))
ok &= check("'verify 2' -> verify('2')", detect_intent("verify 2") == ("verify", "2"))
ok &= check("'/apply 2' slash tolerated", detect_intent("/apply 2") == ("apply", "2"))
ok &= check("'/batch 3' slash tolerated", detect_intent("/batch 3") == ("batch", 3))
ok &= check("'/tracker' slash tolerated", detect_intent("/tracker")[0] == "tracker")
ok &= check("'interview' -> interview(None)", detect_intent("interview") == ("interview", None))
ok &= check("'prep me for 2' -> interview('2')", detect_intent("prep me for 2") == ("interview", "2"))
ok &= check("'interview Acme' -> interview('Acme')", detect_intent("interview Acme") == ("interview", "Acme"))
ok &= check("'read these and find a match' -> match",
            detect_intent("Read these job listings and find a match")[0] == "match")
ok &= check("sheet upload -> import_jobs", detect_intent("", has_sheet=True)[0] == "import_jobs")
ok &= check("'batch 7' -> batch(7)", detect_intent("batch 7") == ("batch", 7))
ok &= check("'batch' defaults to 5", detect_intent("Batch") == ("batch", 5))
ok &= check("'tracker' -> tracker", detect_intent("show my tracker")[0] == "tracker")
jd_text = ("We are looking for a senior engineer. Responsibilities include X. "
           "Requirements: Python. " + "More detail. " * 40)
ok &= check("long JD text -> generate", detect_intent(jd_text)[0] == "generate")
ok &= check("short question -> chat", detect_intent("how do I negotiate salary?")[0] == "chat")

# 9. PDF roundtrip: build a CV pdf with fpdf, read it back with pypdf
cv_pdf = make_pdf("Joy Adeniran\nProduct Engineer\nSkills: Python, React")
ok &= check("PDF bytes valid", cv_pdf[:5] == b"%PDF-" and len(cv_pdf) > 500)
extracted = pdf_to_text(cv_pdf)
ok &= check("pdf_to_text roundtrip", "Joy Adeniran" in extracted and "Python" in extracted)

# 9b. Markdown must be RENDERED in exports, not dumped raw (was a real bug)
MD = """## Cover Letter
Dear Team, I closed ₦2m in sales — **measurable** impact.

*   **Brand Strategy:** built identity across channels
- Led launches

| Dimension | Score |
|-----------|-------|
| Skills | 55 |

Fit Score: 72/100"""
rendered = pdf_to_text(make_pdf(MD))
ok &= check("PDF: no raw markdown tokens",
            "##" not in rendered and "**" not in rendered and "|" not in rendered)
ok &= check("PDF: content survives rendering",
            "Cover Letter" in rendered and "Brand Strategy" in rendered
            and "Skills" in rendered and "72/100" in rendered)
ok &= check("PDF: naira encoded readably", "NGN" in rendered and "?" not in rendered.split("Fit")[0])
ok &= check("DOCX: renders same markdown", make_docx(MD)[:2] == b"PK")

# 9c. Downloads must exclude the fit evaluation (sendable content only)
from core import strip_evaluation
APP_MD = MD.replace("| Dimension | Score |", "## Fit Evaluation\n| Dimension | Score |")
stripped = strip_evaluation(APP_MD)
ok &= check("strip_evaluation removes fit section",
            "Fit Evaluation" not in stripped and "72/100" not in stripped
            and "Dear Team" in stripped)
ok &= check("strip_evaluation handles old '## Fit Score' header",
            "88/100" not in strip_evaluation(CANNED.format(score=88)))
ok &= check("strip_evaluation is a no-op without the section",
            strip_evaluation("## Cover Letter\nhi") == "## Cover Letter\nhi")
ok &= check("strip_evaluation survives None/empty", strip_evaluation("") == "")

# 10. DOCX export
docx = make_docx(CANNED.format(score=88), title="Application - Acme")
ok &= check("DOCX bytes valid (zip magic)", docx[:2] == b"PK" and len(docx) > 1000)

# 11. Career Twin extraction (wizard-schema, normalized)
from core import (parse_career_twin_json, normalize_skills, normalize_entries,
                  normalize_experience_years, build_career_twin_extraction_prompt,
                  extract_career_twin, _profile_block)

ok &= check("twin: fenced JSON parsed + normalized",
            parse_career_twin_json(
                '```json\n{"name":"Ada","headline":"Designer",'
                '"experience_years":4,"skills":["Figma","UX"]}\n```')
            == {"name": "Ada", "headline": "Designer", "current_role": "",
                "location": "", "bio": "", "skills": ["Figma", "UX"],
                "experience_years": "4 years", "experience": [], "education": []})
ok &= check("twin: garbage -> {}", parse_career_twin_json("not json") == {})
ok &= check("twin: empty object -> {} (failed extraction, not a twin)",
            parse_career_twin_json('{"name":"","skills":[]}') == {})
ok &= check("twin: skills comma string -> list",
            normalize_skills("Python, SQL; Excel") == ["Python", "SQL", "Excel"])
ok &= check("twin: skills list passthrough + cleanup",
            normalize_skills([" Figma ", "", 42]) == ["Figma", "42"])
ok &= check("twin: skills garbage -> []", normalize_skills({"a": 1}) == [])
ok &= check("twin: years 1 -> '1 year'", normalize_experience_years(1) == "1 year")
ok &= check("twin: years 4 -> '4 years'", normalize_experience_years("4") == "4 years")
ok &= check("twin: years '7 years' -> bucket", normalize_experience_years("7 years") == "6–10 years")
ok &= check("twin: years 12 -> '10+ years'", normalize_experience_years(12) == "10+ years")
ok &= check("twin: years garbage -> ''", normalize_experience_years("unknown") == "")
ok &= check("twin: years 0 -> ''", normalize_experience_years(0) == "")
ok &= check("twin prompt: carries ground-truth constraint",
            "Never invent" in build_career_twin_extraction_prompt("cv"))
ok &= check("twin prompt: asks for wizard keys",
            all(k in build_career_twin_extraction_prompt("cv")
                for k in ["headline", "current_role", "experience_years", "bio",
                          "experience", "education"]))

# 11a. Structured experience/education entries (HANDOVER §gap: these were
# never extracted at all before; the wizard's Career Twin page has always
# expected [{"summary": "..."}] but nothing produced it).
ok &= check("normalize_entries: dicts with summary kept",
            normalize_entries([{"summary": "PM at Acme (2020-2023)"}, {"summary": ""}])
            == [{"summary": "PM at Acme (2020-2023)"}])
ok &= check("normalize_entries: plain strings coerced to {summary}",
            normalize_entries(["BSc Physics, UNILAG"]) == [{"summary": "BSc Physics, UNILAG"}])
ok &= check("normalize_entries: single string -> one-item list",
            normalize_entries("Just one line") == [{"summary": "Just one line"}])
ok &= check("normalize_entries: garbage -> []", normalize_entries(42) == [])
ok &= check("normalize_entries: caps at MAX_TWIN_ENTRIES",
            len(normalize_entries([{"summary": f"role {i}"} for i in range(30)])) == 15)

ok &= check("twin: experience/education parsed from fenced JSON",
            parse_career_twin_json(
                '{"name":"Ada","experience":[{"summary":"Designer at Acme"}],'
                '"education":[{"summary":"BSc Design"}]}')
            == {"name": "Ada", "headline": "", "current_role": "", "location": "",
                "bio": "", "skills": [], "experience_years": "",
                "experience": [{"summary": "Designer at Acme"}],
                "education": [{"summary": "BSc Design"}]})

class _TwinModel:
    def generate_content(self, prompt):
        class R: text = '{"name":"Tolu","skills":"Go, Rust","experience_years":6}'
        return R()

ok &= check("extract_career_twin: end-to-end with fake model",
            extract_career_twin(_TwinModel(), "cv text")
            == {"name": "Tolu", "headline": "", "current_role": "",
                "location": "", "bio": "", "skills": ["Go", "Rust"],
                "experience_years": "6–10 years", "experience": [], "education": []})

# 11b. _profile_block must render a Career Twin (wizard schema) correctly —
# regression for the bug where PROFILE_KEYS (title/experience/education/goals)
# silently rendered "None" for every wizard-onboarded user's generated
# applications, since the wizard uses headline/current_role/bio/career_goals
# and structured experience/education entries instead.
TWIN_PROFILE = {
    "name": "Joy Adeniran", "headline": "Marketing Manager", "current_role": "MM at Acme",
    "location": "Lagos", "bio": "8 years building brands and driving demand.",
    "skills": ["Brand Building", "Demand Generation"],
    "experience": [{"summary": "Marketing Manager at Acme (2019-2023)"}],
    "education": [{"summary": "BSc Marketing, UNILAG"}],
    "career_goals": ["Career Growth", "Remote work"],
}
twin_block = _profile_block(TWIN_PROFILE)
ok &= check("_profile_block: wizard headline used as title", "Marketing Manager" in twin_block)
ok &= check("_profile_block: wizard skills list joined", "Brand Building" in twin_block and "Demand Generation" in twin_block)
ok &= check("_profile_block: structured experience entry rendered",
            "Marketing Manager at Acme (2019-2023)" in twin_block)
ok &= check("_profile_block: structured education entry rendered", "BSc Marketing, UNILAG" in twin_block)
ok &= check("_profile_block: career_goals rendered as goals", "Career Growth" in twin_block and "Remote work" in twin_block)
ok &= check("_profile_block: no field silently renders 'None'", "None" not in twin_block)

# When a wizard twin has no structured experience, fall back to bio rather
# than an empty "Experience:" line.
BIO_ONLY_TWIN = {"name": "Ada", "headline": "Designer", "bio": "Ships pixel-perfect UI.", "skills": []}
ok &= check("_profile_block: falls back to bio when no structured experience",
            "Ships pixel-perfect UI." in _profile_block(BIO_ONLY_TWIN))

# The legacy flat-string profile schema (still used by the Streamlit
# extract_profile path) must keep working unchanged.
ok &= check("_profile_block: legacy flat-string schema unaffected", "None" not in _profile_block(PROFILE))

from core import admin_allowed
ok &= check("admin_allowed: no allowlist configured = unrestricted",
            admin_allowed("anyone@x.com", "") and admin_allowed("anyone@x.com", None))
ok &= check("admin_allowed: listed email passes (case/space-insensitive)",
            admin_allowed("Joy@EmploiHQ.com", " joy@emploihq.com , ops@emploihq.com "))
ok &= check("admin_allowed: unlisted email blocked",
            not admin_allowed("attacker@evil.com", "joy@emploihq.com"))
ok &= check("admin_allowed: empty email blocked when allowlist set",
            not admin_allowed("", "joy@emploihq.com")
            and not admin_allowed(None, "joy@emploihq.com"))

print("\n" + ("ALL TESTS PASSED ✅" if ok else "SOME TESTS FAILED ❌"))
sys.exit(0 if ok else 1)
