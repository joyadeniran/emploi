"use client";

import { useEffect, useState } from "react";
import { Bell, BellOff, Loader2 } from "lucide-react";

/**
 * Digest + apply-alert opt-in. Default ON (the users row is created that
 * way). Without this control, PATCH /user/notifications had zero callers
 * and a poster who wanted quiet had no product path to it — or to confirm
 * mail was even enabled.
 */
export function EmailNotificationsToggle() {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch("/api/user");
        if (res.ok) {
          const data = await res.json();
          setEnabled(Boolean(data.notifications_enabled));
        }
      } catch {
        /* leave null — control stays disabled */
      }
    })();
  }, []);

  async function toggle() {
    if (enabled === null) return;
    setBusy(true);
    setError(false);
    try {
      const res = await fetch("/api/user", {
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
    <section className="rounded-2xl border border-line bg-card p-6 shadow-card">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-extrabold">Email alerts</h2>
          <p className="mt-2 text-sm text-muted">
            Get an email when someone applies to a role you posted, when a
            verified employer invites you to interview, and when your Career
            Twin finds new matches.
          </p>
        </div>
        <button
          onClick={toggle}
          disabled={busy || enabled === null}
          aria-pressed={enabled ?? false}
          className={`inline-flex shrink-0 items-center gap-2 rounded-full px-4 py-2 text-sm font-bold transition-colors disabled:opacity-60 ${
            enabled ? "bg-brand text-white" : "border border-line bg-card text-muted"
          }`}
        >
          {busy ? (
            <Loader2 className="animate-spin" size={14} />
          ) : enabled ? (
            <Bell size={14} />
          ) : (
            <BellOff size={14} />
          )}
          {enabled === null ? "…" : enabled ? "On" : "Off"}
        </button>
      </div>
      {error ? (
        <p role="alert" className="mt-3 text-xs font-semibold text-warn">
          {"Couldn't update — try again."}
        </p>
      ) : null}
    </section>
  );
}
