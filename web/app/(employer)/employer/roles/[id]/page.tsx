import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { ApiUnavailableError, apiFetch } from "@/lib/api";
import { RoleWorkbench } from "@/components/RoleWorkbench";
import { CloseRoleButton } from "@/components/CloseRoleButton";
import { ShareJobLink } from "@/components/ShareJobLink";

interface Role {
  id: number; title: string; description: string; location: string | null;
  is_remote: number | boolean; salary_text: string | null; status: string;
  is_free: number | boolean; invites_sent: number; created_at: string;
  close_reason: string | null;
}

interface Applicant {
  candidate_user_id: string; status: string; applied_at: string;
  contact: { name?: string; email?: string; headline?: string; location?: string; skills?: string[] };
}

export default async function RoleDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  let role: Role;
  try {
    ({ role } = await apiFetch<{ role: Role }>(`/employer/roles/${id}`));
  } catch (error) {
    if (error instanceof ApiUnavailableError) throw error;
    const status = (error as { status?: number }).status;
    if (status === 404) {
      // Either not their role or no employer account at all.
      try {
        await apiFetch("/employer");
      } catch {
        redirect("/employer/onboarding");
      }
      notFound();
    }
    throw error;
  }

  // Inbound applicants (public-link applies). Non-fatal if it fails — the rest
  // of the page still renders.
  let applicants: Applicant[] = [];
  try {
    ({ applicants } = await apiFetch<{ applicants: Applicant[] }>(`/employer/roles/${id}/applicants`));
  } catch { /* leave empty */ }

  const isFree = Boolean(role.is_free);
  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <Link href="/employer" className="inline-flex items-center gap-1.5 text-sm font-bold text-muted hover:text-brand">
        <ArrowLeft size={15} /> All roles
      </Link>
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight sm:text-3xl">
            {role.title}
            {isFree ? (
              <span className="ml-2 align-middle rounded-full bg-brand-soft px-2.5 py-1 text-[11px] font-bold uppercase text-brand">
                Free role
              </span>
            ) : null}
          </h1>
          <p className="mt-1 text-sm text-muted">
            {Boolean(role.is_remote) ? "Remote" : role.location || "Location unspecified"}
            {role.salary_text ? ` · ${role.salary_text}` : ""}
            {" · "}
            <span className="capitalize">{role.status}</span>
          </p>
          <p className="mt-1 text-xs text-muted">
            {isFree
              ? "Free role: invite up to 10 candidates — contact details are shared when a candidate accepts."
              : "Paid role: unlock a candidate (1 credit = ₦1,000) to see their contact details and invite them."}
          </p>
        </div>
        {role.status === "open" ? <CloseRoleButton roleId={role.id} /> : null}
      </header>

      <details className="rounded-2xl border border-line bg-card p-5 shadow-card">
        <summary className="cursor-pointer text-sm font-bold">Job description</summary>
        <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-muted">
          {role.description}
        </p>
      </details>

      {role.status === "open" ? <ShareJobLink roleId={role.id} /> : null}

      <section className="space-y-3">
        <h2 className="flex items-center gap-2 font-extrabold">
          Applicants
          {applicants.length > 0 ? (
            <span className="rounded-full bg-brand px-2 py-0.5 text-[11px] font-bold text-white">{applicants.length}</span>
          ) : null}
        </h2>
        {applicants.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-line bg-card p-5 text-sm text-muted">
            No direct applicants yet. Share the job link above — anyone who applies through it
            appears here with their contact details (no credit needed — they came to you).
          </p>
        ) : (
          <ul className="space-y-2">
            {applicants.map((a) => (
              <li key={a.candidate_user_id} className="rounded-2xl border border-line bg-card p-4 shadow-card">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="font-bold">{a.contact.name || "Applicant"}</p>
                    {a.contact.headline ? <p className="text-xs text-muted">{a.contact.headline}</p> : null}
                    {a.contact.email ? (
                      <a href={`mailto:${a.contact.email}`} className="text-sm font-semibold text-brand hover:underline">
                        {a.contact.email}
                      </a>
                    ) : null}
                  </div>
                  {a.contact.location ? <span className="text-xs text-muted">{a.contact.location}</span> : null}
                </div>
                {a.contact.skills && a.contact.skills.length > 0 ? (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {a.contact.skills.slice(0, 6).map((s) => (
                      <span key={s} className="rounded-full bg-brand-soft px-2 py-0.5 text-[11px] font-bold text-brand">{s}</span>
                    ))}
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      <RoleWorkbench roleId={role.id} isFree={isFree} status={role.status} />
    </div>
  );
}
