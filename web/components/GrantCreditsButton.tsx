"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Coins, Loader2 } from "lucide-react";

/**
 * Admin control to grant (comp) unlock credits to an employer. Credits are not
 * verification — this only affects how many candidates they can unlock, never
 * their trust badge.
 */
export function GrantCreditsButton({
  employerId,
  companyName,
  balance,
}: {
  employerId: number;
  companyName: string;
  balance: number;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function grant() {
    setError("");
    const raw = window.prompt(
      `Grant free unlock credits to ${companyName} (current balance: ${balance}).\n` +
        `Enter a number — positive to grant, negative to claw back:`,
      "5",
    );
    if (raw === null) return;
    const delta = Number(raw.trim());
    if (!Number.isInteger(delta) || delta === 0) {
      setError("Enter a non-zero whole number.");
      return;
    }
    setBusy(true);
    try {
      const res = await fetch(`/api/admin/employers/${employerId}/credits`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ delta, reason: "admin_grant" }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || "Grant failed");
      router.refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        onClick={grant}
        disabled={busy}
        className="inline-flex items-center gap-1.5 rounded-xl border border-line px-3.5 py-2 text-xs font-bold hover:bg-surface disabled:opacity-60"
      >
        {busy ? <Loader2 className="animate-spin" size={13} /> : <Coins size={13} />}
        Grant credits
      </button>
      {error ? <span className="text-[11px] font-semibold text-warn">{error}</span> : null}
    </div>
  );
}
