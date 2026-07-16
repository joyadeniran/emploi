"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";

const REASONS = ["hired externally", "not hiring", "poor matches", "other"];

export function CloseRoleButton({ roleId }: { roleId: number }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  async function close() {
    setBusy(true);
    await fetch(`/api/employer/roles/${roleId}/close`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: reason || undefined }),
    });
    router.refresh();
    setBusy(false);
    setOpen(false);
  }

  if (!open)
    return (
      <button
        onClick={() => setOpen(true)}
        className="rounded-xl border border-line px-4 py-2 text-sm font-bold text-muted hover:bg-surface"
      >
        Close role
      </button>
    );
  return (
    <div className="w-full max-w-xs space-y-2 rounded-2xl border border-line bg-card p-4 shadow-card">
      <p className="text-sm font-bold">Close this role?</p>
      <p className="text-xs text-muted">Pending invites will be withdrawn.</p>
      <select
        value={reason} onChange={(e) => setReason(e.target.value)}
        className="w-full rounded-xl border border-line px-3 py-2 text-sm"
      >
        <option value="">Reason (optional)</option>
        {REASONS.map((r) => <option key={r} value={r}>{r}</option>)}
      </select>
      <div className="flex gap-2">
        <button
          onClick={close} disabled={busy}
          className="inline-flex items-center gap-1.5 rounded-xl bg-warn px-4 py-2 text-sm font-bold text-white disabled:opacity-60"
        >
          {busy ? <Loader2 className="animate-spin" size={14} /> : null} Close role
        </button>
        <button onClick={() => setOpen(false)} className="rounded-xl border border-line px-4 py-2 text-sm font-bold">
          Cancel
        </button>
      </div>
    </div>
  );
}
