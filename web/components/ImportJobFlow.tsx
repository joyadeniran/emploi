"use client";

import { useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  BadgeCheck,
  Check,
  ClipboardPaste,
  Copy,
  Loader2,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

type Trust = { score: number; level: string; evidence: string[]; company: string; domain?: string };
type Generated = { result: string; fit_score: number | null };

export function ImportJobFlow() {
  const [company, setCompany] = useState("");
  const [contact, setContact] = useState("");
  const [jd, setJd] = useState("");
  const [role, setRole] = useState("");

  const [trust, setTrust] = useState<Trust | null>(null);
  const [generated, setGenerated] = useState<Generated | null>(null);
  const [busy, setBusy] = useState<"" | "trust" | "generate" | "track">("");
  const [error, setError] = useState("");
  const [tracked, setTracked] = useState(false);
  const [copied, setCopied] = useState(false);

  const lowTrust = trust !== null && trust.score <= 40;

  async function runTrustCheck() {
    setError("");
    setBusy("trust");
    setTrust(null);
    setGenerated(null);
    setTracked(false);
    try {
      const res = await fetch("/api/trust-check", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: contact.trim() || company.trim(),
          company: company.trim(),
          job_text: jd.trim(),
        }),
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({})))?.error || "trust check failed");
      setTrust((await res.json()) as Trust);
    } catch (e) {
      setError(e instanceof Error && e.message ? e.message : "Trust check failed — try again.");
    } finally {
      setBusy("");
    }
  }

  async function generate() {
    setError("");
    setBusy("generate");
    try {
      const res = await fetch("/api/applications/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job: { company_name: company.trim(), title: role.trim(), description: jd.trim() },
          include_review: true,
        }),
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({})))?.error || "generation failed");
      setGenerated((await res.json()).generated as Generated);
    } catch (e) {
      setError(e instanceof Error && e.message ? e.message : "Couldn't generate a draft — try again.");
    } finally {
      setBusy("");
    }
  }

  async function track() {
    setError("");
    setBusy("track");
    try {
      const res = await fetch("/api/applications", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          company: company.trim() || trust?.company || "Unknown",
          role: role.trim() || "Imported role",
          status: "applied",
          extra: {
            source: "imported-jd",
            fit_score: generated?.fit_score ?? null,
            trust_score: trust?.score ?? null,
          },
        }),
      });
      if (!res.ok) throw new Error();
      setTracked(true);
    } catch {
      setError("Couldn't save this to your tracker — try again.");
    } finally {
      setBusy("");
    }
  }

  const canCheck = jd.trim().length > 40 && (company.trim() || contact.trim());

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <header>
        <p className="flex items-center gap-2 text-sm font-bold text-brand">
          <ClipboardPaste size={16} /> Import a job
        </p>
        <h1 className="mt-1 text-2xl font-extrabold tracking-tight sm:text-3xl">
          Found a job somewhere else?
        </h1>
        <p className="mt-1 text-sm text-muted">
          Paste the description from LinkedIn, WhatsApp, email — anywhere. We&apos;ll verify the
          employer for scam signals, then prepare an honest tailored application from your Career Twin.
        </p>
      </header>

      {/* Step 1 — paste */}
      <section className="rounded-2xl border border-line bg-white p-6 shadow-card">
        <h2 className="font-extrabold">1 · Paste the job</h2>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <div>
            <label className="block text-xs font-bold text-muted">Company name</label>
            <input value={company} onChange={(e) => setCompany(e.target.value)} placeholder="e.g. Paystack"
              className="mt-1 w-full rounded-xl border border-line px-4 py-2.5 text-sm outline-none focus:border-brand" />
          </div>
          <div>
            <label className="block text-xs font-bold text-muted">Role title <span className="font-normal">(optional)</span></label>
            <input value={role} onChange={(e) => setRole(e.target.value)} placeholder="e.g. Marketing Manager"
              className="mt-1 w-full rounded-xl border border-line px-4 py-2.5 text-sm outline-none focus:border-brand" />
          </div>
        </div>
        <label className="mt-3 block text-xs font-bold text-muted">
          Contact email or website <span className="font-normal">(optional — improves verification)</span>
        </label>
        <input value={contact} onChange={(e) => setContact(e.target.value)} placeholder="e.g. jobs@paystack.com"
          className="mt-1 w-full rounded-xl border border-line px-4 py-2.5 text-sm outline-none focus:border-brand" />
        <label className="mt-3 block text-xs font-bold text-muted">Job description</label>
        <textarea value={jd} onChange={(e) => setJd(e.target.value)} rows={8}
          placeholder="Paste the full job description here…"
          className="mt-1 w-full rounded-xl border border-line px-4 py-3 text-sm leading-relaxed outline-none focus:border-brand" />
        <button type="button" onClick={runTrustCheck} disabled={!canCheck || busy === "trust"}
          className="mt-4 inline-flex items-center gap-2 rounded-xl bg-brand px-5 py-2.5 text-sm font-bold text-white disabled:opacity-60">
          {busy === "trust" ? <Loader2 size={15} className="animate-spin" /> : <ShieldCheck size={15} />}
          Verify employer
        </button>
        {!canCheck && (jd.trim() || company.trim()) ? (
          <p className="mt-2 text-xs text-muted">Add a company name (or contact) and at least a few lines of description.</p>
        ) : null}
      </section>

      {/* Step 2 — trust verdict */}
      {trust ? (
        <section className={`rounded-2xl border p-6 shadow-card ${lowTrust ? "border-warn/40 bg-warn-soft/30" : "border-line bg-white"}`}>
          <h2 className="font-extrabold">2 · Employer trust</h2>
          <p className="mt-3 text-3xl font-extrabold">
            {trust.score}<span className="text-base font-bold text-faint">/100</span>
            <span className={`ml-2 text-base font-extrabold ${lowTrust ? "text-warn" : "text-good"}`}>{trust.level}</span>
          </p>
          <ul className="mt-3 space-y-1.5">
            {trust.evidence?.map((line) => (
              <li key={line} className="flex items-start gap-2 text-sm">
                <BadgeCheck size={15} className="mt-0.5 shrink-0 text-brand" />
                <span>{line}</span>
              </li>
            ))}
          </ul>
          {lowTrust ? (
            <p role="alert" className="mt-4 flex items-start gap-2 rounded-xl bg-warn-soft px-4 py-3 text-sm font-bold text-ink">
              <AlertTriangle size={17} className="mt-0.5 shrink-0 text-warn" />
              This employer scores low on trust. If you continue, never pay a fee and never share
              bank details, your ID, or personal documents before a verified offer.
            </p>
          ) : null}
          {!generated ? (
            <div className="mt-4">
              <button type="button" onClick={generate} disabled={busy === "generate"}
                className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-brand-violet to-brand-indigo px-5 py-2.5 text-sm font-bold text-white shadow-pop disabled:opacity-60">
                {busy === "generate" ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />}
                Generate tailored application
              </button>
              <p className="mt-2 text-xs text-muted">
                Grounded only in your Career Twin — nothing invented. Uses 3 AI calls (drafted, then reviewed).
              </p>
            </div>
          ) : null}
        </section>
      ) : null}

      {/* Step 3 — draft + track */}
      {generated ? (
        <section className="rounded-2xl border border-line bg-white p-6 shadow-card">
          <div className="flex items-center justify-between gap-3">
            <h2 className="font-extrabold">3 · Your application</h2>
            <p className="text-sm font-bold">
              Fit: {generated.fit_score ?? "—"}{generated.fit_score !== null ? "/100" : ""}
            </p>
          </div>
          <pre className="mt-3 max-h-96 overflow-y-auto whitespace-pre-wrap rounded-xl bg-surface p-4 text-sm leading-relaxed text-ink">{generated.result}</pre>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <button type="button"
              onClick={() => { navigator.clipboard.writeText(generated.result); setCopied(true); setTimeout(() => setCopied(false), 2000); }}
              className="inline-flex items-center gap-1.5 rounded-xl border border-line px-4 py-2.5 text-sm font-bold text-brand hover:bg-brand-soft">
              <Copy size={14} /> {copied ? "Copied!" : "Copy draft"}
            </button>
            {tracked ? (
              <Link href="/applications" className="inline-flex items-center gap-1.5 rounded-xl bg-good px-4 py-2.5 text-sm font-bold text-white">
                <Check size={15} /> Tracked — view applications
              </Link>
            ) : (
              <button type="button" onClick={track} disabled={busy === "track"}
                className="inline-flex items-center gap-2 rounded-xl bg-brand px-4 py-2.5 text-sm font-bold text-white disabled:opacity-60">
                {busy === "track" ? <Loader2 size={15} className="animate-spin" /> : <Check size={15} />}
                Add to my tracker
              </button>
            )}
          </div>
        </section>
      ) : null}

      {error ? <p role="alert" className="text-sm font-semibold text-warn">{error}</p> : null}
    </div>
  );
}
