"use client";

import { useState } from "react";
import { Check, Copy, Share2 } from "lucide-react";

/**
 * The public, shareable link for a role — what an employer pastes into a
 * LinkedIn/WhatsApp post. Anyone can open it; applying prompts Google sign-in.
 */
export function ShareJobLink({ roleId }: { roleId: number }) {
  const [copied, setCopied] = useState(false);
  // Prefer the real origin at runtime; fall back to the production host.
  const origin = typeof window !== "undefined" ? window.location.origin : "https://app.emploihq.com";
  const url = `${origin}/jobs/${roleId}`;

  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* clipboard blocked — the field is selectable anyway */ }
  }

  return (
    <section className="rounded-2xl border border-brand-soft bg-brand-soft/30 p-5">
      <h2 className="flex items-center gap-2 text-sm font-extrabold">
        <Share2 size={16} className="text-brand" /> Share this job
      </h2>
      <p className="mt-1 text-xs text-muted">
        Post this link anywhere — LinkedIn, WhatsApp, your site. Anyone can view it;
        they sign in with Google to apply, and you’ll see them under Applicants.
      </p>
      <div className="mt-3 flex items-center gap-2">
        <input
          readOnly
          value={url}
          onFocus={(e) => e.currentTarget.select()}
          className="min-w-0 flex-1 rounded-xl border border-line bg-card px-3.5 py-2.5 text-sm outline-none"
        />
        <button
          onClick={copy}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-xl bg-brand px-4 py-2.5 text-sm font-bold text-white"
        >
          {copied ? <Check size={15} /> : <Copy size={15} />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
    </section>
  );
}
