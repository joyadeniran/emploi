"use client";

import { useEffect, useState } from "react";
import { Sparkles, Loader2 } from "lucide-react";

type BillingStatus = {
  tier: string;
  status: string;
  used_this_month: number;
  limit: number;
  prices_ngn: Record<string, number>;
};

const TIER_LABEL: Record<string, string> = { free: "Free", pro: "Pro", max: "Max" };

/** Sidebar plan widget — real usage against the authenticated user's
 * actual billing state (was static mock data: "2/10" forever). Fetches
 * client-side, same pattern as the notification bell in Topbar. */
export function PlanCard() {
  const [status, setStatus] = useState<BillingStatus | null>(null);
  const [upgrading, setUpgrading] = useState(false);

  useEffect(() => {
    fetch("/api/billing/status")
      .then((r) => (r.ok ? r.json() : null))
      .then(setStatus)
      .catch(() => setStatus(null));
  }, []);

  async function upgrade(tier: "pro" | "max") {
    setUpgrading(true);
    try {
      const res = await fetch("/api/billing/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tier }),
      });
      const data = await res.json();
      if (res.ok && data.authorization_url) {
        window.location.assign(data.authorization_url);
        return;
      }
    } catch {
      /* fall through to settings link below */
    }
    setUpgrading(false);
    window.location.assign("/settings");
  }

  if (!status) {
    return (
      <div className="h-40 animate-pulse rounded-2xl border border-line bg-surface" aria-hidden />
    );
  }

  const pct = status.limit > 0 ? Math.round((status.used_this_month / status.limit) * 100) : 0;
  const label = TIER_LABEL[status.tier] ?? "Free";

  return (
    <div className="space-y-3">
      {status.tier === "free" ? (
        <div className="rounded-2xl border border-line bg-surface p-4">
          <div className="flex items-center gap-2 text-sm font-bold">
            <Sparkles size={16} className="text-brand" />
            Upgrade to Pro
          </div>
          <p className="mt-1.5 text-xs leading-relaxed text-muted">
            Get 50 tailored drafts a month, batch mode, and full interview prep.
          </p>
          <button
            onClick={() => upgrade("pro")}
            disabled={upgrading}
            className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-brand-violet to-brand-indigo px-4 py-2.5 text-sm font-bold text-white shadow-pop transition-transform hover:-translate-y-0.5 disabled:opacity-70"
          >
            {upgrading ? <Loader2 size={15} className="animate-spin" /> : null}
            Upgrade Now — ₦{status.prices_ngn.pro?.toLocaleString() ?? "3,500"}/mo
          </button>
        </div>
      ) : null}

      <div className="rounded-2xl border border-line p-4">
        <div className="flex items-center justify-between text-sm">
          <span className="font-bold">{label} Plan</span>
          {status.tier !== "max" ? (
            <a href="/settings" className="text-xs font-bold text-brand hover:underline">
              Upgrade
            </a>
          ) : null}
        </div>
        <div className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-line">
          <div
            className="h-full rounded-full bg-gradient-to-r from-brand-violet to-brand-indigo"
            style={{ width: `${Math.min(100, pct)}%` }}
          />
        </div>
        <p className="mt-2 text-xs text-muted">
          {status.used_this_month}/{status.limit} tailored drafts this month
        </p>
        {status.status === "past_due" ? (
          <p className="mt-2 text-xs font-semibold text-warn">
            Payment failed — update your card in Settings.
          </p>
        ) : null}
      </div>
    </div>
  );
}
