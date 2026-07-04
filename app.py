import os

import pandas as pd
import streamlit as st
import google.generativeai as genai

from core import (PROFILE_KEYS, batch_generate, chat_turn,
                  classify_document, detect_intent, extract_jobs,
                  extract_profile, generate_application, guess_columns,
                  generate_cv, make_docx, make_pdf, match_jobs, pdf_to_text,
                  prepare_interview, resolve_job, strip_evaluation)


def friendly_error(e):
    s = str(e)
    if "429" in s or "quota" in s.lower():
        m = __import__("re").search(r"retry in (\d+)", s)
        wait = f" Try again in ~{m.group(1)}s." if m else ""
        return ("⏳ The Gemini API quota is exhausted (free tier allows only 20 "
                f"requests/day).{wait} For real usage, enable billing on the API "
                "key — each application costs well under $0.01.")
    return f"Gemini error: {e}"
from verify import extract_domain, verify_employer

st.set_page_config(page_title="Emploi", layout="centered")


def get_server_key():
    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        try:
            key = st.secrets.get("GEMINI_API_KEY", "")
        except Exception:
            key = ""
    return key


# ---------------- Session state ----------------
st.session_state.setdefault("profile", {})
st.session_state.setdefault("applications", [])
st.session_state.setdefault("jobs", [])
st.session_state.setdefault("matches", [])
st.session_state.setdefault("messages", [])
st.session_state.setdefault("verify_cache", {})

