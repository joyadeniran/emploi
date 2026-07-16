import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { ApiUnavailableError, apiFetch } from "@/lib/api";
import { RoleWorkbench } from "@/components/RoleWorkbench";
import { CloseRoleButton } from "@/components/CloseRoleButton";

interface Role {
  id: number; title: string; description: string; location: string | null;
  is_remote: number | boolean; salary_text: string | null; status: string;
  is_free: number | boolean; invites_sent: number; created_at: string;
  close_reason: string | null;
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

      <details className="rounded-2xl border border-line bg-white p-5 shadow-card">
        <summary className="cursor-pointer text-sm font-bold">Job description</summary>
        <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-muted">
          {role.description}
        </p>
      </details>

      <RoleWorkbench roleId={role.id} isFree={isFree} status={role.status} />
    </div>
  );
}
