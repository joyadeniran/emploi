"use client";

import { useState } from "react";
import { Check, Copy, Loader2, X } from "lucide-react";
import type { JobMatch } from "@/lib/data";

type Generated = { result: string; fit_score: number | null };

export function ApplyButton({ match }: { match: JobMatch }) {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<"idle" | "busy" | "ready" | "tracking" | "error">("idle");
  const [generated, setGenerated] = useState<Generated | null>(null);

  async function generate() {
    if (!match.description) { setState("error"); return; }
    setState("busy");
    try {
      const response = await fetch("/api/applications/generate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ job: { company_name: match.company, title: match.title, description: match.description }, include_review: true }) });
      if (!response.ok) throw new Error();
      setGenerated((await response.json()).generated as Generated);
      setState("ready");
    } catch { setState("error"); }
  }

  async function trackAndApply() {
    setState("tracking");
    try {
      const response = await fetch("/api/applications", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ company: match.company, role: match.title, status: "applied", extra: { fit_score: generated?.fit_score ?? match.fit, source: "generated-match", job_id: match.jobId, apply_url: match.applyUrl } }) });
      if (!response.ok) throw new Error();
      if (match.applyUrl) { try { const url = new URL(match.applyUrl); if (url.protocol === "https:" || url.protocol === "http:") window.open(url.toString(), "_blank", "noopener,noreferrer"); } catch {} }
      setOpen(false); setState("idle");
    } catch { setState("error"); }
  }

  return <><button onClick={() => { setOpen(true); setState("idle"); }} className="rounded-xl bg-brand px-5 py-2.5 text-sm font-bold text-white">Apply</button>{open ? <div role="dialog" aria-modal="true" aria-label={`Generate application for ${match.title}`} className="fixed inset-0 z-[60] flex items-center justify-center bg-ink/40 p-4"><div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white p-6 shadow-card"><div className="flex items-start justify-between gap-4"><div><h2 className="text-xl font-extrabold">Tailor your application</h2><p className="mt-1 text-sm text-muted">{match.title} at {match.company}</p></div><button onClick={() => setOpen(false)} aria-label="Close" className="rounded-lg p-2"><X size={18} /></button></div>{!generated ? <div className="mt-5"><p className="text-sm text-muted">Generate a cover-letter draft grounded only in your Career Twin. This uses <strong>3 Gemini calls</strong> with review enabled (2 without review).</p><button onClick={generate} disabled={state === "busy"} className="mt-5 inline-flex items-center gap-2 rounded-xl bg-brand px-4 py-2.5 text-sm font-bold text-white">{state === "busy" ? <Loader2 size={15} className="animate-spin" /> : null}Generate application</button>{state === "error" ? <p role="alert" className="mt-3 text-sm font-semibold text-warn">We couldn’t generate this draft. Check the job details and try again.</p> : null}</div> : <div className="mt-5"><div className="flex items-center justify-between"><p className="text-sm font-bold">Fit score: {generated.fit_score ?? "Not available"}{generated.fit_score !== null ? "/100" : ""}</p><button onClick={() => navigator.clipboard.writeText(generated.result)} className="inline-flex items-center gap-1 text-sm font-bold text-brand"><Copy size={14} /> Copy</button></div><pre className="mt-3 whitespace-pre-wrap rounded-xl bg-surface p-4 text-sm leading-relaxed text-ink">{generated.result}</pre><button onClick={trackAndApply} disabled={state === "tracking"} className="mt-5 inline-flex items-center gap-2 rounded-xl bg-brand px-4 py-2.5 text-sm font-bold text-white">{state === "tracking" ? <Loader2 size={15} className="animate-spin" /> : <Check size={15} />}Track application and open employer site</button>{state === "error" ? <p role="alert" className="mt-3 text-sm font-semibold text-warn">We couldn’t save this application. Please try again.</p> : null}</div>}</div></div> : null}</>;
}
