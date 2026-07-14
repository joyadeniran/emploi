"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Check, Loader2, Pencil, Plus, Sparkles, X } from "lucide-react";
import { UpdateCvButton } from "@/components/UpdateCvButton";

type Entry = { summary: string };
type Twin = {
  name?: string;
  headline?: string;
  bio?: string;
  skills?: string[];
  experience?: Entry[];
  education?: Entry[];
  career_goals?: string[];
  [key: string]: unknown;
};

async function patchTwin(data: Record<string, unknown>): Promise<boolean> {
  try {
    const res = await fetch("/api/career-twin", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ data }),
    });
    return res.ok;
  } catch {
    return false;
  }
}

function EditButton({ onClick, label }: { onClick: () => void; label: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className="rounded-lg p-1.5 text-faint transition hover:bg-brand-soft hover:text-brand"
    >
      <Pencil size={15} />
    </button>
  );
}

function SaveCancel({ saving, onSave, onCancel }: { saving: boolean; onSave: () => void; onCancel: () => void }) {
  return (
    <div className="mt-3 flex items-center gap-2">
      <button
        type="button"
        onClick={onSave}
        disabled={saving}
        className="inline-flex items-center gap-1.5 rounded-xl bg-brand px-4 py-2 text-sm font-bold text-white disabled:opacity-70"
      >
        {saving ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
        Save
      </button>
      <button
        type="button"
        onClick={onCancel}
        disabled={saving}
        className="rounded-xl border border-line px-4 py-2 text-sm font-bold text-muted hover:text-ink"
      >
        Cancel
      </button>
    </div>
  );
}

/** Header block: name + headline, editable together. */
function HeaderSection({ twin, refresh }: { twin: Twin; refresh: () => void }) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(false);
  const [name, setName] = useState(twin.name ?? "");
  const [headline, setHeadline] = useState(twin.headline ?? "");

  async function save() {
    setSaving(true);
    setError(false);
    const ok = await patchTwin({ name: name.trim(), headline: headline.trim() });
    setSaving(false);
    if (!ok) { setError(true); return; }
    setEditing(false);
    refresh();
  }

  if (!editing) {
    return (
      <header>
        <p className="flex items-center gap-2 text-sm font-bold text-brand">
          <Sparkles size={16} /> Your Career Twin
        </p>
        <div className="mt-1 flex items-center gap-2">
          <h1 className="text-3xl font-extrabold tracking-tight">{twin.name || "Your profile"}</h1>
          <EditButton label="Edit name and headline" onClick={() => { setName(twin.name ?? ""); setHeadline(twin.headline ?? ""); setEditing(true); }} />
        </div>
        <p className="mt-2 text-muted">{twin.headline || "A living profile built from your real experience."}</p>
      </header>
    );
  }
  return (
    <header className="rounded-2xl border border-brand-soft bg-white p-6 shadow-card">
      <p className="flex items-center gap-2 text-sm font-bold text-brand"><Sparkles size={16} /> Your Career Twin</p>
      <label className="mt-4 block text-xs font-bold text-muted">Full name</label>
      <input value={name} onChange={(e) => setName(e.target.value)}
        className="mt-1 w-full rounded-xl border border-line px-4 py-2.5 text-sm font-semibold outline-none focus:border-brand" />
      <label className="mt-3 block text-xs font-bold text-muted">Professional headline</label>
      <input value={headline} onChange={(e) => setHeadline(e.target.value)}
        className="mt-1 w-full rounded-xl border border-line px-4 py-2.5 text-sm font-semibold outline-none focus:border-brand" />
      {error ? <p role="alert" className="mt-2 text-sm font-semibold text-warn">Couldn&apos;t save — try again.</p> : null}
      <SaveCancel saving={saving} onSave={save} onCancel={() => setEditing(false)} />
    </header>
  );
}

