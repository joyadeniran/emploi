"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { BadgeCheck, Loader2 } from "lucide-react";

export function VouchButton({ employerId }: { employerId: number }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  async function vouch() {
    if (!window.confirm("Vouch for this employer? This clears their trust restriction — only do it for people you know personally.")) return;
    setBusy(true);
    const res = await fetch(`/api/admin/employers/${employerId}/vouch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ vouched_by: "joy" }),
    });
    setBusy(false);
    if (res.ok) { setDone(true); router.refresh(); }
  }

  if (done)
    return (
      <span className="inline-flex items-center gap-1 text-xs font-bold text-good">
        <BadgeCheck size={13} /> Vouched
      </span>
    );
  return (
    <button
      onClick={vouch} disabled={busy}
      className="inline-flex items-center gap-1.5 rounded-xl border border-line px-3.5 py-2 text-xs font-bold hover:bg-surface disabled:opacity-60"
    >
      {busy ? <Loader2 className="animate-spin" size={13} /> : <BadgeCheck size={13} />}
      Vouch
    </button>
  );
}
