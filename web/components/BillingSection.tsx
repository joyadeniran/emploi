"use client";

import { useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { Check, Loader2, ShieldCheck, Sparkles } from "lucide-react";

type BillingStatus = {
  tier: string;
  status: string;
  current_period_end: string | null;
  used_this_month: number;
  limit: number;
  prices_ngn: Record<string, number>;
};

const TIERS: { key: "free" | "pro" | "max"; label: string; blurb: string; perks: string[] }[] = [
  { key: "free", label: "Free", blurb: "Get started for free.",
    perks: ["10 tailored drafts/month", "Employer trust check on every job", "Application tracker"] },
  { key: "pro", label: "Pro", blurb: "For an active job search.",
    perks: ["50 tailored drafts/month", "Batch mode across job sheets", "Full interview prep"] },
  { key: "max", label: "Max", blurb: "For a full-time search.",
    perks: ["300 tailored drafts/month (fair-use unlimited)", "Highest priority in nightly matching", "Advanced insights & analytics"] },
];

export function BillingSection() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [status, setStatus] = useState<BillingStatus | null>(null);
  const [busyTier, setBusyTier] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function refresh() {
    const res = await fetch("/api/billing/status");
    if (res.ok) setStatus(await res.json());
  }

  useEffect(() => {
    (async () => { await refresh(); })();
  }, []);

  // Returning from Paystack's hosted checkout: verify the transaction for
  // instant feedback (the webhook is authoritative but can lag a few seconds).
  useEffect(() => {
    if (searchParams.get("billing") !== "return") return;
    const reference = searchParams.get("reference");
    if (!reference) return;
    (async () => {
      try {
        const res = await fetch("/api/billing/verify", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ reference }),
        });
        if (res.ok) {
          const data = await res.json();
          setMessage(`You're on the ${data.tier === "max" ? "Max" : "Pro"} plan now.`);
          await refresh();
        } else {
          setError("We couldn't confirm that payment yet — it may still be processing.");
        }
      } finally {
        router.replace("/settings");
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  async function upgrade(tier: "pro" | "max") {
    setError("");
    setBusyTier(tier);
    try {
      const res = await fetch("/api/billing/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tier }),
      });
      const data = await res.json();
      if (!res.ok || !data.authorization_url) {
        setError(data?.error || "Couldn't start checkout — try again.");
        setBusyTier(null);
        return;
      }
      window.location.assign(data.authorization_url);
    } catch {
      setError("Couldn't start checkout — try again.");
      setBusyTier(null);
    }
  }

  async function cancel() {
    setError("");
    setCancelling(true);
    try {
      const res = await fetch("/api/billing/cancel", { method: "POST" });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data?.error);
      }
      setMessage("Your subscription is cancelled — you'll keep access until the current period ends.");
      await refresh();
    } catch (e) {
      setError(e instanceof Error && e.message ? e.message : "Couldn't cancel — try again.");
    } finally {
      setCancelling(false);
    }
  }

  return (
    <section className="rounded-2xl border border-line bg-card p-6 shadow-card">
      <div className="flex items-center gap-2.5">
        <ShieldCheck size={19} className="text-brand" />
        <h2 className="font-extrabold">Billing & plan</h2>
      </div>

      {!status ? (
        <p className="mt-4 text-sm text-muted">Loading…</p>
      ) : (
        <>
          <p className="mt-3 text-sm text-muted">
            You&apos;re on <strong>{status.tier === "free" ? "Free" : status.tier === "pro" ? "Pro" : "Max"}</strong> —
            {" "}{status.used_this_month}/{status.limit} tailored drafts used this month.
            {status.status === "past_due" ? (
              <span className="ml-1 font-semibold text-warn">Last payment failed.</span>
            ) : null}
          </p>

          <div className="mt-5 grid gap-4 sm:grid-cols-3">
            {TIERS.map((tier) => {
              const key = tier.key;
              const isCurrent = status.tier === key;
              return (
                <div key={tier.key}
                  className={`rounded-2xl border p-5 ${isCurrent ? "border-brand bg-brand-soft/40" : "border-line"}`}>
                  <p className="font-extrabold">{tier.label}</p>
                  <p className="mt-1 text-2xl font-extrabold">
                    ₦{(status.prices_ngn[tier.key] ?? 0).toLocaleString()}
                    <span className="text-xs font-bold text-faint">/mo</span>
                  </p>
                  <p className="mt-1 text-xs text-muted">{tier.blurb}</p>
                  <ul className="mt-3 space-y-1.5">
                    {tier.perks.map((perk) => (
                      <li key={perk} className="flex items-start gap-1.5 text-xs">
                        <Check size={13} className="mt-0.5 shrink-0 text-good" />
                        <span>{perk}</span>
                      </li>
                    ))}
                  </ul>
                  {isCurrent ? (
                    <p className="mt-4 rounded-xl bg-card px-3 py-2 text-center text-xs font-bold text-brand">
                      Current plan
                    </p>
                  ) : key === "pro" || key === "max" ? (
                    <button
                      onClick={() => upgrade(key)}
                      disabled={busyTier !== null}
                      className="mt-4 flex w-full items-center justify-center gap-1.5 rounded-xl bg-gradient-to-r from-brand-violet to-brand-indigo px-3 py-2.5 text-xs font-bold text-white shadow-pop disabled:opacity-60"
                    >
                      {busyTier === key ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
                      Upgrade to {tier.label}
                    </button>
                  ) : null}
                </div>
              );
            })}
          </div>

          {status.tier !== "free" ? (
            <button
              onClick={cancel}
              disabled={cancelling}
              className="mt-5 text-xs font-bold text-warn hover:underline disabled:opacity-60"
            >
              {cancelling ? "Cancelling…" : "Cancel subscription"}
            </button>
          ) : null}

          {message ? <p role="status" className="mt-4 text-sm font-semibold text-good">{message}</p> : null}
          {error ? <p role="alert" className="mt-4 text-sm font-semibold text-warn">{error}</p> : null}
        </>
      )}
    </section>
  );
}