/** Free-text section (About/bio). */
function BioSection({ twin, refresh }: { twin: Twin; refresh: () => void }) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(false);
  const [bio, setBio] = useState(twin.bio ?? "");

  async function save() {
    setSaving(true);
    setError(false);
    const ok = await patchTwin({ bio: bio.trim() });
    setSaving(false);
    if (!ok) { setError(true); return; }
    setEditing(false);
    refresh();
  }

  return (
    <section className="rounded-2xl border border-line bg-white p-6 shadow-card">
      <div className="flex items-center justify-between">
        <h2 className="font-extrabold">About</h2>
        {!editing ? <EditButton label="Edit about" onClick={() => { setBio(twin.bio ?? ""); setEditing(true); }} /> : null}
      </div>
      {editing ? (
        <>
          <textarea value={bio} onChange={(e) => setBio(e.target.value)} rows={5}
            className="mt-3 w-full rounded-xl border border-line px-4 py-2.5 text-sm leading-relaxed outline-none focus:border-brand" />
          {error ? <p role="alert" className="mt-2 text-sm font-semibold text-warn">Couldn&apos;t save — try again.</p> : null}
          <SaveCancel saving={saving} onSave={save} onCancel={() => setEditing(false)} />
        </>
      ) : (
        <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-muted">
          {twin.bio || "No summary yet — add one so tailored applications can lead with your story."}
        </p>
      )}
    </section>
  );
}

/** Editable chip list (skills, career goals). */
function ChipListSection({ title, field, values, refresh, empty }: {
  title: string; field: string; values: string[]; refresh: () => void; empty: string;
}) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(false);
  const [items, setItems] = useState<string[]>(values);
  const [draft, setDraft] = useState("");

  function addDraft() {
    const v = draft.trim();
    if (v && !items.includes(v)) setItems([...items, v]);
    setDraft("");
  }
  async function save() {
    setSaving(true);
    setError(false);
    const final = draft.trim() && !items.includes(draft.trim()) ? [...items, draft.trim()] : items;
    const ok = await patchTwin({ [field]: final });
    setSaving(false);
    if (!ok) { setError(true); return; }
    setDraft("");
    setEditing(false);
    refresh();
  }

  return (
    <section className="rounded-2xl border border-line bg-white p-6 shadow-card">
      <div className="flex items-center justify-between">
        <h2 className="font-extrabold">{title}</h2>
        {!editing ? <EditButton label={`Edit ${title.toLowerCase()}`} onClick={() => { setItems(values); setEditing(true); }} /> : null}
      </div>
      {editing ? (
        <>
          <div className="mt-3 flex flex-wrap gap-2">
            {items.map((item) => (
              <span key={item} className="inline-flex items-center gap-1.5 rounded-full bg-brand-soft px-3 py-1.5 text-sm font-semibold text-brand">
                {item}
                <button type="button" aria-label={`Remove ${item}`} onClick={() => setItems(items.filter((i) => i !== item))}
                  className="rounded-full hover:text-warn"><X size={13} /></button>
              </span>
            ))}
            <span className="inline-flex items-center gap-1 rounded-full border border-dashed border-line px-3 py-1.5">
              <input value={draft} onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addDraft(); } }}
                placeholder="Add…" className="w-24 bg-transparent text-sm outline-none" />
              <button type="button" aria-label="Add item" onClick={addDraft} className="text-brand"><Plus size={14} /></button>
            </span>
          </div>
          {error ? <p role="alert" className="mt-2 text-sm font-semibold text-warn">Couldn&apos;t save — try again.</p> : null}
          <SaveCancel saving={saving} onSave={save} onCancel={() => { setDraft(""); setEditing(false); }} />
        </>
      ) : values.length ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {values.map((item) => (
            <span key={item} className="rounded-full bg-brand-soft px-3 py-1.5 text-sm font-semibold text-brand">{item}</span>
          ))}
        </div>
      ) : (
        <p className="mt-3 text-sm text-muted">{empty}</p>
      )}
    </section>
  );
}

