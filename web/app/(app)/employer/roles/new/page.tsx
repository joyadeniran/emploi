"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Link2, Loader2, Sparkles } from "lucide-react";

export default function NewRolePage() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [jdText, setJdText] = useState("");
  const [titleOverride, setTitleOverride] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hintText, setHintText] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setHintText(false);
    try {
      const res = await fetch("/api/employer/roles", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: url.trim() || undefined,
          jd_text: jdText.trim() || undefined,
          title_override: titleOverride.trim() || undefined,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || "Something went wrong");
        // Unsupported/unreadable URL → nudge toward the text area.
        if (res.status === 422 && url.trim() && !jdText.trim()) setHintText(true);
        setBusy(false);
        return;
      }
      router.replace(`/employer/roles/${data.role_id}`);
    } catch {
      setError("Something went wrong — try again.");
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <header>
        <h1 className="text-2xl font-extrabold tracking-tight sm:text-3xl">Post a role</h1>
        <p className="mt-1 text-sm text-muted">
          Paste a job URL from Greenhouse, Lever, Ashby, Workable, or
          SmartRecruiters — or paste the job description text. Emploi extracts
          the role and curates your shortlist from opted-in Career Twins.
        </p>
      </header>

      <form onSubmit={submit} className="space-y-5 rounded-2xl border border-line bg-white p-6 shadow-card">
        <div>
          <label htmlFor="url" className="flex items-center gap-1.5 text-sm font-bold">
            <Link2 size={15} /> Job URL <span className="font-normal text-muted">(optional)</span>
          </label>
          <input
            id="url" value={url} onChange={(e) => setUrl(e.target.value)}
            placeholder="https://boards.greenhouse.io/yourcompany/jobs/123456"
            className="mt-1.5 w-full rounded-xl border border-line px-3.5 py-2.5 text-sm outline-none focus:border-brand"
          />
        </div>
        <div>
          <label
            htmlFor="jd"
            className={`text-sm font-bold ${hintText ? "text-warn" : ""}`}
          >
            Job description text {url ? "(fallback if the URL can’t be read)" : ""}
          </label>
          <textarea
            id="jd" value={jdText} onChange={(e) => setJdText(e.target.value)} rows={8}
            placeholder="Paste the full job description here…"
            className={`mt-1.5 w-full rounded-xl border px-3.5 py-2.5 text-sm outline-none focus:border-brand ${
              hintText ? "border-warn" : "border-line"
            }`}
          />
        </div>
        <div>
          <label htmlFor="title" className="text-sm font-bold">
            Role title override <span className="font-normal text-muted">(optional)</span>
          </label>
          <input
            id="title" value={titleOverride} onChange={(e) => setTitleOverride(e.target.value)}
            placeholder="e.g. Senior Data Analyst"
            className="mt-1.5 w-full rounded-xl border border-line px-3.5 py-2.5 text-sm outline-none focus:border-brand"
          />
        </div>
        {error ? <p role="alert" className="text-sm font-semibold text-warn">{error}</p> : null}
        <button
          type="submit" disabled={busy || (!url.trim() && !jdText.trim())}
          className="inline-flex items-center gap-2 rounded-xl bg-brand px-5 py-3 text-sm font-bold text-white disabled:opacity-60"
        >
          {busy ? <Loader2 className="animate-spin" size={16} /> : <Sparkles size={16} />}
          {busy ? "Extracting the role…" : "Post role & build shortlist"}
        </button>
        <p className="text-xs text-muted">
          Shortlist generation uses 1 AI call per refresh. Pasted text extraction
          uses 1 AI call.
        </p>
      </form>
    </div>
  );
}
