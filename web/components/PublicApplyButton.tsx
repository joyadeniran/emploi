"use client";

import { useState } from "react";
import { ArrowUpRight, Check, Loader2 } from "lucide-react";

/**
 * Apply CTA on a public job page. Viewing the page needs no account; applying
 * does — that's the Google sign-in funnel. When signed out, we send the visitor
 * to /login with a callbackUrl back to this job so they land right back here
 * (and can apply) after authenticating.
 */
export function PublicApplyButton({
  roleId,
  signedIn,
}: {
  roleId: number;
  signedIn: boolean;
}) {
  const [state, setState] = useState<"idle" | "busy" | "done" | "error">("idle");
  const [message, setMessage] = useState("");

  async function apply() {
    if (!signedIn) {
      window.location.href = `/login?callbackUrl=${encodeURIComponent(`/jobs/${roleId}`)}`;
      return;
    }
    setState("busy");
    setMessage("");
    try {
      const res = await fetch(`/api/public/roles/${roleId}/apply`, { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || "Couldn't submit your application.");
      setState("done");
      setMessage(data.already_applied ? "You've already applied to this role." : "Application sent 🎉");
    } catch (e) {
      setState("error");
      setMessage((e as Error).message);
    }
  }

  if (state === "done") {
    return (
      <div className="inline-flex items-center gap-2 rounded-full bg-good-soft px-6 py-3.5 text-sm font-bold text-good">
        <Check size={16} /> {message}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <button
        onClick={apply}
        disabled={state === "busy"}
        className="inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-brand-violet to-brand-indigo px-8 py-3.5 text-sm font-bold text-white shadow-pop transition-transform hover:-translate-y-0.5 disabled:opacity-60"
      >
        {state === "busy" ? <Loader2 size={16} className="animate-spin" /> : <ArrowUpRight size={16} />}
        {signedIn ? "Apply now" : "Sign in with Google to apply"}
      </button>
      {!signedIn ? (
        <p className="text-xs text-muted">Free — takes seconds. Your Career Twin does the rest.</p>
      ) : null}
      {state === "error" ? <p role="alert" className="text-xs font-semibold text-warn">{message}</p> : null}
    </div>
  );
}
