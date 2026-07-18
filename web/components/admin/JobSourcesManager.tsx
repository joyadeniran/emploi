"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Plus, Power, RefreshCw, Search } from "lucide-react";

interface Source {
  id: number; company: string; ats: string; token: string;
  priority: number; active: number | boolean; region: string | null; category: string | null;
}

export function JobSourcesManager({ sources }: { sources: Source[] }) {
  const router = useRouter();
  const [busy, setBusy] = useState<number | "seed" | "add" | null>(null);
  const [filter, setFilter] = useState("");
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ ats: "jooble", token: "", company: "", priority: 5 });
  const [error, setError] = useState("");

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    const list = q
      ? sources.filter((s) => `${s.ats} ${s.token} ${s.company}`.toLowerCase().includes(q))
      : sources;
    return [...list].sort((a, b) => Number(Boolean(b.active)) - Number(Boolean(a.active)) || a.ats.localeCompare(b.ats));
  }, [sources, filter]);

  const activeCount = sources.filter((s) => Boolean(s.active)).length;

  async function toggle(s: Source) {
    setBusy(s.id);
    try {
      await fetch(`/api/admin/job-sources/${s.id}/toggle?active=${!Boolean(s.active)}`, { method: "PATCH" });
      router.refresh();
    } finally { setBusy(null); }
  }

  async function seed() {
    setBusy("seed");
    try {
      const res = await fetch(`/api/admin/job-sources/seed?sync=true`, { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (res.ok) { setError(""); router.refresh(); }
      else setError(data.error || "Sync failed");
    } finally { setBusy(null); }
  }

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setBusy("add"); setError("");
    try {
      const res = await fetch(`/api/admin/job-sources`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...form, token: form.token.trim(), active: true }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || "Add failed");
      setShowAdd(false); setForm({ ats: "jooble", token: "", company: "", priority: 5 });
      router.refresh();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(null); }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[180px]">
          <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint" />
          <input
            value={filter} onChange={(e) => setFilter(e.target.value)}
            placeholder={`Filter ${sources.length} sources (${activeCount} active)`}
            className="w-full rounded-xl border border-line bg-card py-2 pl-9 pr-3 text-sm outline-none focus:border-brand"
          />
        </div>
        <button onClick={() => setShowAdd((v) => !v)}
          className="inline-flex items-center gap-1.5 rounded-xl border border-line px-3 py-2 text-xs font-bold hover:bg-surface">
          <Plus size={13} /> Add source
        </button>
        <button onClick={seed} disabled={busy !== null}
          className="inline-flex items-center gap-1.5 rounded-xl border border-line px-3 py-2 text-xs font-bold hover:bg-surface disabled:opacity-50">
          {busy === "seed" ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />} Sync from repo
        </button>
      </div>

      {error ? <p role="alert" className="text-xs font-semibold text-warn">{error}</p> : null}

      {showAdd ? (
        <form onSubmit={add} className="grid gap-2 rounded-2xl border border-line bg-card p-4 sm:grid-cols-[110px_1fr_110px_auto]">
          <select value={form.ats} onChange={(e) => setForm({ ...form, ats: e.target.value })}
            className="rounded-lg border border-line bg-card px-2 py-2 text-sm">
            {["jooble", "adzuna", "greenhouse", "lever", "ashby", "workable", "smartrecruiters", "manual"].map((a) => <option key={a}>{a}</option>)}
          </select>
          <input required value={form.token} onChange={(e) => setForm({ ...form, token: e.target.value })}
            placeholder="token (jooble: Location:keywords · greenhouse: board slug)"
            className="rounded-lg border border-line bg-card px-3 py-2 text-sm" />
          <input type="number" min={1} max={10} value={form.priority}
            onChange={(e) => setForm({ ...form, priority: Number(e.target.value) })}
            className="rounded-lg border border-line bg-card px-3 py-2 text-sm" title="priority 1–10" />
          <button type="submit" disabled={busy === "add"}
            className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-brand px-4 py-2 text-sm font-bold text-white disabled:opacity-50">
            {busy === "add" ? <Loader2 size={14} className="animate-spin" /> : "Add"}
          </button>
        </form>
      ) : null}

      <div className="max-h-96 overflow-y-auto rounded-2xl border border-line">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-surface">
            <tr className="text-left text-[11px] font-bold uppercase text-faint">
              <th className="px-3 py-2">ATS</th><th className="px-3 py-2">Token</th>
              <th className="px-3 py-2">Prio</th><th className="px-3 py-2">Status</th><th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((s) => (
              <tr key={s.id} className="border-t border-line">
                <td className="px-3 py-2 font-semibold">{s.ats}</td>
                <td className="max-w-[220px] truncate px-3 py-2" title={s.token}>{s.token}</td>
                <td className="px-3 py-2 text-muted">{s.priority}</td>
                <td className="px-3 py-2">
                  <span className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${Boolean(s.active) ? "bg-good-soft text-good" : "bg-surface text-muted"}`}>
                    {Boolean(s.active) ? "active" : "off"}
                  </span>
                </td>
                <td className="px-3 py-2 text-right">
                  <button onClick={() => toggle(s)} disabled={busy === s.id}
                    className="inline-flex items-center gap-1 rounded-lg border border-line px-2 py-1 text-[11px] font-bold hover:bg-surface disabled:opacity-50">
                    {busy === s.id ? <Loader2 size={11} className="animate-spin" /> : <Power size={11} />}
                    {Boolean(s.active) ? "Disable" : "Enable"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
