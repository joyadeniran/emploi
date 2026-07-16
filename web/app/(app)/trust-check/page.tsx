"use client";

import { useState } from "react";
import {
  BadgeCheck,
  CheckCircle2,
  Loader2,
  Search,
  ShieldAlert,
  ShieldCheck,
  XCircle,
} from "lucide-react";

interface TrustResult {
  company: string;
  domain: string | null;
  score: number;
  level: string;
  evidence: string[];
}

function levelMeta(score: number) {
  if (score >= 70)
    return { label: "High Trust", cls: "text-good", bg: "bg-good-soft", Icon: ShieldCheck };
  if (score >= 45)
    return { label: "Caution", cls: "text-amber", bg: "bg-amber-soft", Icon: ShieldAlert };
  return { label: "Avoid", cls: "text-warn", bg: "bg-warn-soft", Icon: ShieldAlert };
}

export default function TrustCheckPage() {
  const [query, setQuery] = useState("");
  const [jobText, setJobText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<TrustResult | null>(null);

  async function runCheck(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim() || loading) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch("/api/trust-check", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: query.trim(), job_text: jobText }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error ?? "Something went wrong — try again.");
      } else {
        setResult(data as TrustResult);
      }
    } catch {
      setError("Network error — check your connection and try again.");
    } finally {
      setLoading(false);
    }
  }

  const meta = result ? levelMeta(result.score) : null;

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="rise-in text-2xl font-extrabold tracking-tight sm:text-3xl">Trust Check</h1>
      <p className="mt-1 text-sm text-muted">
        Every trust score is computed from real, named evidence — never from an
        AI&apos;s opinion. Verification reduces risk; it is not a guarantee.
      </p>

      <form
        onSubmit={runCheck}
        className="rise-in mt-6 space-y-3 rounded-2xl border border-line bg-card p-6 shadow-card"
      >
        <div className="relative">
          <Search
            size={16}
            className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-faint"
          />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Company name, domain, or contact email (e.g. jobs@company.com)"
            className="w-full rounded-full border border-line bg-surface py-3 pl-11 pr-4 text-sm outline-none placeholder:text-faint focus:border-brand/40 focus:bg-card"
            aria-label="Company, domain or contact email"
          />
        </div>
        <textarea
          value={jobText}
          onChange={(e) => setJobText(e.target.value)}
          rows={3}
          placeholder="Optional: paste the job posting text — we scan it for known scam patterns (fees, WhatsApp-only contact, unrealistic pay...)"
          className="w-full resize-y rounded-2xl border border-line bg-surface px-4 py-3 text-sm outline-none placeholder:text-faint focus:border-brand/40 focus:bg-card"
          aria-label="Job posting text"
        />
        <button
          type="submit"
          disabled={loading || !query.trim()}
          className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-brand-violet to-brand-indigo px-6 py-3 text-sm font-bold text-white shadow-pop transition-transform hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? <Loader2 size={16} className="animate-spin" /> : <ShieldCheck size={16} />}
          {loading ? "Checking..." : "Run trust check"}
        </button>
      </form>

      {error ? (
        <div className="rise-in mt-4 flex items-center gap-2.5 rounded-2xl bg-warn-soft px-5 py-4 text-sm font-semibold text-warn">
          <XCircle size={16} className="shrink-0" />
          {error}
        </div>
      ) : null}

      {result && meta ? (
        <div className="rise-in mt-4 rounded-2xl border border-line bg-card p-6 shadow-card">
          <div className="flex items-center gap-3">
            <span className={`flex h-12 w-12 items-center justify-center rounded-xl ${meta.bg}`}>
              <meta.Icon size={22} className={meta.cls} />
            </span>
            <div className="min-w-0">
              <p className="flex items-center gap-1.5 text-lg font-extrabold">
                {result.company || result.domain || query}
                {result.score >= 70 ? <BadgeCheck size={16} className="text-brand" /> : null}
              </p>
              {result.domain ? (
                <p className="truncate text-sm text-muted">{result.domain}</p>
              ) : (
                <p className="text-sm text-muted">
                  No contact domain provided — treated as unverified.
                </p>
              )}
            </div>
            <p className="ml-auto whitespace-nowrap text-2xl font-extrabold">
              {result.score}
              <span className="text-base font-bold text-faint">/100</span>
            </p>
          </div>
          <p className={`mt-3 text-base font-extrabold ${meta.cls}`}>{meta.label}</p>
          <p className="mt-3 text-xs font-bold uppercase tracking-wide text-faint">Evidence:</p>
          <ul className="mt-2 grid gap-2 sm:grid-cols-2">
            {result.evidence.map((r) => (
              <li
                key={r}
                className="flex items-center gap-2 rounded-xl bg-surface px-3.5 py-2.5 text-xs font-semibold"
              >
                <CheckCircle2 size={14} className="shrink-0 text-brand" />
                {r}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <p className="mt-6 rounded-2xl bg-warn-soft px-5 py-4 text-xs font-semibold leading-relaxed text-ink">
        ⚠️ Whatever a trust score says: never pay a fee to apply or to be hired,
        and never share bank details, BVN, NIN or identity documents during an
        application process. A real employer will never ask.
      </p>
    </div>
  );
}
