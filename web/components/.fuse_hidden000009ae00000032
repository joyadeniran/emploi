"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Check, Loader2, Mail, X } from "lucide-react";

export function InviteActions({ inviteId }: { inviteId: number }) {
  const router = useRouter();
  const [declining, setDeclining] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState<"accept" | "decline" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [acceptedEmail, setAcceptedEmail] = useState<string | null>(null);

  async function accept() {
    setBusy("accept");
    setError(null);
    try {
      const res = await fetch(`/api/invites/${inviteId}/accept`, { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Couldn't accept this invite");
      setAcceptedEmail(data.employer_contact_email || "");
      router.refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function decline() {
    setBusy("decline");
    setError(null);
    try {
      const res = await fetch(`/api/invites/${inviteId}/decline`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: reason.trim() || undefined }),
      });
      if (!res.ok) throw new Error((await res.json()).error || "Couldn't decline");
      router.refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  }

  if (acceptedEmail !== null)
    return (
      <div className="rounded-xl bg-good-soft p-3 text-sm">
        <p className="font-bold text-good">Invite accepted 🎉</p>
        <p className="mt-1 text-muted">
          The employer can now see your Career Twin contact details.
          {acceptedEmail ? (
            <>
              {" "}Want to reach out first?{" "}
              <a href={`mailto:${acceptedEmail}`} className="inline-flex items-center gap-1 font-bold text-brand">
                <Mail size={12} /> {acceptedEmail}
              </a>
            </>
          ) : null}
        </p>
      </div>
    );

  return (
    <div className="space-y-2">
      {declining ? (
        <div className="space-y-2">
          <input
            value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500}
            placeholder="Reason (optional — helps employers improve)"
            className="w-full rounded-xl border border-line px-3 py-2 text-xs outline-none focus:border-brand"
          />
          <div className="flex gap-2">
            <button
              onClick={decline} disabled={busy !== null}
              className="inline-flex items-center gap-1.5 rounded-xl bg-warn px-3.5 py-2 text-xs font-bold text-white disabled:opacity-60"
            >
              {busy === "decline" ? <Loader2 className="animate-spin" size={13} /> : <X size={13} />}
              Confirm decline
            </button>
            <button onClick={() => setDeclining(false)} className="rounded-xl border border-line px-3.5 py-2 text-xs font-bold">
              Back
            </button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          <button
            onClick={accept} disabled={busy !== null}
            className="inline-flex items-center gap-1.5 rounded-xl bg-brand px-4 py-2 text-sm font-bold text-white disabled:opacity-60"
          >
            {busy === "accept" ? <Loader2 className="animate-spin" size={14} /> : <Check size={14} />}
            Accept
          </button>
          <button
            onClick={() => setDeclining(true)} disabled={busy !== null}
            className="rounded-xl border border-line px-4 py-2 text-sm font-bold text-muted hover:bg-surface"
          >
            Decline
          </button>
        </div>
      )}
      {error ? <p role="alert" className="text-xs font-semibold text-warn">{error}</p> : null}
    </div>
  );
}
