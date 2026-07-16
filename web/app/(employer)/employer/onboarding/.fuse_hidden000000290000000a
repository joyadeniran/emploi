"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Building2, Loader2, ShieldX } from "lucide-react";

/** Mirror of the backend's _derive_company_domain heuristic — preview only;
 * the server derivation is authoritative. */
function guessDomain(name: string): string {
  const stop = new Set(["inc", "llc", "ltd", "limited", "corp", "corporation",
    "co", "gmbh", "sa", "ag", "plc", "group", "holdings", "the"]);
  const slug = name.toLowerCase().replace(/\([^)]*\)/g, "")
    .split(/[^a-z0-9]+/).filter((t) => t && !stop.has(t)).join("");
  return slug.length >= 3 ? `${slug}.com` : "";
}

export default function EmployerOnboardingPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [domain, setDomain] = useState("");
  const [domainTouched, setDomainTouched] = useState(false);
  const [state, setState] = useState<"idle" | "busy">("idle");
  const [error, setError] = useState<{ blocked?: boolean; message: string } | null>(null);

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
      if (res.status === 409) {
        router.replace("/employer");
        return;
      }
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
          shortlist, and interview. We verify every employer so candidates can
          trust the invites they receive.
        </p>
      </header>

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

      <form onSubmit={submit} className="space-y-5 rounded-2xl border border-line bg-white p-6 shadow-card">
        <div>
          <label htmlFor="company" className="text-sm font-bold">Company name</label>
          <input
            id="company" required minLength={2} value={name}
            onChange={(e) => {
              setName(e.target.value);
              if (!domainTouched) setDomain(guessDomain(e.target.value));
            }}
            placeholder="e.g. Acme Corp"
            className="mt-1.5 w-full rounded-xl border border-line px-3.5 py-2.5 text-sm outline-none focus:border-brand"
          />
        </div>
        <div>
          <label htmlFor="domain" className="text-sm font-bold">
            Company website domain <span className="font-normal text-muted">(auto-guessed — fix it if wrong)</span>
          </label>
          <input
            id="domain" value={domain}
            onChange={(e) => { setDomain(e.target.value); setDomainTouched(true); }}
            placeholder="acmecorp.com"
            className="mt-1.5 w-full rounded-xl border border-line px-3.5 py-2.5 text-sm outline-none focus:border-brand"
          />
          <p className="mt-1.5 text-xs text-muted">
            We run an automated trust check on this domain so candidates know
            who&apos;s inviting them.
          </p>
        </div>
        {error && !error.blocked ? (
          <p role="alert" className="text-sm font-semibold text-warn">{error.message}</p>
        ) : null}
        <button
          type="submit" disabled={state === "busy" || name.trim().length < 2}
          className="inline-flex items-center gap-2 rounded-xl bg-brand px-5 py-3 text-sm font-bold text-white disabled:opacity-60"
        >
          {state === "busy" ? <Loader2 className="animate-spin" size={16} /> : <Building2 size={16} />}
          {state === "busy" ? "Verifying your company…" : "Create employer account"}
        </button>
      </form>
    </div>
  );
}
