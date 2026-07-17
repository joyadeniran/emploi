"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Coins, Loader2 } from "lucide-react";

const PACKS = [5, 10, 25, 50];

function BillingInner() {
  const params = useSearchParams();
  const [status, setStatus] = useState<{
    credit_balance: number; unlock_price_ngn: number; min_pack: number;
  } | null>(null);
  const [busyPack, setBusyPack] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadStatus() {
    const res = await fetch("/api/employer/billing/status");
    if (res.ok) setStatus(await res.json());
  }

  useEffect(() => {
    // Returning from Paystack: confirm instantly (webhook stays authoritative).
    const ref = params.get("reference") || params.get("trxref");
    (async () => {
      if (ref) {
        await fetch("/api/employer/billing/verify", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ reference: ref }),
        });
      }
      await loadStatus();
    })();
  }, [params]);

  async function buy(credits: number) {
    setBusyPack(credits);
    setError(null);
    try {
      const res = await fetch("/api/employer/billing/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ credits }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Checkout failed");
      window.location.assign(data.authorization_url);
    } catch (err) {
      setError((err as Error).message);
      setBusyPack(null);
    }
  }

  const price = status?.unlock_price_ngn ?? 1000;
  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <header>
        <h1 className="text-2xl font-extrabold tracking-tight sm:text-3xl">Unlock credits</h1>
        <p className="mt-1 text-sm text-muted">
          Your first role is free. On every role after that, unlocking a
          candidate&apos;s contact details and inviting them uses one credit
          (₦{price.toLocaleString()} each).
        </p>
      </header>

      <section className="flex items-center gap-3 rounded-2xl border border-line bg-card p-5 shadow-card">
        <Coins className="text-brand" size={22} />
        <p className="text-sm font-bold">
          {status ? `${status.credit_balance} credit${status.credit_balance === 1 ? "" : "s"} available`
                  : "Loading balance…"}
        </p>
      </section>

      <section className="grid gap-3 sm:grid-cols-2">
        {PACKS.map((credits) => (
          <button
            key={credits}
            onClick={() => buy(credits)}
            disabled={busyPack !== null}
            className="rounded-2xl border border-line bg-card p-5 text-left shadow-card transition-shadow hover:shadow-pop disabled:opacity-60"
          >
            <p className="flex items-center gap-2 font-extrabold">
              {busyPack === credits ? <Loader2 className="animate-spin" size={15} /> : null}
              {credits} unlocks
            </p>
            <p className="mt-1 text-sm text-muted">₦{(credits * price).toLocaleString()}</p>
            <p className="mt-2 text-xs font-bold text-brand">Buy with Paystack →</p>
          </button>
        ))}
      </section>
      {error ? <p role="alert" className="text-sm font-semibold text-warn">{error}</p> : null}
      <p className="text-xs text-muted">
        Payments are processed by Paystack. Credits never expire and work on any
        of your paid roles.
      </p>
    </div>
  );
}

export default function EmployerBillingPage() {
  return (
    <Suspense fallback={null}>
      <BillingInner />
    </Suspense>
  );
}
