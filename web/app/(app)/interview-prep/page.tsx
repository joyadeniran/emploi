"use client";

import { useState } from "react";
import { Copy, FileDown, Loader2, Mic, Sparkles } from "lucide-react";
import {
  downloadDocument,
  generateInterviewPrep,
  GenerationError,
} from "@/lib/generate";

function progressLabel(elapsedSeconds: number): string {
  if (elapsedSeconds < 12) return "Reading the role against your Career Twin…";
  if (elapsedSeconds < 30) return "Drafting STAR answers from your real experience…";
  return "Almost there — building your prep…";
}

export default function InterviewPrepPage() {
  const [company, setCompany] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [state, setState] = useState<"idle" | "busy" | "ready" | "error">("idle");
  const [progress, setProgress] = useState("");
  const [prep, setPrep] = useState("");
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [downloading, setDownloading] = useState<"pdf" | "docx" | null>(null);

  async function prepare() {
    if (!description.trim()) {
      setError("Paste the job description so we can tailor your prep to it.");
      setState("error");
      return;
    }
    setError("");
    setProgress(progressLabel(0));
    setState("busy");
    try {
      const result = await generateInterviewPrep(
        { company_name: company.trim(), title: title.trim(), description: description.trim() },
        (elapsed) => setProgress(progressLabel(elapsed)),
      );
      setPrep(result.interview_prep);
      setState("ready");
    } catch (e) {
      setError(e instanceof GenerationError ? e.message : "Something went wrong — try again in a moment.");
      setState("error");
    }
  }

  async function download(format: "pdf" | "docx") {
    setDownloading(format);
    try {
      await downloadDocument(prep, format, `Interview Prep — ${title || company || "role"}`);
    } catch {
      setError("Couldn’t build that document — you can still copy the text.");
    } finally {
      setDownloading(null);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <header>
        <h1 className="flex items-center gap-2 text-2xl font-extrabold tracking-tight sm:text-3xl">
          <Mic size={24} className="text-brand" /> Interview Prep
        </h1>
        <p className="mt-1 text-sm text-muted">
          STAR answers, likely questions and talking points — built only from your real
          experience, never invented. Paste the role you’re interviewing for.
        </p>
      </header>

      <section className="space-y-4 rounded-2xl border border-line bg-card p-6 shadow-card">
        <div className="flex flex-wrap gap-4">
          <div className="min-w-[160px] flex-1">
            <label htmlFor="ip-company" className="text-sm font-bold">
              Company <span className="font-normal text-muted">(optional)</span>
            </label>
            <input
              id="ip-company" value={company} onChange={(e) => setCompany(e.target.value)}
              placeholder="e.g. Paystack"
              className="mt-1.5 w-full rounded-xl border border-line px-3.5 py-2.5 text-sm outline-none focus:border-brand"
            />
          </div>
          <div className="min-w-[160px] flex-1">
            <label htmlFor="ip-title" className="text-sm font-bold">
              Role title <span className="font-normal text-muted">(optional)</span>
            </label>
            <input
              id="ip-title" value={title} onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Product Designer"
              className="mt-1.5 w-full rounded-xl border border-line px-3.5 py-2.5 text-sm outline-none focus:border-brand"
            />
          </div>
        </div>
        <div>
          <label htmlFor="ip-desc" className="text-sm font-bold">Job description</label>
          <textarea
            id="ip-desc" value={description} onChange={(e) => setDescription(e.target.value)}
            rows={8} placeholder="Paste the full job description here…"
            className="mt-1.5 w-full rounded-xl border border-line px-3.5 py-2.5 text-sm outline-none focus:border-brand"
          />
        </div>

        {state === "busy" ? (
          <div className="flex items-center gap-3 rounded-xl bg-surface px-4 py-3">
            <Loader2 size={16} className="shrink-0 animate-spin text-brand" />
            <p className="text-sm font-semibold text-ink">{progress}</p>
          </div>
        ) : (
          <button
            onClick={prepare}
            className="inline-flex items-center gap-2 rounded-xl bg-brand px-5 py-3 text-sm font-bold text-white"
          >
            <Sparkles size={16} /> Prepare my interview
          </button>
        )}
        <p className="text-xs text-muted">
          Uses <strong>1 AI call</strong> and counts toward your monthly allowance.
        </p>
        {state === "error" ? <p role="alert" className="text-sm font-semibold text-warn">{error}</p> : null}
      </section>

      {state === "ready" && prep ? (
        <section className="rounded-2xl border border-line bg-card p-6 shadow-card">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-extrabold">Your interview prep</h2>
            <div className="flex items-center gap-3">
              <button
                onClick={() => { navigator.clipboard.writeText(prep); setCopied(true); setTimeout(() => setCopied(false), 2000); }}
                className="inline-flex items-center gap-1 text-xs font-bold text-brand"
              >
                <Copy size={13} /> {copied ? "Copied" : "Copy"}
              </button>
              <button
                onClick={() => download("pdf")} disabled={downloading !== null}
                className="inline-flex items-center gap-1 rounded-lg border border-line px-2.5 py-1.5 text-xs font-bold text-brand hover:bg-brand-soft disabled:opacity-60"
              >
                {downloading === "pdf" ? <Loader2 size={13} className="animate-spin" /> : <FileDown size={13} />} PDF
              </button>
              <button
                onClick={() => download("docx")} disabled={downloading !== null}
                className="inline-flex items-center gap-1 rounded-lg border border-line px-2.5 py-1.5 text-xs font-bold text-brand hover:bg-brand-soft disabled:opacity-60"
              >
                {downloading === "docx" ? <Loader2 size={13} className="animate-spin" /> : <FileDown size={13} />} Word
              </button>
            </div>
          </div>
          <pre className="mt-3 max-h-[32rem] overflow-y-auto whitespace-pre-wrap rounded-xl bg-surface p-4 text-sm leading-relaxed text-ink">
            {prep}
          </pre>
          {error ? <p role="alert" className="mt-2 text-xs font-semibold text-warn">{error}</p> : null}
        </section>
      ) : null}
    </div>
  );
}
