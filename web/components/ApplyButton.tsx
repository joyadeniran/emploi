"use client";

import { useState } from "react";
import { ArrowUpRight, Check, Copy, Loader2, X } from "lucide-react";
import type { JobMatch } from "@/lib/data";

type Generated = { result: string; fit_score: number | null };

function friendlyError(status: number, detail: string): string {
  if (status === 429) return "You've hit the hourly limit for tailored drafts — try again in a bit, or track the application without a draft below.";
  if (status === 503 || status === 502) return "The AI writer is unavailable right now. You can still track this application and apply directly.";
  if (status === 409) return "Complete your Career Twin first — the draft is written from it.";
  return detail || "We couldn't generate this draft. You can still track the application and apply directly.";
}

export function ApplyButton({ match }: { match: JobMatch }) {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<"idle" | "busy" | "ready" | "tracking" | "error">("idle");
  const [generated, setGenerated] = useState<Generated | null>(null);
  const [errorMsg, setErrorMsg] = useState("");

  async function generate() {
    if (!match.description) {
      setErrorMsg("This job has no description to write from — track it directly below.");
      setState("error");
      return;
    }
    setErrorMsg("");
    setState("busy");
    try {
      const response = await fetch("/api/applications/generate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ job: { company_name: match.company, title: match.title, description: match.description }, include_review: true }) });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        setErrorMsg(friendlyError(response.status, String(data?.error ?? "")));
        setState("error");
        return;
      }
      setGenerated((await response.json()).generated as Generated);
      setState("ready");
    } catch {
      setErrorMsg("Network hiccup — the draft didn't come back. Try again, or track the application without one.");
      setState("error");
    }
  }

  async function trackAndApply() {
    setState("tracking");
    try {
      const response = await fetch("/api/applications", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ company: match.company, role: match.title, status: "applied", extra: { fit_score: generated?.fit_score ?? match.fit, source: generated ? "generated-match" : "direct-apply", job_id: match.jobId, apply_url: match.applyUrl } }) });
      if (!response.ok) throw new Error();
      if (match.applyUrl) { try { const url = new URL(match.applyUrl); if (url.protocol === "https:" || url.protocol === "http:") window.open(url.toString(), "_blank", "noopener,noreferrer"); } catch {} }
      setOpen(false); setState("idle"); setGenerated(null);
    } catch {
      setErrorMsg("We couldn't save this application. Please try again.");
      setState("error");
    }
  }

  return <><button onClick={() => { setOpen(true); setState("idle"); setErrorMsg(""); }} className="rounded-xl bg-brand px-5 py-2.5 text-sm font-bold text-white">Apply</button>{open ? <div role="dialog" aria-modal="true" aria-label={`Apply to ${match.title}`} className="fixed inset-0 z-[60] flex items-center justify-center bg-ink/40 p-4"><div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white p-6 shadow-card"><div className="flex items-start justify-between gap-4"><div><h2 className="text-xl font-extrabold">Apply to this role</h2><p className="mt-1 text-sm text-muted">{match.title} at {match.company}</p></div><button onClick={() => setOpen(false)} aria-label="Close" className="rounded-lg p-2"><X size={18} /></button></div>{!generated ? <div className="mt-5"><p className="text-sm text-muted">Want a cover-letter draft grounded only in your Career Twin? That uses <strong>3 AI calls</strong> with review enabled (2 without). Or skip the draft and apply directly — we&apos;ll still track it.</p><div className="mt-5 flex flex-wrap items-center gap-3"><button onClick={generate} disabled={state === "busy" || state === "tracking"} className="inline-flex items-center gap-2 rounded-xl bg-brand px-4 py-2.5 text-sm font-bold text-white disabled:opacity-60">{state === "busy" ? <Loader2 size={15} className="animate-spin" /> : null}Generate application</button><button onClick={trackAndApply} disabled={state === "busy" || state === "tracking"} className="inline-flex items-center gap-2 rounded-xl border border-line px-4 py-2.5 text-sm font-bold text-brand hover:bg-brand-soft disabled:opacity-60">{state === "tracking" ? <Loader2 size={15} className="animate-spin" /> : <ArrowUpRight size={15} />}Skip draft — track &amp; apply</button></div>{state === "error" ? <p role="alert" className="mt-3 text-sm font-semibold text-warn">{errorMsg}</p> : null}</div> : <div className="mt-5"><div className="flex items-center justify-between"><p className="text-sm font-bold">Fit score: {generated.fit_score ?? "Not available"}{generated.fit_score !== null ? "/100" : ""}</p><button onClick={() => navigator.clipboard.writeText(generated.result)} className="inline-flex items-center gap-1 text-sm font-bold text-brand"><Copy size={14} /> Copy</button></div><pre className="mt-3 whitespace-pre-wrap rounded-xl bg-surface p-4 text-sm leading-relaxed text-ink">{generated.result}</pre><button onClick={trackAndApply} disabled={state === "tracking"} className="mt-5 inline-flex items-center gap-2 rounded-xl bg-brand px-4 py-2.5 text-sm font-bold text-white">{state === "tracking" ? <Loader2 size={15} className="animate-spin" /> : <Check size={15} />}Track application and open employer site</button>{state === "error" ? <p role="alert" className="mt-3 text-sm font-semibold text-warn">{errorMsg}</p> : null}</div>}</div></div> : null}</>;
}