/** Editable line-entry list (experience, education) — [{summary}] shape. */
function EntryListSection({ title, field, values, refresh, empty, placeholder }: {
  title: string; field: string; values: Entry[]; refresh: () => void; empty: string; placeholder: string;
}) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(false);
  const [lines, setLines] = useState<string[]>(values.map((v) => v.summary));

  async function save() {
    setSaving(true);
    setError(false);
    const entries = lines.map((l) => l.trim()).filter(Boolean).map((summary) => ({ summary }));
    const ok = await patchTwin({ [field]: entries });
    setSaving(false);
    if (!ok) { setError(true); return; }
    setEditing(false);
    refresh();
  }

  return (
    <section className="rounded-2xl border border-line bg-white p-6 shadow-card">
      <div className="flex items-center justify-between">
        <h2 className="font-extrabold">{title}</h2>
        {!editing ? <EditButton label={`Edit ${title.toLowerCase()}`} onClick={() => { setLines(values.map((v) => v.summary)); setEditing(true); }} /> : null}
      </div>
      {editing ? (
        <>
          <div className="mt-3 space-y-2">
            {lines.map((line, i) => (
              <div key={i} className="flex items-start gap-2">
                <textarea value={line} rows={2}
                  onChange={(e) => setLines(lines.map((l, j) => (j === i ? e.target.value : l)))}
                  className="w-full rounded-xl border border-line px-3 py-2 text-sm leading-relaxed outline-none focus:border-brand" />
                <button type="button" aria-label="Remove entry" onClick={() => setLines(lines.filter((_, j) => j !== i))}
                  className="mt-2 rounded-lg p-1.5 text-faint hover:text-warn"><X size={15} /></button>
              </div>
            ))}
            <button type="button" onClick={() => setLines([...lines, ""])}
              className="inline-flex items-center gap-1.5 rounded-xl border border-dashed border-line px-3 py-2 text-sm font-semibold text-muted hover:border-brand/40 hover:text-brand">
              <Plus size={14} /> {placeholder}
            </button>
          </div>
          {error ? <p role="alert" className="mt-2 text-sm font-semibold text-warn">Couldn&apos;t save — try again.</p> : null}
          <SaveCancel saving={saving} onSave={save} onCancel={() => setEditing(false)} />
        </>
      ) : values.length ? (
        <ul className="mt-3 space-y-3 text-sm text-muted">
          {values.map((v, i) => (
            <li key={`${v.summary}-${i}`} className="border-l-2 border-brand-soft pl-3">{v.summary}</li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-sm text-muted">{empty}</p>
      )}
    </section>
  );
}

export function CareerTwinEditor({ twin }: { twin: Twin }) {
  const router = useRouter();
  const refresh = () => router.refresh();
  const skills = Array.isArray(twin.skills) ? twin.skills.filter((s): s is string => typeof s === "string") : [];
  const goals = Array.isArray(twin.career_goals) ? twin.career_goals.filter((g): g is string => typeof g === "string") : [];
  const experience = Array.isArray(twin.experience)
    ? twin.experience.filter((e): e is Entry => !!e && typeof (e as Entry).summary === "string")
    : [];
  const education = Array.isArray(twin.education)
    ? twin.education.filter((e): e is Entry => !!e && typeof (e as Entry).summary === "string")
    : [];

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <HeaderSection twin={twin} refresh={refresh} />
      <BioSection twin={twin} refresh={refresh} />
      <UpdateCvButton />
      <ChipListSection title="Skills" field="skills" values={skills} refresh={refresh}
        empty="No skills have been added yet." />
      <div className="grid gap-6 md:grid-cols-2">
        <EntryListSection title="Experience" field="experience" values={experience} refresh={refresh}
          empty="No experience entries have been added yet." placeholder="Add a role" />
        <EntryListSection title="Education" field="education" values={education} refresh={refresh}
          empty="No education entries have been added yet." placeholder="Add a qualification" />
      </div>
      <ChipListSection title="Career goals" field="career_goals" values={goals} refresh={refresh}
        empty="No career goals have been added yet." />
    </div>
  );
}
