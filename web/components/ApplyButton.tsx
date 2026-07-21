"use client";

import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
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

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  function copy() {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <button onClick={copy} className="inline-flex items-center gap-1 text-xs font-bold text-brand hover:text-brand-vivid">
      {copied ? <><Check size={13} /> Copied</> : <><Copy size={13} /> Copy</>}
    </button>
  );
}

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
    <section className="rounded-2xl border border-line bg-card p-4 sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-sm font-extrabold">
          <FileText size={15} className="text-brand" /> {title}
        </h3>
        <div className="flex items-center gap-2">
          <CopyButton text={text} />
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
      <pre className="mt-3 max-h-72 overflow-y-auto whitespace-pre-wrap rounded-xl bg-surface p-4 text-xs leading-relaxed text-ink">
        {text}
      </pre>
      {error ? <p role="alert" className="mt-2 text-xs font-semibold text-warn">{error}</p> : null}
    </section>
  );
}

function parseMarkdownTable(md: string): { headers: string[]; rows: string[][] } | null {
  const lines = md.trim().split("\n");
  if (lines.length < 3) return null;
  const parse = (line: string) =>
    line.replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
  const headers = parse(lines[0]);
  if (!lines[1].match(/^[\s|:-]+$/)) return null;
  const rows = lines.slice(2).filter((l) => l.includes("|")).map(parse);
  if (rows.length === 0) return null;
  return { headers, rows };
}

