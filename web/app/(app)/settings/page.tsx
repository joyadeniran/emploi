"use client";

import { Suspense, useState } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import { BillingSection } from "@/components/BillingSection";
import { RecruiterVisibilityToggle } from "@/components/RecruiterVisibilityToggle";

export default function SettingsPage() {
  const [confirming, setConfirming] = useState(false);
  const [state, setState] = useState<"idle" | "busy" | "error">("idle");
  async function erase() {
    setState("busy");
    try {
      const response = await fetch("/api/user", { method: "DELETE" });
      if (!response.ok) throw new Error();
      window.location.assign("/signout");
    } catch {
      setState("error");
    }
  }
  return <div className="mx-auto max-w-3xl space-y-6"><header><h1 className="text-2xl font-extrabold tracking-tight sm:text-3xl">Settings</h1><p className="mt-1 text-sm text-muted">Manage your Career Twin, billing, and account data.</p></header><Suspense fallback={null}><BillingSection /></Suspense><RecruiterVisibilityToggle /><section className="rounded-2xl border border-line bg-card p-6 shadow-card"><h2 className="font-extrabold">Career Twin</h2><p className="mt-2 text-sm text-muted">Update your profile from a new CV on your Career Twin page. Your saved profile drives all match and generation results.</p><a href="/career-twin" className="mt-4 inline-block rounded-xl bg-brand px-4 py-2.5 text-sm font-bold text-white">View Career Twin</a></section><section className="rounded-2xl border border-warn/30 bg-warn-soft/40 p-6 shadow-card"><div className="flex gap-3"><AlertTriangle className="mt-0.5 text-warn" size={20} /><div><h2 className="font-extrabold">Delete all my data</h2><p className="mt-2 text-sm text-muted">This permanently deletes your Career Twin, applications, matches, and user events. This cannot be undone.</p>{confirming ? <div className="mt-4 flex flex-wrap gap-3"><button onClick={erase} disabled={state === "busy"} className="inline-flex items-center gap-2 rounded-xl bg-warn px-4 py-2.5 text-sm font-bold text-white disabled:opacity-70">{state === "busy" ? <Loader2 className="animate-spin" size={15} /> : null}Delete permanently</button><button onClick={() => { setConfirming(false); setState("idle"); }} className="rounded-xl border border-line bg-card px-4 py-2.5 text-sm font-bold">Cancel</button></div> : <button onClick={() => setConfirming(true)} className="mt-4 rounded-xl border border-warn px-4 py-2.5 text-sm font-bold text-warn">Delete my data</button>}{state === "error" ? <p role="alert" className="mt-3 text-sm font-semibold text-warn">We could not delete your data. Please try again.</p> : null}</div></div></section></div>;
}
