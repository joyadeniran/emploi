import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, BadgeCheck, ShieldAlert } from "lucide-react";
import { ApiUnavailableError, apiFetch } from "@/lib/api";
import { InviteActions } from "@/components/InviteActions";

interface InviteDetail {
  id: number;
  role: { title: string; description: string; location: string | null;
          is_remote: boolean; salary_text: string | null };
  employer: { company_name: string; trust_score: number | null;
              trust_level: string | null; verified: boolean;
              trust_evidence: string[] };
  fit_score: number | null; invite_note: string | null; status: string;
  expires_at: string;
}

export default async function InviteDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  let invite: InviteDetail;
  try {
    invite = await apiFetch<InviteDetail>(`/invites/${id}`);
  } catch (error) {
    if (error instanceof ApiUnavailableError) throw error;
    if ((error as { status?: number }).status === 404) notFound();
    throw error;
  }

  const lowTrust = !invite.employer.verified && invite.employer.trust_level !== "medium";
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <Link href="/invites" className="inline-flex items-center gap-1.5 text-sm font-bold text-muted hover:text-brand">
        <ArrowLeft size={15} /> All invites
      </Link>

      <header>
        <h1 className="text-2xl font-extrabold tracking-tight sm:text-3xl">{invite.role.title}</h1>
        <p className="mt-1 text-sm text-muted">
          {invite.employer.company_name} ·{" "}
          {invite.role.is_remote ? "Remote" : invite.role.location || "Location unspecified"}
          {invite.role.salary_text ? ` · ${invite.role.salary_text}` : ""}
        </p>
      </header>

      {lowTrust ? (
        <div className="flex gap-3 rounded-2xl border border-warn/30 bg-warn-soft/40 p-4 text-sm">
          <ShieldAlert className="mt-0.5 shrink-0 text-warn" size={18} />
          <p className="text-muted">
            <span className="font-bold text-warn">This employer has a {invite.employer.trust_level ?? "unverified"} trust rating.</span>{" "}
            Verify them before responding — and never pay a fee or share bank/ID
            details to get a job.
          </p>
        </div>
      ) : null}

      {invite.invite_note ? (
        <blockquote className="rounded-2xl bg-surface px-4 py-3 text-sm italic text-muted">
          “{invite.invite_note}”
        </blockquote>
      ) : null}

      {invite.status === "pending" ? (
        <div className="rounded-2xl border border-line bg-white p-5 shadow-card">
          <InviteActions inviteId={invite.id} />
          <p className="mt-3 text-xs text-muted">
            Accepting shares your Career Twin contact details with this employer
            and gives you their email so you can reach out first.
          </p>
        </div>
      ) : (
        <p className="rounded-2xl border border-line bg-white p-4 text-sm font-bold capitalize shadow-card">
          Status: {invite.status}
        </p>
      )}

      <section className="rounded-2xl border border-line bg-white p-5 shadow-card">
        <h2 className="font-extrabold">Role description</h2>
        <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-muted">
          {invite.role.description}
        </p>
      </section>

      <section className="rounded-2xl border border-line bg-white p-5 shadow-card">
        <h2 className="flex items-center gap-2 font-extrabold">
          {invite.employer.verified ? <BadgeCheck className="text-good" size={18} /> : null}
          Employer trust check
        </h2>
        <p className="mt-1 text-sm text-muted">
          {invite.employer.company_name}
          {invite.employer.trust_score != null ? ` — score ${invite.employer.trust_score}/100` : ""}
        </p>
        {invite.employer.trust_evidence?.length ? (
          <ul className="mt-3 space-y-1.5 text-sm text-muted">
            {invite.employer.trust_evidence.map((line) => <li key={line}>{line}</li>)}
          </ul>
        ) : (
          <p className="mt-3 text-sm text-muted">
            No automated evidence on file — run a Trust Check from the sidebar
            if you want a fresh report.
          </p>
        )}
      </section>
    </div>
  );
}
