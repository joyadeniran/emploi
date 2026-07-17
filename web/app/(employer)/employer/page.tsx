import Link from "next/link";
import { redirect } from "next/navigation";
import { BadgeCheck, Coins, Plus, ShieldAlert, ShieldQuestion } from "lucide-react";
import { ApiUnavailableError, apiFetch } from "@/lib/api";

interface Employer {
  id: number;
  company_name: string;
  company_domain: string | null;
  trust_score: number | null;
  trust_level: string | null;
  warm_intro_by: string | null;
  free_role_used: boolean;
  credit_balance: number;
}

interface RoleRow {
  id: number;
  title: string;
  status: string;
  is_free: boolean;
  invites_sent: number;
  accepted_count: number;
  unread_responses: number;
  created_at: string;
}

function TrustBadge({ employer }: { employer: Employer }) {
  if (employer.warm_intro_by || employer.trust_level === "high")
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-good-soft px-3 py-1 text-xs font-bold text-good">
        <BadgeCheck size={14} /> Verified Employer
      </span>
    );
  if (employer.trust_level === "medium")
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-soft px-3 py-1 text-xs font-bold text-amber">
        <ShieldQuestion size={14} /> Trust: medium
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-warn-soft px-3 py-1 text-xs font-bold text-warn">
      <ShieldAlert size={14} /> Trust: {employer.trust_level ?? "unverified"}
    </span>
  );
}

export default async function EmployerDashboardPage() {
  let employer: Employer;
  let roles: RoleRow[] = [];
  try {
    ({ employer } = await apiFetch<{ employer: Employer }>("/employer"));
    ({ roles } = await apiFetch<{ roles: RoleRow[] }>("/employer/roles"));
  } catch (error) {
    if (error instanceof ApiUnavailableError) throw error;
    if ((error as { status?: number }).status === 404) redirect("/employer/onboarding");
    throw error;
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight sm:text-3xl">
            {employer.company_name}
          </h1>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-muted">
            <TrustBadge employer={employer} />
            {employer.company_domain ? <span>{employer.company_domain}</span> : null}
          </div>
          {/* Without this, a legitimate employer sees a middling badge and no
              reason for it. "Verified" now requires proof of domain control,
              which nothing can grant yet — so say what's true and don't imply
              they did something wrong. */}
          {!employer.warm_intro_by && employer.trust_level !== "high" ? (
            <p className="mt-2 max-w-md text-xs leading-relaxed text-muted">
              We&apos;ve checked that{" "}
              <span className="font-semibold">{employer.company_domain ?? "your domain"}</span>{" "}
              looks legitimate. The <span className="font-semibold">Verified Employer</span> badge
              additionally requires confirming you control that domain — we&apos;re rolling that out
              shortly. Candidates can still see and accept your invites.
            </p>
          ) : null}
        </div>
        <Link
          href="/employer/roles/new"
          className="inline-flex items-center gap-2 rounded-xl bg-brand px-4 py-2.5 text-sm font-bold text-white"
        >
          <Plus size={16} /> Post a role
        </Link>
      </header>

      <section className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-line bg-card p-5 shadow-card">
        <div className="flex items-center gap-3">
          <Coins className="text-brand" size={20} />
          <div>
            <p className="text-sm font-bold">
              {employer.credit_balance} unlock credit{employer.credit_balance === 1 ? "" : "s"}
            </p>
            <p className="text-xs text-muted">
              {employer.free_role_used
                ? "Roles after your first use 1 credit (₦1,000) per candidate you unlock."
                : "Your first role is free — invite up to 10 candidates, no credits needed."}
            </p>
          </div>
        </div>
        <Link href="/employer/billing" className="rounded-xl border border-line px-4 py-2 text-sm font-bold hover:bg-surface">
          Buy credits
        </Link>
      </section>

      <section className="space-y-3">
        <h2 className="font-extrabold">Your roles</h2>
        {roles.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-line bg-card p-8 text-center">
            <p className="font-bold">No roles yet</p>
            <p className="mt-1 text-sm text-muted">
              Post your first role free — paste a job URL or the description text,
              and Emploi builds your candidate shortlist.
            </p>
            <Link href="/employer/roles/new" className="mt-4 inline-block rounded-xl bg-brand px-4 py-2.5 text-sm font-bold text-white">
              Post your first role
            </Link>
          </div>
        ) : (
          roles.map((role) => (
            <Link
              key={role.id}
              href={`/employer/roles/${role.id}`}
              className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-line bg-card p-5 shadow-card transition-shadow hover:shadow-pop"
            >
              <div>
                <p className="font-bold">
                  {role.title}
                  {role.is_free ? (
                    <span className="ml-2 rounded-full bg-brand-soft px-2 py-0.5 text-[10px] font-bold uppercase text-brand">
                      Free role
                    </span>
                  ) : null}
                </p>
                <p className="mt-1 text-xs text-muted">
                  {role.invites_sent} invited · {role.accepted_count} accepted
                </p>
              </div>
              <div className="flex items-center gap-2">
                {role.unread_responses > 0 ? (
                  <span className="rounded-full bg-brand px-2.5 py-1 text-xs font-bold text-white">
                    {role.unread_responses} new
                  </span>
                ) : null}
                <span className={`rounded-full px-3 py-1 text-xs font-bold capitalize ${
                  role.status === "open" ? "bg-good-soft text-good"
                  : role.status === "hired" ? "bg-brand-soft text-brand"
                  : "bg-surface text-muted"
                }`}>
                  {role.status}
                </span>
              </div>
            </Link>
          ))
        )}
      </section>
    </div>
  );
}
