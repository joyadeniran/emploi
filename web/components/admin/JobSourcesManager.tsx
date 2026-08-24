"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Pencil, Plus, Power, RefreshCw, Search, Trash2, X } from "lucide-react";

interface Source {
  id: number; company: string; ats: string; token: string;
  priority: number; active: number | boolean; region: string | null; category: string | null;
}

export function JobSourcesManager({ sources }: { sources: Source[] }) {
  const router = useRouter();
  const [busy, setBusy] = useState<number | "seed" | "save" | null>(null);
  const [filter, setFilter] = useState("");
  const [editing, setEditing] = useState<number | "new" | null>(null);
  const [form, setForm] = useState({ ats: "jooble", token: "", company: "", priority: 5, category: "", region: "global", active: true });
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
      const res = await fetch(`/api/admin/job-sources/${s.id}/toggle?active=${!Boolean(s.active)}`, { method: "PATCH" });
      if (!res.ok) throw new Error("Status update failed");
      router.refresh();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(null); }
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

  function openNew() {
    setError("");
    setForm({ ats: "jooble", token: "", company: "", priority: 5, category: "", region: "global", active: true });
    setEditing("new");
  }

  function openEdit(s: Source) {
    setError("");
    setForm({ ats: s.ats, token: s.token, company: s.company, priority: s.priority, category: s.category ?? "", region: s.region ?? "", active: Boolean(s.active) });
    setEditing(s.id);
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy("save"); setError("");
    try {
      const payload = { ...form, token: form.token.trim(), company: form.company.trim(), category: form.category.trim() || null, region: form.region.trim() || null };
      const res = await fetch(editing === "new" ? "/api/admin/job-sources" : `/api/admin/job-sources/${editing}`, {
        method: editing === "new" ? "POST" : "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || data.detail || "Save failed");
      setEditing(null);
      router.refresh();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(null); }
  }

  async function remove(s: Source) {
    if (!window.confirm(`Delete ${s.ats} source “${s.token}”?`)) return;
    setBusy(s.id); setError("");
    try {
      const res = await fetch(`/api/admin/job-sources/${s.id}`, { method: "DELETE" });
      if (!res.ok) throw new Error("Delete failed");
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
        <button onClick={openNew}
          className="inline-flex items-center gap-1.5 rounded-xl border border-line px-3 py-2 text-xs font-bold hover:bg-surface">
          <Plus size={13} /> Add source
        </button>
        <button onClick={seed} disabled={busy !== null}
          className="inline-flex items-center gap-1.5 rounded-xl border border-line px-3 py-2 text-xs font-bold hover:bg-surface disabled:opacity-50">
          {busy === "seed" ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />} Sync from repo
        </button>
      </div>

      {error ? <p role="alert" className="text-xs font-semibold text-warn">{error}</p> : null}

      {editing !== null ? (
        <form onSubmit={save} className="rounded-2xl border border-brand/30 bg-brand-soft/30 p-4">
          <div className="mb-3 flex items-center justify-between"><p className="text-sm font-extrabold">{editing === "new" ? "Add job source" : "Edit job source"}</p><button type="button" onClick={() => setEditing(null)} className="rounded-lg p-1 text-muted hover:bg-card" aria-label="Close source editor"><X size={16} /></button></div>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <select value={form.ats} onChange={(e) => setForm({ ...form, ats: e.target.value })}
            className="rounded-lg border border-line bg-card px-2 py-2 text-sm">
            {["jooble", "adzuna", "greenhouse", "lever", "ashby", "workable", "smartrecruiters", "manual"].map((a) => <option key={a}>{a}</option>)}
          </select>
          <input required value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} placeholder="Company or source name"
            className="rounded-lg border border-line bg-card px-3 py-2 text-sm" />
          <input required value={form.token} onChange={(e) => setForm({ ...form, token: e.target.value })}
            placeholder="token (jooble: Location:keywords · greenhouse: board slug)"
            className="rounded-lg border border-line bg-card px-3 py-2 text-sm" />
          <input type="number" min={1} max={10} value={form.priority}
            onChange={(e) => setForm({ ...form, priority: Number(e.target.value) })}
            className="rounded-lg border border-line bg-card px-3 py-2 text-sm" title="priority 1–10" />
          <input value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} placeholder="Category (optional)" className="rounded-lg border border-line bg-card px-3 py-2 text-sm" />
          <input value={form.region} onChange={(e) => setForm({ ...form, region: e.target.value })} placeholder="Region (optional)" className="rounded-lg border border-line bg-card px-3 py-2 text-sm" />
          <label className="flex items-center gap-2 px-1 text-sm font-semibold"><input type="checkbox" checked={form.active} onChange={(e) => setForm({ ...form, active: e.target.checked })} /> Active</label>
          <button type="submit" disabled={busy === "save"}
            className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-brand px-4 py-2 text-sm font-bold text-white disabled:opacity-50">
            {busy === "save" ? <Loader2 size={14} className="animate-spin" /> : editing === "new" ? "Add source" : "Save changes"}
          </button>
          </div>
        </form>
      ) : null}

      <div className="max-h-96 overflow-y-auto rounded-2xl border border-line">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-surface">
            <tr className="text-left text-[11px] font-bold uppercase text-faint">
              <th className="px-3 py-2">Source</th><th className="px-3 py-2">Token</th>
              <th className="px-3 py-2">Prio</th><th className="px-3 py-2">Status</th><th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((s) => (
              <tr key={s.id} className="border-t border-line">
                <td className="px-3 py-2"><p className="font-semibold">{s.company || s.ats}</p><p className="text-[11px] text-muted">{s.ats}{s.region ? ` · ${s.region}` : ""}</p></td>
                <td className="max-w-[220px] truncate px-3 py-2" title={s.token}>{s.token}</td>
                <td className="px-3 py-2 text-muted">{s.priority}</td>
                <td className="px-3 py-2">
                  <span className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${Boolean(s.active) ? "bg-good-soft text-good" : "bg-surface text-muted"}`}>
                    {Boolean(s.active) ? "active" : "off"}
                  </span>
                </td>
                <td className="px-3 py-2 text-right">
                  <div className="flex justify-end gap-1"><button onClick={() => openEdit(s)} disabled={busy !== null}
                    className="inline-flex items-center gap-1 rounded-lg border border-line px-2 py-1 text-[11px] font-bold hover:bg-surface disabled:opacity-50"><Pencil size={11} /> Edit</button>
                  <button onClick={() => toggle(s)} disabled={busy === s.id}
                    className="inline-flex items-center gap-1 rounded-lg border border-line px-2 py-1 text-[11px] font-bold hover:bg-surface disabled:opacity-50">
                    {busy === s.id ? <Loader2 size={11} className="animate-spin" /> : <Power size={11} />}
                    {Boolean(s.active) ? "Disable" : "Enable"}
                  </button>
                  <button onClick={() => remove(s)} disabled={busy !== null} aria-label={`Delete ${s.token}`}
                    className="rounded-lg border border-line p-1.5 text-warn hover:bg-warn-soft disabled:opacity-50"><Trash2 size={12} /></button></div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
