"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, CheckCircle2, Clock, Loader2, Play } from "lucide-react";

type LastRun = { at?: string; summary?: { ok?: boolean } } | null;

const WORKERS: { key: string; label: string; event: string; hint: string }[] = [
  { key: "ingest", label: "Ingest jobs", event: "JobIngestionRun", hint: "Fetch from all sources" },
  { key: "match", label: "Match", event: "MatchingWorkerRun", hint: "Score jobs vs Career Twins (heavy — AI)" },
  { key: "verify-employers", label: "Verify employers", event: "VerificationWorkerRun", hint: "Refresh trust records" },
  { key: "expire-invites", label: "Expire invites", event: "ExpireInvitesRun", hint: "Close stale invites" },
  { key: "notify", label: "Notify", event: "NotifyWorkerRun", hint: "Send digest emails" },
  { key: "backup", label: "Backup", event: "BackupWorkerRun", hint: "Snapshot DB to R2" },
];

function ageLabel(at?: string): { text: string; stale: boolean } {
  if (!at) return { text: "never run", stale: true };
  const ts = new Date(at.replace(" ", "T") + "Z").getTime();
  const hours = (Date.now() - ts) / 3_600_000;
  const text =
    hours < 1 ? `${Math.max(1, Math.round(hours * 60))}m ago`
    : hours < 48 ? `${Math.round(hours)}h ago`
    : `${Math.round(hours / 24)}d ago`;
  return { text, stale: hours > 26 }; // daily workers should run within ~26h
}

export function WorkerControls({ lastRuns }: { lastRuns: Record<string, LastRun> }) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<{ key: string; msg: string; ok: boolean } | null>(null);

  async function run(worker: string, label: string) {
    if (worker === "match" && !window.confirm(`Run "${label}" now? This is the heavy AI job (Gemini calls per job × Career Twin).`)) return;
    setBusy(worker);
    setNote(null);
    try {
      const res = await fetch(`/api/admin/run/${worker}`, { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || "Trigger failed");
      setNote({ key: worker, msg: "Started — runs in the background.", ok: true });
      setTimeout(() => router.refresh(), 1500);
    } catch (e) {
      setNote({ key: worker, msg: (e as Error).message, ok: false });
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
      {WORKERS.map((w) => {
        const run_ = lastRuns[w.event] ?? null;
        const age = ageLabel(run_?.at);
        const failed = run_?.summary?.ok === false;
        return (
          <div key={w.key} className="rounded-2xl border border-line bg-card p-4">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="text-sm font-bold">{w.label}</p>
                <p className="text-[11px] text-muted">{w.hint}</p>
              </div>
              <button
                onClick={() => run(w.key, w.label)}
                disabled={busy !== null}
                className="inline-flex shrink-0 items-center gap-1 rounded-lg bg-brand px-2.5 py-1.5 text-xs font-bold text-white disabled:opacity-50"
              >
                {busy === w.key ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />} Run
              </button>
            </div>
            <div className="mt-2 flex items-center gap-1.5 text-[11px] font-semibold">
              {failed ? <AlertTriangle size={12} className="text-warn" />
                : age.stale ? <Clock size={12} className="text-amber" />
                : <CheckCircle2 size={12} className="text-good" />}
              <span className={failed ? "text-warn" : age.stale ? "text-amber" : "text-muted"}>
                {failed ? "last run failed" : age.text}
              </span>
            </div>
            {note?.key === w.key ? (
              <p className={`mt-1.5 text-[11px] font-semibold ${note.ok ? "text-good" : "text-warn"}`}>{note.msg}</p>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