# ---------------- Sidebar ----------------
SERVER_KEY = get_server_key()
with st.sidebar:
    st.header("💼 Emploi")
    if SERVER_KEY:
        api_key = SERVER_KEY
        st.success("Connected")
    else:
        api_key = st.text_input("Gemini API key (dev mode)", type="password")
        st.caption("In production, set GEMINI_API_KEY as a server secret — users never see this field.")
    model_name = st.selectbox("Model", ["gemini-2.5-flash", "gemini-2.5-pro"])
    reviewer_pass = st.toggle("Reviewer pass (better quality, 2x calls)", value=True)
    st.caption("Each application = cover letter + tailored CV "
               f"({3 if reviewer_pass else 2} API calls).")
    if api_key:
        genai.configure(api_key=api_key)

    st.divider()
    done = sum(1 for k in PROFILE_KEYS if st.session_state.profile.get(k))
    st.caption(f"Profile: {done}/{len(PROFILE_KEYS)} fields · "
               f"Jobs loaded: {len(st.session_state.jobs)} · "
               f"Applications: {len(st.session_state.applications)}")
    if st.session_state.profile:
        with st.expander("Edit profile"):
            for k in PROFILE_KEYS:
                st.session_state.profile[k] = st.text_area(
                    k.title(), st.session_state.profile.get(k, ""), height=68,
                    key=f"pf_{k}")
    if st.button("Clear all data"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()


def get_model():
    return genai.GenerativeModel(model_name)


def say(role, content, payload=None):
    st.session_state.messages.append(
        {"role": role, "content": content, "payload": payload})


def log_application(app):
    st.session_state.applications.append(
        {"date": app["date"], "company": app["company"],
         "fit_score": app["fit_score"], "status": "Generated"})


def render_downloads(result_text, company, key):
    base = f"emploi_{(company or 'application').replace(' ', '_')}"
    c1, c2, c3 = st.columns(3)
    c1.download_button("⬇️ PDF", make_pdf(result_text), f"{base}.pdf",
                       "application/pdf", key=f"{key}_pdf")
    c2.download_button("⬇️ Word", make_docx(result_text, title=f"Application — {company or 'Role'}"),
                       f"{base}.docx",
                       "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                       key=f"{key}_docx")
    c3.download_button("⬇️ Text", result_text, f"{base}.txt", "text/plain",
                       key=f"{key}_txt")


TRUST_BADGE = {"High trust": "🟢", "Medium trust": "🟡", "Low trust": "🟠", "Avoid": "🔴"}


def verify_job(job):
    return verify_employer(
        job.get("company", ""), job.get("contact", ""),
        job.get("description", ""), job.get("title", ""),
        model=get_model(), cache=st.session_state.verify_cache)


def trust_line(v):
    return f"{TRUST_BADGE.get(v['level'], '⚪')} {v['level']} ({v['score']}/100)"


def render_message(i, msg):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        p = msg.get("payload") or {}
        if p.get("type") == "application":
            with st.expander(f"📄 {p['company']} — cover letter & evaluation", expanded=p.get("expand", False)):
                st.markdown(p["result"])
            st.caption("Downloads contain only the sendable cover letter — the evaluation stays here.")
            render_downloads(strip_evaluation(p["result"]), p["company"], f"m{i}")
            if p.get("cv"):
                with st.expander(f"📋 {p['company']} — tailored CV"):
                    st.markdown(p["cv"])
                render_downloads(p["cv"], f"{p['company']}_CV", f"m{i}cv")
        elif p.get("type") == "batch":
            for j, r in enumerate(p["results"]):
                score = f"{r['fit_score']}/100" if r["fit_score"] is not None else "n/a"
                with st.expander(f"#{j+1} · {r['company']} · Fit {score}"):
                    st.markdown(r["result"])
                    render_downloads(strip_evaluation(r["result"]), r["company"], f"m{i}b{j}")
        elif p.get("type") == "profile":
            st.table(pd.DataFrame(
                [(k.title(), (p["profile"].get(k) or "")[:120]) for k in PROFILE_KEYS],
                columns=["Field", "Value"]).set_index("Field"))
        elif p.get("type") == "matches":
            rows = [{"#": j + 1, "Company": r.get("company") or "?",
                     "Role": r.get("title") or "?",
                     "Fit": f"{r['fit_score']}/100" if r["fit_score"] is not None else "n/a",
                     "Trust": f"{TRUST_BADGE.get(r.get('trust_level'), '⚪')} "
                              f"{r.get('trust_score', '—')}",
                     "Why": r.get("reason", "")}
                    for j, r in enumerate(p["matches"])]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            st.caption("Trust = automated employer verification (domain, website, scam patterns). "
                       "Type **verify 2** for the full evidence on any job.")
        elif p.get("type") == "verification":
            v = p["verification"]
            st.markdown(f"**{trust_line(v)}**" +
                        (f" · domain: `{v['domain']}`" if v.get("domain") else ""))
            for line in v["evidence"]:
                st.markdown(f"- {line}")
        elif p.get("type") == "tracker":
            df = pd.DataFrame(p["rows"])
            st.dataframe(df, use_container_width=True)
            st.download_button("⬇️ Export CSV", df.to_csv(index=False),
                               "emploi_tracker.csv", "text/csv", key=f"m{i}_csv")


def annotate_trust(matches):
    for r in matches:
        try:
            v = verify_job(r)
            r["trust_score"], r["trust_level"] = v["score"], v["level"]
        except Exception:
            r["trust_score"], r["trust_level"] = None, None
    return matches


def handle_pdf(pdf_file, user_text):
    doc_text = pdf_to_text(pdf_file.getvalue())
    if len(doc_text.strip()) < 50:
        say("assistant", "I couldn't extract text from that PDF — it may be a scanned image. "
                         "Try an exported (not scanned) PDF, or paste the content here as text.")
        return

    kind = classify_document(get_model(), doc_text)
    wants_jobs = bool(detect_intent(user_text)[0] == "match" or
                      "job" in (user_text or "").lower())
    if kind == "cv" and not wants_jobs:
        profile = extract_profile(get_model(), doc_text)
        if profile.get("name") or profile.get("experience"):
            st.session_state.profile = profile
            say("assistant",
                "Read your CV — here's the profile I built. Edit any field in the sidebar, "
                "or send me job listings (PDF, sheet, or pasted text) to start matching.",
                {"type": "profile", "profile": profile})
        else:
            say("assistant", "That looks like a CV but I couldn't structure it. "
                             "Paste the key details here and I'll build your profile from chat.")
    elif kind == "jobs" or wants_jobs:
        jobs = extract_jobs(get_model(), doc_text)
        if not jobs:
            say("assistant", "I could read the PDF but couldn't find distinct job postings in it. "
                             "Paste one job's text directly and I'll take it from there.")
            return
        st.session_state.jobs = jobs
        if st.session_state.profile:
            matches = annotate_trust(
                match_jobs(get_model(), st.session_state.profile, jobs))
            st.session_state.matches = matches
            best = matches[0]
            say("assistant",
                f"Found **{len(jobs)} jobs** in that PDF, ranked them against your profile, "
                f"and verified each employer. Best match: "
                f"**{best.get('company') or best.get('title')}** ({best['fit_score']}/100). "
                "Type **apply 1** to generate the application, or **verify 1** for the evidence.",
                {"type": "matches", "matches": matches})
        else:
            say("assistant",
                f"Found **{len(jobs)} jobs** in that PDF. Drop your CV first so I can rank them "
                "against your profile, or type **apply 1** to apply to one directly.")
    else:
        say("assistant", "I read that PDF but it doesn't look like a CV or job listings. "
                         "What would you like me to do with it?")


def do_apply(job):
    jd = job.get("description") or ""
    if not jd:
        jd_col, _ = guess_columns([job])
        jd = str(job.get(jd_col, ""))
    company = job.get("company") or ""
    st.session_state.last_jd, st.session_state.last_company = jd, company
    app = generate_application(get_model(), st.session_state.profile, jd,
                               company, review=reviewer_pass)
    cv = generate_cv(get_model(), st.session_state.profile, jd, company)
    log_application(app)
    score = f" Fit score: **{app['fit_score']}/100**." if app["fit_score"] is not None else ""
    say("assistant",
        f"Application for **{app['company']}** ready"
        f"{' (reviewer-improved)' if app['reviewed'] else ''}.{score} "
        "Cover letter and a complete tailored CV below — both downloadable. Logged to your tracker.",
        {"type": "application", "company": app["company"],
         "result": app["result"], "cv": cv, "expand": True})


# ---------------- Greeting ----------------
if not st.session_state.messages:
    say("assistant",
        "Hi, I'm **Emploi** — your job application agent.\n\n"
        "1. 📎 **Drop your CV (PDF)** — I'll build your profile automatically\n"
        "2. 📋 **Drop job listings** — a PDF of postings or a CSV/Excel sheet; I'll rank them by fit\n"
        "3. ✨ **Paste a job description** — I'll draft a tailored cover letter + CV bullets\n"
        "4. ⚡ **apply 2** / **apply Acme** — apply to a ranked job · **batch 5** — apply across a sheet\n"
        "5. 🛡️ **verify 2** / **verify info@company.com** — employer trust check (scam protection)\n"
        "6. 🎤 **interview** — STAR prep for the last role (or **interview 2** for a ranked one)\n"
        "7. 📊 **tracker** — everything you've generated\n\n"
        "Start by dropping your CV 👇")

for i, msg in enumerate(st.session_state.messages):
    render_message(i, msg)

# ---------------- Chat input ----------------
user_input = st.chat_input(
    "Drop a CV or job listings, paste a job description, or type 'apply 1'…",
    accept_file=True, file_type=["pdf", "csv", "xlsx"])

if user_input:
    text = user_input.text or ""
    files = user_input.files or []
    pdf_file = next((f for f in files if f.name.lower().endswith(".pdf")), None)
    sheet_file = next((f for f in files if f.name.lower().endswith((".csv", ".xlsx"))), None)

    shown = " ".join(x for x in [text, pdf_file and f"📎 {pdf_file.name}",
                                 sheet_file and f"📎 {sheet_file.name}"] if x)
    say("user", shown)

    intent, arg = detect_intent(text, has_pdf=bool(pdf_file), has_sheet=bool(sheet_file))

    if not api_key and intent != "tracker":
        say("assistant", "No API key configured. Add GEMINI_API_KEY (or use the sidebar field in dev mode), then resend.")

    elif intent == "process_pdf":
        with st.spinner("Reading the PDF..."):
            try:
                handle_pdf(pdf_file, text)
            except Exception as e:
                say("assistant", friendly_error(e))

    elif intent == "import_jobs":
        try:
            df = pd.read_csv(sheet_file) if sheet_file.name.endswith(".csv") else pd.read_excel(sheet_file)
            st.session_state.jobs = df.to_dict("records")
            st.session_state.matches = []
            jd_col, co_col = guess_columns(st.session_state.jobs)
            say("assistant",
                f"Loaded **{len(df)} jobs** from {sheet_file.name} "
                f"(descriptions from **{jd_col}**"
                + (f", companies from **{co_col}**" if co_col else "") + "). "
                "Type **match** to rank them against your profile, or **batch 5** to apply across them.")
        except Exception as e:
            say("assistant", f"Couldn't read that file: {e}")

    elif intent == "match":
        if not st.session_state.profile:
            say("assistant", "Drop your CV (PDF) first so I know what to match against.")
        elif not st.session_state.jobs:
            say("assistant", "No jobs loaded yet — drop a job-listings PDF or a CSV/Excel sheet.")
        else:
            with st.spinner("Ranking jobs against your profile..."):
                try:
                    jobs = st.session_state.jobs
                    if "description" not in (jobs[0] if jobs else {}):
                        jd_col, co_col = guess_columns(jobs)
                        jobs = [{"company": str(j.get(co_col, "") or "") if co_col else "",
                                 "title": "", "description": str(j.get(jd_col, "") or "")}
                                for j in jobs]
                    matches = annotate_trust(
                        match_jobs(get_model(), st.session_state.profile, jobs))
                    st.session_state.matches = matches
                    say("assistant",
                        "Ranked by fit, employers verified — type **apply 1** to generate "
                        "an application or **verify 1** for the evidence:",
                        {"type": "matches", "matches": matches})
                except Exception as e:
                    say("assistant", friendly_error(e))

    elif intent == "apply":
        pool = st.session_state.matches or st.session_state.jobs
        if not st.session_state.profile:
            say("assistant", "Drop your CV (PDF) first so I can tailor the application.")
        elif not pool:
            say("assistant", "No jobs loaded — drop job listings or paste the job description directly.")
        else:
            job = resolve_job(arg, pool)
            if not job:
                say("assistant", f"Couldn't find a job matching “{arg}”. "
                                 "Type **match** to see the numbered list.")
            else:
                with st.spinner("Verifying the employer, then drafting..."):
                    try:
                        v = verify_job(job)
                        if v["level"] in ("Low trust", "Avoid"):
                            say("assistant",
                                f"⚠️ Heads-up before you send anything: {trust_line(v)}. "
                                "Never pay a fee or share bank/ID details with this contact.",
                                {"type": "verification", "verification": v})
                        do_apply(job)
                    except Exception as e:
                        say("assistant", friendly_error(e))

    elif intent == "batch":
        if not st.session_state.profile:
            say("assistant", "I need your profile first — drop your CV (PDF) here.")
        elif not st.session_state.jobs:
            say("assistant", "No jobs loaded yet — drop a job sheet or listings PDF first.")
        else:
            jd_col, co_col = guess_columns(st.session_state.jobs)
            n = min(arg, len(st.session_state.jobs), 25)
            with st.spinner(f"Applying to {n} jobs..."):
                try:
                    results = batch_generate(get_model(), st.session_state.profile,
                                             st.session_state.jobs, jd_col, co_col,
                                             review=reviewer_pass, limit=n)
                    for r in results:
                        log_application(r)
                    say("assistant",
                        f"Done — **{len(results)} applications**, ranked best fit first:",
                        {"type": "batch", "results": results})
                except Exception as e:
                    say("assistant", friendly_error(e))

    elif intent == "tracker":
        if st.session_state.applications:
            say("assistant", "Everything you've generated so far:",
                {"type": "tracker", "rows": st.session_state.applications})
        else:
            say("assistant", "Nothing tracked yet — paste a job description to make your first application.")

    elif intent == "verify":
        pool = st.session_state.matches or st.session_state.jobs
        job = resolve_job(arg, pool) if pool else None
        with st.spinner("Checking domain, website, and scam patterns..."):
            try:
                if job:
                    v = verify_job(job)
                elif extract_domain(arg):
                    v = verify_employer(arg, arg, model=get_model(),
                                        cache=st.session_state.verify_cache)
                else:
                    v = None
                if v:
                    say("assistant", f"Verification for **{v['company'] or arg}**:",
                        {"type": "verification", "verification": v})
                else:
                    say("assistant", f"Couldn't find “{arg}” in the loaded jobs. "
                                     "Use a match number, a company name, or paste an "
                                     "email/website to verify directly.")
            except Exception as e:
                say("assistant", friendly_error(e))

    elif intent == "interview":
        if not st.session_state.profile:
            say("assistant", "Drop your CV (PDF) first so I can build prep from your real experience.")
        else:
            pool = st.session_state.matches or st.session_state.jobs
            job = resolve_job(arg, pool) if arg and pool else None
            jd = (job.get("description") if job else None) or st.session_state.get("last_jd")
            company = (job.get("company") if job else None) or st.session_state.get("last_company", "")
            if not jd:
                say("assistant", "Which role? Apply to a job first, or say **interview 2** / "
                                 "**interview Acme** after a match, or paste the job description.")
            else:
                with st.spinner("Building your interview prep..."):
                    try:
                        prep = prepare_interview(get_model(), st.session_state.profile, jd, company)
                        say("assistant", f"Interview prep for **{company or 'the role'}** — "
                                         "STAR stories from your real experience, tough questions, "
                                         "and what to ask them:",
                            {"type": "application", "company": f"{company or 'role'}_interview_prep",
                             "result": prep, "expand": True})
                    except Exception as e:
                        say("assistant", friendly_error(e))

    elif intent == "generate":
        if not st.session_state.profile:
            say("assistant", "Before I tailor an application, drop your CV (PDF) so I know your background.")
        else:
            st.session_state.last_jd, st.session_state.last_company = text, ""
            with st.spinner("Drafting cover letter, tailored CV, and evaluation..."):
                try:
                    app = generate_application(get_model(), st.session_state.profile,
                                               text, "", review=reviewer_pass)
                    cv = generate_cv(get_model(), st.session_state.profile, text, "")
                    log_application(app)
                    score = f" Fit score: **{app['fit_score']}/100**." if app["fit_score"] is not None else ""
                    say("assistant",
                        f"Application ready{' (reviewer-improved)' if app['reviewed'] else ''}.{score} "
                        "Cover letter and a complete tailored CV below — both downloadable. "
                        "Logged to your tracker.",
                        {"type": "application", "company": app["company"],
                         "result": app["result"], "cv": cv, "expand": True})
                except Exception as e:
                    say("assistant", friendly_error(e))

    else:  # chat — conversational, context-aware, can update the profile
        with st.spinner("Thinking..."):
            try:
                history = "\n".join(
                    f"{m['role']}: {str(m['content'])[:300]}"
                    for m in st.session_state.messages[-8:-1])
                reply, updates = chat_turn(get_model(), st.session_state.profile,
                                           text, history)
                if updates:
                    st.session_state.profile.update(updates)
                    reply += ("\n\n📝 *Updated your profile: "
                              + ", ".join(f"**{k}**" for k in updates)
                              + " — check the sidebar.*")
            except Exception as e:
                reply = friendly_error(e)
        say("assistant", reply)

    st.rerun()
