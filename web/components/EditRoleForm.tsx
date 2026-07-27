"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Pencil, X } from "lucide-react";

interface EditableRole {
  id: number;
  title: string;
  description: string;
  location: string | null;
  is_remote: number | boolean;
  salary_text: string | null;
}

/**
 * Inline editor for a posted role. The backend `PATCH /employer/roles/{id}`
 * already supports this (and clears the cached shortlist when the description
 * changes) — this is the missing UI. Title + description are required; a blank
 * one is rejected client-side and also guarded server-side.
 */
export function EditRoleForm({ role }: { role: EditableRole }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const [title, setTitle] = useState(role.title);
  const [description, setDescription] = useState(role.description);
  const [location, setLocation] = useState(role.location ?? "");
  const [isRemote, setIsRemote] = useState(Boolean(role.is_remote));
  const [salary, setSalary] = useState(role.salary_text ?? "");

  function reset() {
    setTitle(role.title);
    setDescription(role.description);
    setLocation(role.location ?? "");
    setIsRemote(Boolean(role.is_remote));
    setSalary(role.salary_text ?? "");
    setError("");
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim() || !description.trim()) {
      setError("Title and description can’t be empty.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const res = await fetch(`/api/employer/roles/${role.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: title.trim(),
          description: description.trim(),
          location: location.trim(),
          is_remote: isRemote,
          salary_text: salary.trim(),
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || "Couldn’t save your changes.");
      }
      setOpen(false);
      router.refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => {
          reset();
          setOpen(true);
        }}
        className="inline-flex items-center gap-1.5 rounded-full border border-line px-3.5 py-1.5 text-sm font-bold text-muted hover:text-brand"
      >
        <Pencil size={14} /> Edit role
      </button>
    );
  }

  return (
    <form onSubmit={save} className="space-y-4 rounded-2xl border border-brand-soft bg-card p-5 shadow-card">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-extrabold">Edit role</h3>
        <button
          type="button"
          onClick={() => setOpen(false)}
          aria-label="Cancel editing"
          className="text-muted hover:text-ink"
        >
          <X size={16} />
        </button>
      </div>
      <div>
        <label htmlFor="edit-title" className="text-sm font-bold">Title</label>
        <input
          id="edit-title" value={title} onChange={(e) => setTitle(e.target.value)}
          maxLength={200}
          className="mt-1.5 w-full rounded-xl border border-line px-3.5 py-2.5 text-sm outline-none focus:border-brand"
        />
      </div>
      <div>
        <label htmlFor="edit-desc" className="text-sm font-bold">Description</label>
        <textarea
          id="edit-desc" value={description} onChange={(e) => setDescription(e.target.value)}
          rows={8} maxLength={30000}
          className="mt-1.5 w-full rounded-xl border border-line px-3.5 py-2.5 text-sm outline-none focus:border-brand"
        />
        <p className="mt-1 text-xs text-muted">
          Changing the description rebuilds the shortlist next time you refresh it.
        </p>
      </div>
      <div className="flex flex-wrap gap-4">
        <div className="flex-1 min-w-[160px]">
          <label htmlFor="edit-loc" className="text-sm font-bold">Location</label>
          <input
            id="edit-loc" value={location} onChange={(e) => setLocation(e.target.value)}
            maxLength={200} placeholder="e.g. Lagos, Nigeria"
            className="mt-1.5 w-full rounded-xl border border-line px-3.5 py-2.5 text-sm outline-none focus:border-brand"
          />
        </div>
        <div className="flex-1 min-w-[160px]">
          <label htmlFor="edit-salary" className="text-sm font-bold">Salary</label>
          <input
            id="edit-salary" value={salary} onChange={(e) => setSalary(e.target.value)}
            maxLength={200} placeholder="e.g. ₦400k–₦600k / month"
            className="mt-1.5 w-full rounded-xl border border-line px-3.5 py-2.5 text-sm outline-none focus:border-brand"
          />
        </div>
      </div>
      <label className="flex items-center gap-2 text-sm font-bold">
        <input
          type="checkbox" checked={isRemote} onChange={(e) => setIsRemote(e.target.checked)}
          className="h-4 w-4 rounded border-line"
        />
        Remote role
      </label>
      {error ? <p role="alert" className="text-sm font-semibold text-warn">{error}</p> : null}
      <div className="flex items-center gap-2">
        <button
          type="submit" disabled={busy}
          className="inline-flex items-center gap-2 rounded-xl bg-brand px-5 py-2.5 text-sm font-bold text-white disabled:opacity-60"
        >
          {busy ? <Loader2 size={15} className="animate-spin" /> : null}
          {busy ? "Saving…" : "Save changes"}
        </button>
        <button
          type="button" onClick={() => setOpen(false)}
          className="rounded-xl px-4 py-2.5 text-sm font-bold text-muted hover:text-ink"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
