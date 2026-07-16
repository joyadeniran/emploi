"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Sparkles, X } from "lucide-react";

const DISMISS_KEY = "emploi.visibility-banner-dismissed";

/** One-time nudge for candidates whose twin is complete but discovery is off. */
export function RecruiterVisibilityBanner() {
  const [show, setShow] = useState(false);

  useEffect(() => {
    try {
      if (window.localStorage.getItem(DISMISS_KEY)) return;
    } catch { /* private mode */ }
    (async () => {
      try {
        const res = await fetch("/api/career-twin/recruiter-visibility");
        if (!res.ok) return;
        const data = await res.json();
        if (data.has_twin && !data.recruiter_visibility) setShow(true);
      } catch { /* stay hidden */ }
    })();
  }, []);

  if (!show) return null;
  return (
    <div className="flex items-start gap-3 rounded-2xl border border-brand/20 bg-brand-soft p-4">
      <Sparkles className="mt-0.5 shrink-0 text-brand" size={18} />
      <div className="flex-1 text-sm">
        <p className="font-bold text-brand">Get discovered by verified employers</p>
        <p className="mt-0.5 text-muted">
          Your Career Twin is ready. Turn on employer discovery and hiring
          managers can invite you to interviews — you stay in control of what
          they see.
        </p>
        <Link href="/settings" className="mt-1.5 inline-block text-xs font-bold text-brand">
          Turn it on in Settings →
        </Link>
      </div>
      <button
        aria-label="Dismiss"
        onClick={() => {
          try { window.localStorage.setItem(DISMISS_KEY, "1"); } catch { /* noop */ }
          setShow(false);
        }}
        className="rounded-lg p-1 text-muted hover:bg-white"
      >
        <X size={16} />
      </button>
    </div>
  );
}
