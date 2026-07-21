"use client";

/**
 * Client workbench for one employer role: shortlist (invite / unlock),
 * invited-candidates rail (contact after accept on free roles, after unlock
 * on paid roles), refresh-with-refinement, close, and hire.
 */
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  BadgeCheck, Loader2, Lock, LockOpen, Mail, RefreshCw, Send, UserCheck, X,
} from "lucide-react";

interface Contact {
  name: string; email: string; phone: string; headline: string; location: string;
  skills: string[]; experience: string[]; education: string[]; career_goals: string[];
}

interface ShortlistRow {
  candidate_id: string; fit_score: number | null; reason: string;
  headline: string; skills: string[]; experience_summary: string;
  location: string; unlocked: boolean; contact: Contact | null;
}

interface InviteRow {
  invite_id: number; candidate_user_id: string; candidate_name: string;
  candidate_headline: string; fit_score: number | null; status: string;
  invited_at: string; expires_at: string; responded_at: string | null;
  decline_reason: string | null; contact: Contact | null;
}

export function RoleWorkbench({
  roleId, isFree, status,
}: {
  roleId: number; isFree: boolean; status: string;
}) {
  const router = useRouter();
  const [shortlist, setShortlist] = useState<ShortlistRow[] | null>(null);
  const [invites, setInvites] = useState<InviteRow[]>([]);
  const [note, setNote] = useState("");
  const [refining, setRefining] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState(false);

  const load = useCallback(async () => {
    try {
      const [slRes, roleRes] = await Promise.all([
        fetch(`/api/employer/roles/${roleId}/shortlist`),
        fetch(`/api/employer/roles/${roleId}`),
      ]);
      if (slRes.ok) setShortlist((await slRes.json()).shortlist);
      else setLoadError(true);
      if (roleRes.ok) setInvites((await roleRes.json()).invites);
    } catch {
      setLoadError(true);
    }
  }, [roleId]);

  useEffect(() => {
    (async () => { await load(); })();
  }, [load]);

  async function act(candidateId: string, kind: "invite" | "unlock", inviteNote?: string) {
    setBusyId(candidateId);
    setError(null);
    try {
      const res = await fetch(
        `/api/employer/roles/${roleId}/${kind === "invite" ? "invites" : "unlocks"}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(
            kind === "invite"
              ? { candidate_user_id: candidateId, invite_note: inviteNote || undefined }
              : { candidate_user_id: candidateId },
          ),
        },
      );
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || "Something went wrong");
        return;
      }
      await load();
      router.refresh();
    } finally {
      setBusyId(null);
    }
  }

  async function refresh() {
    setRefining(true);
    setError(null);
    const before = JSON.stringify(shortlist?.map((c) => c.candidate_id) ?? []);
    await fetch(`/api/employer/roles/${roleId}/shortlist/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refinement_note: note.trim() || undefined }),
    });
    setNote("");
    // Regeneration runs in the background and routinely takes >10s (it's a
    // model call) — poll until the shortlist actually changes, capped at ~30s.
    for (let attempt = 0; attempt < 10; attempt++) {
      await new Promise((r) => setTimeout(r, 3000));
      try {
        const res = await fetch(`/api/employer/roles/${roleId}/shortlist`);
        if (res.ok) {
          const next = (await res.json()).shortlist as ShortlistRow[];
          setShortlist(next);
          if (JSON.stringify(next.map((c) => c.candidate_id)) !== before) break;
        }
      } catch { /* transient — keep polling */ }
    }
    setRefining(false);
  }

  async function hire(inviteId: number) {
    if (!window.confirm("Mark this candidate as hired? Other pending invites for this role will be closed.")) return;
    const res = await fetch(`/api/employer/roles/${roleId}/hire`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ invite_id: inviteId }),
    });
    if (res.ok) { await load(); router.refresh(); }
    else setError((await res.json()).error || "Couldn't mark as hired");
  }

  const open = status === "open";

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-extrabold">Emploi shortlist</h2>
          {open ? (
            <button
              onClick={refresh} disabled={refining}
              className="inline-flex items-center gap-1.5 rounded-xl border border-line px-3 py-1.5 text-xs font-bold hover:bg-surface disabled:opacity-60"
            >
              {refining ? <Loader2 className="animate-spin" size={13} /> : <RefreshCw size={13} />}
              Regenerate
            </button>
          ) : null}
        </div>
        {open ? (
          <textarea
            value={note} onChange={(e) => setNote(e.target.value)} rows={2}
            placeholder="Optional refinement for the next shortlist, e.g. “these candidates lacked startup experience”"
            className="w-full rounded-xl border border-line px-3.5 py-2.5 text-xs outline-none focus:border-brand"
          />
        ) : null}
        {error ? <p role="alert" className="text-sm font-semibold text-warn">{error}</p> : null}

        {shortlist === null && !loadError ? (
          <div className="flex items-center gap-2 rounded-2xl border border-line bg-card p-6 text-sm text-muted">
            <Loader2 className="animate-spin" size={16} /> Curating your shortlist…
          </div>
        ) : loadError || shortlist === null ? (
          <p className="rounded-2xl border border-line bg-card p-6 text-sm text-muted">
            Couldn&apos;t load the shortlist — refresh the page to retry.
          </p>
        ) : shortlist.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-line bg-card p-6 text-sm text-muted">
            No candidates to show yet. As more professionals opt in to employer
            discovery, your shortlist fills in automatically.
          </p>
        ) : (
          shortlist.map((c) => (
            <article key={c.candidate_id} className="rounded-2xl border border-line bg-card p-5 shadow-card">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-bold">
                    {c.contact?.name || c.headline || "Career Twin candidate"}
                    {c.unlocked ? (
                      <span className="ml-2 inline-flex items-center gap-1 rounded-full bg-good-soft px-2 py-0.5 text-[10px] font-bold text-good">
                        <LockOpen size={10} /> Unlocked
                      </span>
                    ) : null}
                  </p>
                  <p className="text-xs text-muted">
                    {c.headline}{c.location ? ` · ${c.location}` : ""}
                  </p>
                </div>
                {c.fit_score != null ? (
                  <span className="rounded-full bg-brand-soft px-3 py-1 text-xs font-extrabold text-brand">
                    {c.fit_score}/100
                  </span>
                ) : null}
              </div>
              {c.skills?.length ? (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {c.skills.slice(0, 8).map((s) => (
                    <span key={s} className="rounded-full bg-surface px-2.5 py-0.5 text-[11px] font-semibold text-muted">
                      {s}
                    </span>
                  ))}
                </div>
              ) : null}
              {c.reason ? <p className="mt-2 text-xs text-muted">{c.reason}</p> : null}
              {c.contact ? (
                <p className="mt-2 inline-flex items-center gap-1.5 text-xs font-bold text-brand">
                  <Mail size={12} /> {c.contact.email}
                </p>
              ) : null}
              {open ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  {!isFree && !c.unlocked ? (
                    <button
                      onClick={() => act(c.candidate_id, "unlock")}
                      disabled={busyId === c.candidate_id}
                      className="inline-flex items-center gap-1.5 rounded-xl border border-brand px-3.5 py-2 text-xs font-bold text-brand disabled:opacity-60"
                    >
                      <Lock size={13} /> Unlock (1 credit)
                    </button>
                  ) : (
                    <InviteButton
                      busy={busyId === c.candidate_id}
                      onInvite={(msg) => act(c.candidate_id, "invite", msg)}
                    />
                  )}
                </div>
              ) : null}
            </article>
          ))
        )}
      </section>

      <aside className="space-y-3">
        <h2 className="font-extrabold">Invited</h2>
        {invites.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-line bg-card p-5 text-xs text-muted">
            Nobody invited yet.
          </p>
        ) : (
          invites.map((inv) => (
            <article key={inv.invite_id} className="rounded-2xl border border-line bg-card p-4 shadow-card">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate text-sm font-bold">
                    {inv.candidate_name || inv.candidate_headline || "Candidate"}
                  </p>
                  <p className="text-[11px] text-muted">{inv.candidate_headline}</p>
                </div>
                <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${
                  inv.status === "accepted" ? "bg-good-soft text-good"
                  : inv.status === "hired" ? "bg-brand-soft text-brand"
                  : inv.status === "pending" ? "bg-amber-soft text-amber"
                  : "bg-surface text-muted"
                }`}>
                  {inv.status}
                </span>
              </div>
              {inv.status === "declined" && inv.decline_reason ? (
                <p className="mt-1.5 text-[11px] italic text-muted">“{inv.decline_reason}”</p>
              ) : null}
              {inv.contact ? (
                <div className="mt-2 space-y-0.5 text-[11px]">
                  <p className="inline-flex items-center gap-1 font-bold text-brand">
                    <Mail size={11} /> {inv.contact.email}
                  </p>
                  {inv.contact.phone ? <p className="text-muted">{inv.contact.phone}</p> : null}
                </div>
              ) : inv.status === "pending" ? (
                <p className="mt-1.5 text-[11px] text-faint">
                  {isFree ? "Contact shared when they accept." : "Awaiting response."}
                </p>
              ) : null}
              {inv.status === "accepted" && open ? (
                <button
                  onClick={() => hire(inv.invite_id)}
                  className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-brand px-3 py-1.5 text-[11px] font-bold text-white"
                >
                  <UserCheck size={12} /> Mark hired
                </button>
              ) : null}
              {inv.status === "hired" ? (
                <p className="mt-2 inline-flex items-center gap-1 text-[11px] font-extrabold text-good">
                  <BadgeCheck size={12} /> HIRED
                </p>
              ) : null}
            </article>
          ))
        )}
      </aside>
    </div>
  );
}

function InviteButton({
  busy, onInvite,
}: {
  busy: boolean; onInvite: (note: string) => void;
}) {
  const [openNote, setOpenNote] = useState(false);
  const [msg, setMsg] = useState("");
  if (!openNote)
    return (
      <button
        onClick={() => setOpenNote(true)} disabled={busy}
        className="inline-flex items-center gap-1.5 rounded-xl bg-brand px-3.5 py-2 text-xs font-bold text-white disabled:opacity-60"
      >
        <Send size={13} /> Invite to interview
      </button>
    );
  return (
    <div className="w-full space-y-2">
      <textarea
        value={msg} onChange={(e) => setMsg(e.target.value)} rows={2} maxLength={500}
        placeholder="Optional note to the candidate (they see it in the invite)"
        className="w-full rounded-xl border border-line px-3 py-2 text-xs outline-none focus:border-brand"
      />
      <div className="flex gap-2">
        <button
          onClick={() => onInvite(msg)} disabled={busy}
          className="inline-flex items-center gap-1.5 rounded-xl bg-brand px-3.5 py-2 text-xs font-bold text-white disabled:opacity-60"
        >
          {busy ? <Loader2 className="animate-spin" size={13} /> : <Send size={13} />}
          Send invite
        </button>
        <button
          onClick={() => setOpenNote(false)}
          className="inline-flex items-center gap-1 rounded-xl border border-line px-3 py-2 text-xs font-bold"
        >
          <X size={13} /> Cancel
        </button>
      </div>
    </div>
  );
}
