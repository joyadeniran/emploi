"use client";

import { useState } from "react";
import { Check, Loader2, X } from "lucide-react";

/**
 * Employer-side triage of an inbound applicant. This is the EMPLOYER's private
 * view of the applicant ('applied' → 'reviewed' / 'rejected') and is a separate
 * axis from the candidate's own application tracker — the two never sync.
 */
const LABELS: Record<string, string> = {
  applied: "New",
  reviewed: "Reviewed",
  rejected: "Rejected",
};

export function ApplicantStatusControl({
  roleId,
  candidateUserId,
  initialStatus,
}: {
  roleId: number;
  candidateUserId: string;
  initialStatus: string;
}) {
  const [status, setStatus] = useState(initialStatus || "applied");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function setNext(next: string) {
    setBusy(true);
    setError("");
    try {
      const res = await fetch(
        `/api/employer/roles/${roleId}/applicants/${encodeURIComponent(candidateUserId)}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status: next }),
        },
      );
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || "Couldn't update status.");
      }
      setStatus(next);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const badgeTone =
    status === "rejected"
      ? "bg-amber-soft text-amber"
      : status === "reviewed"
        ? "bg-good-soft text-good"
        : "bg-brand-soft text-brand";

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className={`rounded-full px-2 py-0.5 text-[11px] font-bold uppercase ${badgeTone}`}>
        {LABELS[status] ?? status}
      </span>
      {status !== "reviewed" ? (
        <button
          type="button"
          disabled={busy}
          onClick={() => setNext("reviewed")}
          className="inline-flex items-center gap-1 rounded-full border border-line px-2.5 py-1 text-[11px] font-bold text-muted hover:text-brand disabled:opacity-60"
        >
          <Check size={12} /> Reviewed
        </button>
      ) : null}
      {status !== "rejected" ? (
        <button
          type="button"
          disabled={busy}
          onClick={() => setNext("rejected")}
          className="inline-flex items-center gap-1 rounded-full border border-line px-2.5 py-1 text-[11px] font-bold text-muted hover:text-amber disabled:opacity-60"
        >
          <X size={12} /> Reject
        </button>
      ) : null}
      {busy ? <Loader2 size={13} className="animate-spin text-muted" /> : null}
      {error ? <span role="alert" className="text-[11px] font-semibold text-warn">{error}</span> : null}
    </div>
  );
}
