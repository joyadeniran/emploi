"use client";

import { useEffect, useState } from "react";
import { Eye, EyeOff, Loader2 } from "lucide-react";

/**
 * Candidate opt-in for employer discovery. Copy is deliberately explicit
 * about the paid-unlock reveal (decision locked with Joy 2026-07-16) so the
 * consent is informed: on paid roles a verified employer who purchases
 * access sees contact details when they unlock; on free roles contact is
 * shared when the candidate accepts an invite.
 */
export function RecruiterVisibilityToggle() {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [hasTwin, setHasTwin] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch("/api/career-twin/recruiter-visibility");
        if (res.ok) {
          const data = await res.json();
          setEnabled(Boolean(data.recruiter_visibility));
          setHasTwin(Boolean(data.has_twin));
        }
      } catch { /* leave null — control stays disabled */ }
    })();
  }, []);

  async function toggle() {
    if (enabled === null) return;
    setBusy(true);
    setError(false);
    try {
      const res = await fetch("/api/career-twin/recruiter-visibility", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !enabled }),
      });
      if (!res.ok) throw new Error();
      setEnabled(!enabled);
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-2xl border border-line bg-white p-6 shadow-card">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-extrabold">Employer discovery</h2>
          <p className="mt-2 text-sm text-muted">
            Let verified employers discover your Career Twin and invite you to
            interviews. Off by default — flip it on and Emploi puts you on
            curated shortlists for matching roles.
          </p>
          <p className="mt-2 text-xs text-muted">
            What&apos;s shared: your structured Career Twin (headline, skills,
            experience summary). Your email and phone are revealed only when
            you <span className="font-bold">accept an invite</span>, or when a
            verified employer on a paid role{" "}
            <span className="font-bold">purchases access to your profile</span>.
            Never your CV file or chat history.
          </p>
        </div>
        <button
          onClick={toggle}
          disabled={busy || enabled === null || !hasTwin}
          aria-pressed={enabled ?? false}
          className={`inline-flex shrink-0 items-center gap-2 rounded-full px-4 py-2 text-sm font-bold transition-colors disabled:opacity-60 ${
            enabled ? "bg-brand text-white" : "border border-line bg-white text-muted"
          }`}
        >
          {busy ? <Loader2 className="animate-spin" size={14} />
            : enabled ? <Eye size={14} /> : <EyeOff size={14} />}
          {enabled === null ? "…" : enabled ? "Discoverable" : "Hidden"}
        </button>
      </div>
      {!hasTwin ? (
        <p className="mt-3 text-xs font-semibold text-amber">
          Complete your Career Twin first — there&apos;s nothing to show employers yet.
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="mt-3 text-xs font-semibold text-warn">
          Couldn&apos;t update — try again.
        </p>
      ) : null}
    </section>
  );
}
