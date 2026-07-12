"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Check, Loader2 } from "lucide-react";
import type { JobMatch } from "@/lib/data";

export function ApplyButton({ match }: { match: JobMatch }) {
  const router = useRouter();
  const [state, setState] = useState<"idle" | "busy" | "done" | "error">("idle");

  async function apply() {
    if (state !== "idle") return;
    setState("busy");
    try {
      const res = await fetch("/api/applications", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          company: match.company,
          role: match.title,
          status: "applied",
          extra: { fit_score: match.fit, source: "dashboard-match" },
        }),
      });
      if (!res.ok) throw new Error();
      setState("done");
      setTimeout(() => router.push("/applications"), 700);
    } catch {
      setState("error");
      setTimeout(() => setState("idle"), 2500);
    }
  }

  return (
    <button
      onClick={apply}
      disabled={state === "busy" || state === "done"}
      className="inline-flex items-center gap-2 rounded-xl bg-brand px-5 py-2.5 text-sm font-bold text-white transition-transform hover:-translate-y-0.5 disabled:opacity-70"
    >
      {state === "busy" ? <Loader2 size={14} className="animate-spin" /> : null}
      {state === "done" ? <Check size={14} /> : null}
      {state === "idle" && "Apply"}
      {state === "busy" && "Applying..."}
      {state === "done" && "Tracked!"}
      {state === "error" && "Offline — try later"}
    </button>
  );
}
