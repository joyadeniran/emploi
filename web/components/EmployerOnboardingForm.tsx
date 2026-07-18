"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Building2, Check, Loader2, Mail, ShieldX, Sparkles } from "lucide-react";

const FREE_MAIL = new Set([
  "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.uk", "outlook.com",
  "hotmail.com", "live.com", "icloud.com", "proton.me", "protonmail.com",
  "aol.com", "gmx.com", "yandex.com", "mail.com", "zoho.com",
]);

/** The domain of a work email — "" for free-mail/personal accounts. When
 * present it's a strong signal: Google has already verified this person
 * receives mail at that domain. */
function workEmailDomain(email: string): string {
  const at = email.lastIndexOf("@");
  if (at === -1) return "";
  const host = email.slice(at + 1).trim().toLowerCase();
  return host && !FREE_MAIL.has(host) ? host : "";
}

/** Mirror of the backend's _derive_company_domain heuristic — a SUGGESTION the
 * user opts into, never an auto-fill (see the earlier "it picked supplya.com
 * before I could edit" report). */
function guessDomain(name: string): string {
  const stop = new Set(["inc", "llc", "ltd", "limited", "corp", "corporation",
    "co", "gmbh", "sa", "ag", "plc", "group", "holdings", "the"]);
  const slug = name.toLowerCase().replace(/\([^)]*\)/g, "")
    .split(/[^a-z0-9]+/).filter((t) => t && !stop.has(t)).join("");
  return slug.length >= 3 ? `${slug}.com` : "";
}

export function EmployerOnboardingForm({ email }: { email: string }) {
  const router = useRouter();
  const [name, setName] = useState("");
  // Derived from the signed-in email at first render — no effect needed.
  const [domain, setDomain] = useState(() => workEmailDomain(email));
  const [domainFromEmail, setDomainFromEmail] = useState(() => Boolean(workEmailDomain(email)));
  const [state, setState] = useState<"idle" | "busy">("idle");
  const [error, setError] = useState<{ blocked?: boolean; message: string } | null>(null);

  // The name-based suggestion, only offered when it differs from what's typed.
  const suggestion = guessDomain(name);
  const showSuggestion = suggestion && suggestion !== domain.trim().toLowerCase();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setState("busy");
    setError(null);
    try {
      const res = await fetch("/api/employer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          company_name: name.trim(),
          company_domain: domain.trim() || undefined,
        }),
      });
      const data = await res.json();
      if (res.status === 403) {
        setError({ blocked: true, message: data.error });
        setState("idle");
        return;
      }
      if (res.status === 409) { router.replace("/employer"); return; }
      if (!res.ok) throw new Error(data.error || "Something went wrong");
      router.replace("/employer");
    } catch (err) {
      setError({ message: (err as Error).message || "Something went wrong — try again." });
      setState("idle");
    }
  }

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <header>
        <h1 className="text-2xl font-extrabold tracking-tight sm:text-3xl">
          Set up your Employer Portal
        </h1>
        <p className="mt-1 text-sm text-muted">
          Your first role is completely free — post it, review your Emploi-curated
          shortlist, and interview.
        </p>
      </header>

      {email ? (
        <div className="flex items-center gap-2.5 rounded-2xl border border-line bg-surface/60 px-4 py-3 text-sm">
          <Mail size={15} className="shrink-0 text-brand" />
          <span className="text-muted">Signed in as</span>
          <span className="font-bold">{email}</span>
        </div>
      ) : null}

      {error?.blocked ? (
        <div className="flex gap-3 rounded-2xl border border-warn/30 bg-warn-soft/40 p-5">
          <ShieldX className="mt-0.5 shrink-0 text-warn" size={20} />
          <div className="text-sm">
            <p className="font-bold">We couldn&apos;t verify this employer</p>
            <p className="mt-1 text-muted">{error.message}</p>
            <a href="mailto:hello@emploihq.com" className="mt-2 inline-block font-bold text-brand">
              hello@emploihq.com
            </a>
          </div>
        </div>
      ) : null}

      <form onSubmit={submit} className="space-y-5 rounded-2xl border border-line bg-card p-6 shadow-card">
        <div>
          <label htmlFor="company" className="text-sm font-bold">Company name</label>
          <input
            id="company" required minLength={2} value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Supplya"
            className="mt-1.5 w-full rounded-xl border border-line px-3.5 py-2.5 text-sm outline-none focus:border-brand"
          />
        </div>

        <div>
          <label htmlFor="domain" className="text-sm font-bold">Company website domain</label>
          <input
            id="domain" value={domain}
            onChange={(e) => { setDomain(e.target.value); setDomainFromEmail(false); }}
            placeholder="yourcompany.com"
            className="mt-1.5 w-full rounded-xl border border-line px-3.5 py-2.5 text-sm outline-none focus:border-brand"
          />

          {domainFromEmail ? (
            <p className="mt-1.5 flex items-center gap-1.5 text-xs font-semibold text-good">
              <Check size={13} /> From your work email — you can change it.
            </p>
          ) : showSuggestion ? (
            <button
              type="button"
              onClick={() => setDomain(suggestion)}
              className="mt-1.5 inline-flex items-center gap-1.5 rounded-lg border border-brand/30 bg-brand-soft px-2.5 py-1 text-xs font-bold text-brand"
            >
              <Sparkles size={12} /> Use {suggestion}?
            </button>
          ) : (
            <p className="mt-1.5 text-xs text-muted">
              The domain candidates will see. We run an automated check on it.
            </p>
          )}
        </div>

        <p className="rounded-xl bg-surface px-3.5 py-2.5 text-xs leading-relaxed text-muted">
          You can post and shortlist right away. The{" "}
          <span className="font-semibold text-ink">Verified Employer</span> badge
          candidates trust is granted once you confirm you control this domain —
          we&apos;ll walk you through that shortly.
        </p>

        {error && !error.blocked ? (
          <p role="alert" className="text-sm font-semibold text-warn">{error.message}</p>
        ) : null}
        <button
          type="submit" disabled={state === "busy" || name.trim().length < 2}
          className="inline-flex items-center gap-2 rounded-xl bg-brand px-5 py-3 text-sm font-bold text-white disabled:opacity-60"
        >
          {state === "busy" ? <Loader2 className="animate-spin" size={16} /> : <Building2 size={16} />}
          {state === "busy" ? "Creating your account…" : "Create employer account"}
        </button>
      </form>
    </div>
  );
}
