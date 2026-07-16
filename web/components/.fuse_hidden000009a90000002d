"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Bookmark } from "lucide-react";

/** Bookmark toggle for a real ingested job. Optimistic with revert — the
 *  icon fills instantly and rolls back if the API says no. */
export function SaveJobButton({ jobId, title, initialSaved = false, onRemoved }: {
  jobId?: number;
  title: string;
  initialSaved?: boolean;
  onRemoved?: () => void;
}) {
  const router = useRouter();
  const [saved, setSaved] = useState(initialSaved);
  const [busy, setBusy] = useState(false);
  if (!jobId) return null; // demo/imported cards have no pool job to bookmark

  async function toggle() {
    if (busy) return;
    const next = !saved;
    setSaved(next);
    setBusy(true);
    try {
      const res = await fetch(`/api/saved-jobs/${jobId}`, { method: next ? "PUT" : "DELETE" });
      if (!res.ok) throw new Error();
      if (!next) {
        onRemoved?.();
        router.refresh();
      }
    } catch {
      setSaved(!next); // revert — never show a bookmark that didn't stick
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      type="button"
      onClick={toggle}
      disabled={busy}
      aria-pressed={saved}
      aria-label={saved ? `Remove ${title} from saved jobs` : `Save ${title}`}
      className={`rounded-xl border p-2.5 transition ${saved
        ? "border-brand bg-brand-soft text-brand"
        : "border-line text-muted hover:bg-surface hover:text-brand"}`}
    >
      <Bookmark size={16} fill={saved ? "currentColor" : "none"} />
    </button>
  );
}
