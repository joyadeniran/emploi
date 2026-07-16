import Link from "next/link";
import { BadgeCheck, ShieldAlert, ShieldQuestion } from "lucide-react";
import { ApiUnavailableError, apiFetch } from "@/lib/api";
import { InviteActions } from "@/components/InviteActions";

interface InviteItem {
  id: number;
  role: { title: string; description_preview: string; location: string | null;
          is_remote: boolean; salary_text: string | null };
  employer: { company_name: string; trust_score: number | null;
              trust_level: string | null; verified: boolean };
  fit_score: number | null; invite_note: string | null; status: string;
  expires_at: string; created_at: string;
}

const TABS = [
  { key: "pending", label: "Pending" },
  { key: "accepted", label: "Accepted" },
  { key: "declined", label: "Declined" },
  { key: "expired", label: "Expired" },
  { key: "hired", label: "Hired" },
] as const;

function TrustChip({ employer }: { employer: InviteItem["employer"] }) {
  if (employer.verified)
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-good-soft px-2.5 py-0.5 text-[11px] font-bold text-good">
        <BadgeCheck size={12} /> Verified employer
      </span>
    );
  if (employer.trust_level === "medium")
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-amber-soft px-2.5 py-0.5 text-[11px] font-bold text-amber">
        <ShieldQuestion size={12} /> Trust: medium
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-warn-soft px-2.5 py-0.5 text-[11px] font-bold text-warn">
      <ShieldAlert size={12} /> Trust: {employer.trust_level ?? "unverified"} — verify before responding
    </span>
  );
}

function daysLeft(expiresAt: string): number {
  return Math.max(0, Math.ceil((new Date(expiresAt + "Z").getTime() - Date.now()) / 86_400_000));
}

export default async function InvitesPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>;
}) {
  const { status: raw } = await searchParams;
  const status = TABS.some((t) => t.key === raw) ? (raw as string) : "pending";
  let invites: InviteItem[] = [];
  let offline = false;
  try {
    ({ invites } = await apiFetch<{ invites: InviteItem[] }>(
      `/invites?status=${status}`,
    ));
  } catch (error) {
    if (error instanceof ApiUnavailableError) offline = true;
    else throw error;
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <header>
        <h1 className="text-2xl font-extrabold tracking-tight sm:text-3xl">Interview Invites</h1>
        <p className="mt-1 text-sm text-muted">
          Employers who found your Career Twin and want to talk. You&apos;re in
          control — nothing is shared beyond your visibility settings.
        </p>
      </header>

      <nav className="flex flex-wrap gap-2" aria-label="Invite status">
        {TABS.map((tab) => (
          <Link
            key={tab.key}
            href={`/invites?status=${tab.key}`}
            className={`rounded-full px-4 py-1.5 text-sm font-bold ${
              status === tab.key ? "bg-brand text-white" : "border border-line bg-card text-muted hover:bg-surface"
            }`}
          >
            {tab.label}
          </Link>
        ))}
      </nav>

      {offline ? (
        <p className="rounded-2xl border border-line bg-card p-6 text-sm text-muted">
          We couldn&apos;t reach the server — try again in a moment.
        </p>
      ) : invites.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-line bg-card p-8 text-center">
          <p className="font-bold">No {status} invites</p>
          {status === "pending" ? (
            <p className="mt-1 text-sm text-muted">
              Make sure employer discovery is on in{" "}
              <Link href="/settings" className="font-bold text-brand">Settings</Link>{" "}
              so verified employers can find your Career Twin.
            </p>
          ) : null}
        </div>
      ) : (
        invites.map((inv) => (
          <article key={inv.id} className="rounded-2xl border border-line bg-card p-5 shadow-card">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <Link href={`/invites/${inv.id}`} className="font-bold hover:text-brand">
                  {inv.role.title}
                </Link>
                <p className="mt-0.5 text-sm text-muted">
                  {inv.employer.company_name} ·{" "}
                  {inv.role.is_remote ? "Remote" : inv.role.location || "Location unspecified"}
                  {inv.role.salary_text ? ` · ${inv.role.salary_text}` : ""}
                </p>
                <div className="mt-1.5"><TrustChip employer={inv.employer} /></div>
              </div>
              <div className="text-right">
                {inv.fit_score != null ? (
                  <span className="rounded-full bg-brand-soft px-3 py-1 text-xs font-extrabold text-brand">
                    {inv.fit_score}/100 fit
                  </span>
                ) : null}
                {inv.status === "pending" ? (
                  <p className="mt-1.5 text-[11px] font-semibold text-muted">
                    Expires in {daysLeft(inv.expires_at)} day{daysLeft(inv.expires_at) === 1 ? "" : "s"}
                  </p>
                ) : null}
              </div>
            </div>
            {inv.invite_note ? (
              <p className="mt-3 rounded-xl bg-surface px-3.5 py-2.5 text-sm italic text-muted">
                “{inv.invite_note}”
              </p>
            ) : null}
            <p className="mt-2 text-sm text-muted">{inv.role.description_preview}…</p>
            <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
              <Link href={`/invites/${inv.id}`} className="text-sm font-bold text-brand">
                View full details →
              </Link>
              {inv.status === "pending" ? <InviteActions inviteId={inv.id} /> : null}
            </div>
          </article>
        ))
      )}
    </div>
  );
}
