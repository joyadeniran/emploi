"use client";

import { useMemo, useState } from "react";
import { ArrowUpRight, Check, Copy, Eye, FileDown, FileText, Loader2, X } from "lucide-react";
import type { JobMatch } from "@/lib/data";
import {
  downloadDocument,
  generateApplication,
  generateCv,
  GenerationError,
  splitDraft,
  type GeneratedDraft,
} from "@/lib/generate";

function progressLabel(elapsedSeconds: number): string {
  if (elapsedSeconds < 12) return "Writing your draft…";
  if (elapsedSeconds < 30) return "Reviewing it for tone and honesty…";
  return "Still working — a reviewed draft can take a little while…";
}

/**
 * One downloadable artifact. Only ever rendered for the cover letter and the
 * tailored CV — never the fit evaluation, which contains the candidate's own
 * gap analysis and must not end up in a file they send to an employer.
 */
function Artifact({
  title,
  text,
  filename,
}: {
  title: string;
  text: string;
  filename: string;
}) {
  const [busy, setBusy] = useState<"pdf" | "docx" | null>(null);
  const [error, setError] = useState("");

  async function download(format: "pdf" | "docx") {
    setError("");
    setBusy(format);
    try {
      await downloadDocument(text, format, filename);
    } catch (e) {
      setError(e instanceof GenerationError ? e.message : "Download failed — you can still copy the text.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="rounded-2xl border border-line bg-card p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-sm font-extrabold">
          <FileText size={15} className="text-brand" /> {title}
        </h3>
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigator.clipboard.writeText(text)}
            className="inline-flex items-center gap-1 text-xs font-bold text-brand"
          >
            <Copy size={13} /> Copy
          </button>
          <button
            onClick={() => download("pdf")}
            disabled={busy !== null}
            className="inline-flex items-center gap-1 rounded-lg border border-line px-2.5 py-1.5 text-xs font-bold text-brand hover:bg-brand-soft disabled:opacity-60"
          >
            {busy === "pdf" ? <Loader2 size={13} className="animate-spin" /> : <FileDown size={13} />} PDF
          </button>
          <button
            onClick={() => download("docx")}
            disabled={busy !== null}
            className="inline-flex items-center gap-1 rounded-lg border border-line px-2.5 py-1.5 text-xs font-bold text-brand hover:bg-brand-soft disabled:opacity-60"
          >
            {busy === "docx" ? <Loader2 size={13} className="animate-spin" /> : <FileDown size={13} />} Word
          </button>
        </div>
      </div>
      <pre className="mt-3 max-h-64 overflow-y-auto whitespace-pre-wrap rounded-xl bg-surface p-3 text-xs leading-relaxed text-ink">
        {text}
      </pre>
      {error ? <p role="alert" className="mt-2 text-xs font-semibold text-warn">{error}</p> : null}
    </section>
  );
}

export function ApplyButton({ match }: { match: JobMatch }) {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<"idle" | "busy" | "ready" | "tracking" | "error">("idle");
  const [generated, setGenerated] = useState<GeneratedDraft | null>(null);
  const [cv, setCv] = useState<string>("");
  const [cvState, setCvState] = useState<"idle" | "busy" | "error">("idle");
  const [cvError, setCvError] = useState("");
  const [errorMsg, setErrorMsg] = useState("");
  const [progress, setProgress] = useState("");

  const sections = useMemo(
    () => (generated ? splitDraft(generated.result) : null),
    [generated],
  );
  const base = `${match.title} — ${match.company}`;

  async function generate() {
    if (!match.description) {
      setErrorMsg("This job has no description to write from — track it directly below.");
      setState("error");
      return;
    }
    setErrorMsg("");
    setProgress(progressLabel(0));
    setState("busy");
    try {
      const draft = await generateApplication(
        { company_name: match.company, title: match.title, description: match.description },
        true,
        (elapsed) => setProgress(progressLabel(elapsed)),
      );
      setGenerated(draft);
      setState("ready");
    } catch (e) {
      setErrorMsg(e instanceof GenerationError ? e.message : "Something went wrong — you can still track the application and apply directly.");
      setState("error");
    }
  }

  async function buildCv() {
    if (!match.description) return;
    setCvError("");
    setCvState("busy");
    try {
      const result = await generateCv({
        company_name: match.company,
        title: match.title,
        description: match.description,
      });
      setCv(result.cv);
      setCvState("idle");
    } catch (e) {
      setCvError(e instanceof GenerationError ? e.message : "Couldn't build your CV — try again in a moment.");
      setCvState("error");
    }
  }

  async function trackAndApply() {
    setState("tracking");
    try {
      const response = await fetch("/api/applications", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ company: match.company, role: match.title, status: "applied", extra: { fit_score: generated?.fit_score ?? match.fit, source: generated ? "generated-match" : "direct-apply", job_id: match.jobId, apply_url: match.applyUrl } }) });
      if (!response.ok) throw new Error();
      if (match.applyUrl) { try { const url = new URL(match.applyUrl); if (url.protocol === "https:" || url.protocol === "http:") window.open(url.toString(), "_blank", "noopener,noreferrer"); } catch {} }
      setOpen(false); setState("idle"); setGenerated(null); setCv(""); setCvState("idle");
    } catch {
      setErrorMsg("We couldn't save this application. Please try again.");
      setState("error");
    }
  }

  return (
    <>
      <button
        onClick={() => { setOpen(true); setState("idle"); setErrorMsg(""); }}
        className="rounded-xl bg-brand px-5 py-2.5 text-sm font-bold text-white"
      >
        Apply
      </button>

      {open ? (
        <div role="dialog" aria-modal="true" aria-label={`Apply to ${match.title}`}
          className="fixed inset-0 z-[60] flex items-center justify-center bg-ink/40 p-4">
          <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-card p-6 shadow-card">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-xl font-extrabold">Apply to this role</h2>
                <p className="mt-1 text-sm text-muted">{match.title} at {match.company}</p>
              </div>
              <button onClick={() => setOpen(false)} aria-label="Close" className="rounded-lg p-2"><X size={18} /></button>
            </div>

            {!generated ? (
              <div className="mt-5">
                {state === "busy" ? (
                  <div className="flex items-center gap-3 rounded-xl bg-surface px-4 py-3">
                    <Loader2 size={16} className="shrink-0 animate-spin text-brand" />
                    <p className="text-sm font-semibold text-ink">{progress}</p>
                  </div>
                ) : (
                  <>
                    <p className="text-sm text-muted">
                      Want a cover letter grounded only in your Career Twin? That uses <strong>3 AI calls</strong> with
                      review enabled (2 without), and you can download it as PDF or Word. Or skip the draft and apply
                      directly — we&apos;ll still track it.
                    </p>
                    <div className="mt-5 flex flex-wrap items-center gap-3">
                      <button onClick={generate} disabled={state === "tracking"}
                        className="inline-flex items-center gap-2 rounded-xl bg-brand px-4 py-2.5 text-sm font-bold text-white disabled:opacity-60">
                        Generate application
                      </button>
                      <button onClick={trackAndApply} disabled={state === "tracking"}
                        className="inline-flex items-center gap-2 rounded-xl border border-line px-4 py-2.5 text-sm font-bold text-brand hover:bg-brand-soft disabled:opacity-60">
                        {state === "tracking" ? <Loader2 size={15} className="animate-spin" /> : <ArrowUpRight size={15} />}
                        Skip draft — track &amp; apply
                      </button>
                    </div>
                  </>
                )}
                {state === "error" ? <p role="alert" className="mt-3 text-sm font-semibold text-warn">{errorMsg}</p> : null}
              </div>
            ) : (
              <div className="mt-5 space-y-4">
                <p className="text-sm font-bold">
                  Fit score: {generated.fit_score ?? "Not available"}{generated.fit_score !== null ? "/100" : ""}
                </p>

                {sections?.coverLetter ? (
                  <Artifact title="Cover letter" text={sections.coverLetter} filename={`Cover Letter — ${base}`} />
                ) : null}

                {/* A complete CV is a separate model call, so it's opt-in and the
                    cost is stated up front (the draft's bullets are fragments). */}
                {cv ? (
                  <Artifact title="Tailored CV" text={cv} filename={`CV — ${base}`} />
                ) : (
                  <section className="rounded-2xl border border-dashed border-line bg-card p-4">
                    <h3 className="text-sm font-extrabold">Tailored CV</h3>
                    <p className="mt-1 text-xs leading-relaxed text-muted">
                      Build a complete, ready-to-send CV rewritten for this role from your Career Twin — downloadable as
                      PDF or Word. Uses <strong>1 more AI call</strong> and counts toward your monthly drafts.
                    </p>
                    {sections?.cvBullets ? (
                      <details className="mt-3">
                        <summary className="cursor-pointer text-xs font-bold text-brand">
                          Preview the tailored bullets from your draft
                        </summary>
                        <pre className="mt-2 whitespace-pre-wrap rounded-xl bg-surface p-3 text-xs leading-relaxed text-ink">
                          {sections.cvBullets}
                        </pre>
                      </details>
                    ) : null}
                    <button onClick={buildCv} disabled={cvState === "busy"}
                      className="mt-3 inline-flex items-center gap-2 rounded-xl bg-brand px-4 py-2.5 text-sm font-bold text-white disabled:opacity-60">
                      {cvState === "busy" ? <Loader2 size={15} className="animate-spin" /> : <FileText size={15} />}
                      {cvState === "busy" ? "Building your CV…" : "Build my tailored CV"}
                    </button>
                    {cvState === "error" ? <p role="alert" className="mt-2 text-xs font-semibold text-warn">{cvError}</p> : null}
                  </section>
                )}

                {/* Screen-only, deliberately NOT downloadable: this is the
                    candidate's own gap analysis, not something to send anyone. */}
                {sections?.evaluation ? (
                  <section className="rounded-2xl border border-line bg-surface/60 p-4">
                    <h3 className="flex items-center gap-2 text-sm font-extrabold">
                      <Eye size={15} className="text-muted" /> Fit evaluation
                      <span className="rounded-full bg-card px-2 py-0.5 text-[10px] font-bold uppercase text-muted">
                        For your eyes only
                      </span>
                    </h3>
                    <p className="mt-1 text-xs text-muted">
                      Your honest gaps and where the draft stretched. Never sent to the employer — it isn&apos;t included
                      in any download.
                    </p>
                    <pre className="mt-3 max-h-52 overflow-y-auto whitespace-pre-wrap rounded-xl bg-card p-3 text-xs leading-relaxed text-ink">
                      {sections.evaluation}
                    </pre>
                  </section>
                ) : null}

                <button onClick={trackAndApply} disabled={state === "tracking"}
                  className="inline-flex items-center gap-2 rounded-xl bg-brand px-4 py-2.5 text-sm font-bold text-white">
                  {state === "tracking" ? <Loader2 size={15} className="animate-spin" /> : <Check size={15} />}
                  Track application and open employer site
                </button>
                {state === "error" ? <p role="alert" className="mt-3 text-sm font-semibold text-warn">{errorMsg}</p> : null}
              </div>
            )}
          </div>
        </div>
      ) : null}
    </>
  );
}