function RenderedEvaluation({ text }: { text: string }) {
  const blocks = text.split(/\n\n+/);
  return (
    <div className="mt-3 space-y-3">
      {blocks.map((block, i) => {
        const table = parseMarkdownTable(block);
        if (table) {
          return (
            <div key={i} className="overflow-x-auto rounded-xl bg-card">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-line">
                    {table.headers.map((h, j) => (
                      <th key={j} className="px-3 py-2 text-left font-bold text-ink">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {table.rows.map((row, ri) => (
                    <tr key={ri} className="border-b border-line/50 last:border-0">
                      {row.map((cell, ci) => (
                        <td key={ci} className="px-3 py-2 text-muted">{cell}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }
        const trimmed = block.trim();
        if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
          const items = trimmed.split(/\n/).filter((l) => l.match(/^[\s]*[-*]\s/));
          return (
            <ul key={i} className="list-inside list-disc space-y-1 text-xs leading-relaxed text-muted">
              {items.map((item, j) => (
                <li key={j}>{item.replace(/^[\s]*[-*]\s/, "")}</li>
              ))}
            </ul>
          );
        }
        if (trimmed.startsWith("**") || trimmed.startsWith("Fit Score")) {
          return <p key={i} className="text-xs font-bold text-ink">{trimmed.replace(/\*\*/g, "")}</p>;
        }
        return (
          <p key={i} className="text-xs leading-relaxed text-muted">{trimmed}</p>
        );
      })}
    </div>
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
  const [trackError, setTrackError] = useState("");
  const [progress, setProgress] = useState("");
  // Portal target is only available client-side; the mounting gate keeps SSR
  // and the first client render identical (no hydration mismatch).
  const mounted = useSyncExternalStore(() => () => {}, () => true, () => false);

  useEffect(() => {
    if (open) document.body.style.overflow = "hidden";
    else document.body.style.overflow = "";
    return () => { document.body.style.overflow = ""; };
  }, [open]);

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
    if (!match.description) {
      setCvError("This job has no description to write from — track it directly below.");
      setCvState("error");
      return;
    }
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
      setCvError(e instanceof GenerationError ? e.message : "Couldn’t build your CV — try again in a moment.");
      setCvState("error");
    }
  }

  async function trackAndApply() {
    setTrackError("");
    setState("tracking");
    try {
      const response = await fetch("/api/applications", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          company: match.company,
          role: match.title,
          status: "applied",
          extra: {
            fit_score: generated?.fit_score ?? match.fit,
            source: generated ? "generated-match" : "direct-apply",
            job_id: match.jobId,
            apply_url: match.applyUrl,
          },
        }),
      });
      if (!response.ok) throw new Error();
      if (match.applyUrl) {
        try {
          const url = new URL(match.applyUrl);
          if (url.protocol === "https:" || url.protocol === "http:")
            window.open(url.toString(), "_blank", "noopener,noreferrer");
        } catch {}
      }
      setOpen(false);
      setState("idle");
      setGenerated(null);
      setCv("");
      setCvState("idle");
    } catch {
      setTrackError("We couldn’t save this application. Please try again.");
      setState("idle");
    }
  }

  function close() {
    setOpen(false);
  }

  return (
    <>
      <button
        onClick={() => { setOpen(true); setState("idle"); setErrorMsg(""); setTrackError(""); setCvError(""); if (cvState === "error") setCvState("idle"); }}
        className="rounded-xl bg-brand px-5 py-2.5 text-sm font-bold text-white shadow-sm transition-transform hover:-translate-y-0.5 hover:shadow-pop"
      >
        Apply
      </button>

      {open && mounted ? createPortal(
        <div
          role="dialog"
          aria-modal="true"
          aria-label={`Apply to ${match.title}`}
          className="fixed inset-0 z-[60] flex justify-end"
        >
          {/* backdrop */}
          <div className="absolute inset-0 bg-ink/60 backdrop-blur-sm" onClick={close} onPointerDown={(e) => e.stopPropagation()} />

          {/* drawer */}
          <div className="relative flex h-full w-full max-w-xl flex-col bg-card shadow-2xl sm:max-w-2xl">
            {/* sticky header */}
            <div className="flex items-center justify-between border-b border-line px-5 py-4 sm:px-6">
              <div className="min-w-0">
                <h2 className="truncate text-lg font-extrabold">{match.title}</h2>
                <p className="truncate text-sm text-muted">{match.company}</p>
              </div>
              <button onClick={close} aria-label="Close" className="ml-4 shrink-0 rounded-lg p-2 text-muted hover:bg-surface hover:text-ink">
                <X size={20} />
              </button>
            </div>

            {/* scrollable body — two independent artifacts, costs on the buttons */}
            <div className="flex-1 overflow-y-auto px-5 py-5 sm:px-6">
              <div className="space-y-5">
                {/* fit score badge (appears once the cover letter draft exists) */}
                {generated && generated.fit_score !== null ? (
                  <div className="inline-flex items-center gap-2 rounded-full bg-surface px-3 py-1.5 text-sm font-bold">
                    <span className={generated.fit_score >= 85 ? "text-good" : generated.fit_score >= 60 ? "text-amber" : "text-warn"}>
                      {generated.fit_score}/100
                    </span>
                    <span className="text-muted">fit score</span>
                  </div>
                ) : null}

                {/* cover letter + fit check */}
                {sections?.coverLetter ? (
                  <Artifact title="Cover letter" text={sections.coverLetter} filename={`Cover Letter — ${base}`} />
                ) : (
                  <section className="rounded-2xl border border-dashed border-line p-4 sm:p-5">
                    <h3 className="text-sm font-extrabold">Cover letter + fit check</h3>
                    <p className="mt-1.5 text-xs leading-relaxed text-muted">
                      A cover letter grounded only in your Career Twin, reviewed for tone and honesty, plus a
                      private fit evaluation. Downloadable as PDF or Word.
                    </p>
                    {state === "busy" ? (
                      <div className="mt-3 flex items-center gap-3 rounded-xl bg-surface px-4 py-3">
                        <Loader2 size={16} className="shrink-0 animate-spin text-brand" />
                        <p className="text-sm font-semibold text-ink">{progress}</p>
                      </div>
                    ) : (
                      <button onClick={generate} disabled={state === "tracking"}
                        className="mt-3 inline-flex items-center gap-2 rounded-xl bg-brand px-4 py-2.5 text-sm font-bold text-white shadow-sm disabled:opacity-60">
                        <FileText size={15} /> Generate — uses 3 AI calls
                      </button>
                    )}
                    {state === "error" ? <p role="alert" className="mt-2 text-xs font-semibold text-warn">{errorMsg}</p> : null}
                  </section>
                )}

                {/* tailored CV — independent of the cover letter */}
                {cv ? (
                  <Artifact title="Tailored CV" text={cv} filename={`CV — ${base}`} />
                ) : (
                  <section className="rounded-2xl border border-dashed border-line p-4 sm:p-5">
                    <h3 className="text-sm font-extrabold">Tailored CV</h3>
                    <p className="mt-1.5 text-xs leading-relaxed text-muted">
                      A complete, ready-to-send CV rewritten for this role from your Career Twin — downloadable as
                      PDF or Word. Only facts from your profile, never invented details.
                    </p>
                    {sections?.cvBullets ? (
                      <details className="mt-3">
                        <summary className="cursor-pointer text-xs font-bold text-brand hover:text-brand-vivid">
                          Preview the tailored bullets from your draft
                        </summary>
                        <pre className="mt-2 whitespace-pre-wrap rounded-xl bg-surface p-3 text-xs leading-relaxed text-ink">
                          {sections.cvBullets}
                        </pre>
                      </details>
                    ) : null}
                    <button onClick={buildCv} disabled={cvState === "busy"}
                      className="mt-3 inline-flex items-center gap-2 rounded-xl bg-brand px-4 py-2.5 text-sm font-bold text-white shadow-sm disabled:opacity-60">
                      {cvState === "busy" ? <Loader2 size={15} className="animate-spin" /> : <FileText size={15} />}
                      {cvState === "busy" ? "Building your CV…" : "Build CV — uses 1 AI call"}
                    </button>
                    {cvState === "error" ? <p role="alert" className="mt-2 text-xs font-semibold text-warn">{cvError}</p> : null}
                  </section>
                )}

                {/* fit evaluation — screen-only, never downloadable */}
                {sections?.evaluation ? (
                  <section className="rounded-2xl border border-line bg-surface/60 p-4 sm:p-5">
                    <div className="flex items-center gap-2">
                      <Eye size={15} className="shrink-0 text-muted" />
                      <h3 className="text-sm font-extrabold">Fit evaluation</h3>
                      <span className="rounded-full bg-card px-2 py-0.5 text-[10px] font-bold uppercase text-muted">
                        For your eyes only
                      </span>
                    </div>
                    <p className="mt-1.5 text-xs text-muted">
                      Your honest gaps and where the draft stretched. Never sent to the employer — it isn&apos;t included
                      in any download.
                    </p>
                    <RenderedEvaluation text={sections.evaluation} />
                  </section>
                ) : null}
              </div>
            </div>

            {/* sticky footer — the zero-cost path is ALWAYS available */}
            <div className="border-t border-line px-5 py-4 sm:px-6">
              <button onClick={trackAndApply} disabled={state === "tracking"}
                className={`flex w-full items-center justify-center gap-2 rounded-xl px-5 py-3 text-sm font-bold shadow-sm disabled:opacity-60 ${
                  generated || cv
                    ? "bg-brand text-white"
                    : "border border-line text-brand hover:bg-brand-soft"
                }`}>
                {state === "tracking" ? <Loader2 size={15} className="animate-spin" /> : generated || cv ? <Check size={15} /> : <ArrowUpRight size={15} />}
                Track application &amp; open employer site — no AI calls
              </button>
              {trackError ? (
                <p role="alert" className="mt-2 text-center text-xs font-semibold text-warn">{trackError}</p>
              ) : null}
            </div>
          </div>
        </div>,
        document.body,
      ) : null}
    </>
  );
}
