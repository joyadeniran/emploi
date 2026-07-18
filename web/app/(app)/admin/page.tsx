import { notFound } from "next/navigation";
import { BadgeCheck, Coins, ShieldAlert, Users } from "lucide-react";
import { isAdmin } from "@/lib/admin";
import { ApiUnavailableError, apiFetch } from "@/lib/api";
import { VouchButton } from "@/components/VouchButton";
import { GrantCreditsButton } from "@/components/GrantCreditsButton";

interface Metrics {
  career_twins: number; twins_opted_in: number; employers: number;
  employers_vouched: number; roles_open: number; roles_hired: number;
  invites: Record<string, number>; unlocks_total: number;
  credits_purchased: number; jobs_ingested_today: number;
  applications: number; generations_last_30d: number;
  trust_alerts: { id: number; company_name: string; company_domain: string | null;
                  trust_score: number | null; trust_level: string | null }[];
}

interface EmployerRow {
  id: number; company_name: string; company_domain: string | null;
  trust_level: string | null; warm_intro_by: string | null; credit_balance: number;
}

interface UserRow {
  id: string; email: string; name: string | null; created_at: string;
  has_twin: boolean; twin_complete: boolean;
}

export default async function AdminPage() {
  if (!(await isAdmin())) notFound();
  let metrics: Metrics;
  let employers: EmployerRow[] = [];
  let users: UserRow[] = [];
  try {
    [metrics, { employers }, { users }] = await Promise.all([
      apiFetch<Metrics>("/admin/metrics"),
      apiFetch<{ employers: EmployerRow[] }>("/admin/employers"),
      apiFetch<{ users: UserRow[] }>("/admin/users"),
    ]);
  } catch (error) {
    if (error instanceof ApiUnavailableError)
      return <p className="text-sm text-muted">API offline — try again shortly.</p>;
    throw error;
  }

  const invites = metrics.invites ?? {};
  const tiles: [string, number | string][] = [
    ["Career Twins", metrics.career_twins],
    ["Opted-in (discoverable)", metrics.twins_opted_in],
    ["Employers", metrics.employers],
    ["Vouched employers", metrics.employers_vouched],
    ["Open roles", metrics.roles_open],
    ["Hires", metrics.roles_hired],
    ["Invites pending", invites.pending ?? 0],
    ["Invites accepted", (invites.accepted ?? 0) + (invites.hired ?? 0)],
    ["Candidate unlocks", metrics.unlocks_total],
    ["Credits purchased", metrics.credits_purchased],
    ["Jobs ingested (24h)", metrics.jobs_ingested_today],
    ["Drafts generated (30d)", metrics.generations_last_30d],
  ];

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <header>
        <h1 className="text-2xl font-extrabold tracking-tight sm:text-3xl">Admin</h1>
        <p className="mt-1 text-sm text-muted">Live platform rollup. Counts only — no candidate PII.</p>
      </header>

      <section className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {tiles.map(([label, value]) => (
          <div key={label} className="rounded-2xl border border-line bg-card p-4 shadow-card">
            <p className="text-2xl font-extrabold">{value}</p>
            <p className="mt-0.5 text-xs font-semibold text-muted">{label}</p>
          </div>
        ))}
      </section>

      <section className="rounded-2xl border border-line bg-card p-6 shadow-card">
        <h2 className="flex items-center gap-2 font-extrabold">
          <ShieldAlert className="text-warn" size={18} /> Trust alerts
        </h2>
        <p className="mt-1 text-xs text-muted">
          Low-trust employers who signed up cold. Vouch the ones you know
          personally — vouching clears their badge restriction.
        </p>
        {metrics.trust_alerts.length === 0 ? (
          <p className="mt-4 text-sm text-muted">No low-trust employers right now.</p>
        ) : (
          <ul className="mt-4 divide-y divide-line">
            {metrics.trust_alerts.map((alert) => (
              <li key={alert.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div>
                  <p className="text-sm font-bold">{alert.company_name}</p>
                  <p className="text-xs text-muted">
                    {alert.company_domain ?? "no domain"} · score {alert.trust_score ?? "—"} · {alert.trust_level}
                  </p>
                </div>
                <VouchButton employerId={alert.id} />
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-2xl border border-line bg-card p-6 shadow-card">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="flex items-center gap-2 font-extrabold">
            <Users className="text-brand" size={18} /> Users
            <span className="rounded-full bg-surface px-2 py-0.5 text-xs font-bold text-muted">{users.length}</span>
          </h2>
          <p className="text-xs text-muted">Signed-in accounts. Contains email — owner-only.</p>
        </div>
        {users.length === 0 ? (
          <p className="mt-4 text-sm text-muted">No users yet.</p>
        ) : (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[520px] text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs font-bold uppercase text-faint">
                  <th className="py-2 pr-3">Name</th>
                  <th className="py-2 pr-3">Email</th>
                  <th className="py-2 pr-3">Career Twin</th>
                  <th className="py-2">Joined</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id} className="border-b border-line last:border-0">
                    <td className="py-2 pr-3 font-semibold">{u.name || "—"}</td>
                    <td className="py-2 pr-3">
                      <a href={`mailto:${u.email}`} className="font-semibold text-brand hover:underline">{u.email}</a>
                    </td>
                    <td className="py-2 pr-3">
                      {u.twin_complete ? (
                        <span className="rounded-full bg-good-soft px-2 py-0.5 text-[11px] font-bold text-good">Active</span>
                      ) : u.has_twin ? (
                        <span className="rounded-full bg-amber-soft px-2 py-0.5 text-[11px] font-bold text-amber">Started</span>
                      ) : (
                        <span className="rounded-full bg-surface px-2 py-0.5 text-[11px] font-bold text-muted">None</span>
                      )}
                    </td>
                    <td className="py-2 text-muted">{u.created_at.slice(0, 10)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="rounded-2xl border border-line bg-card p-6 shadow-card">
        <h2 className="flex items-center gap-2 font-extrabold">
          <Coins className="text-brand" size={18} /> Employers &amp; credits
        </h2>
        <p className="mt-1 text-xs text-muted">
          Grant free unlock credits — comp a partner or fix a billing mishap.
          Credits are not verification; they only affect how many candidates an
          employer can unlock.
        </p>
        {employers.length === 0 ? (
          <p className="mt-4 text-sm text-muted">No employers yet.</p>
        ) : (
          <ul className="mt-4 divide-y divide-line">
            {employers.map((emp) => (
              <li key={emp.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div className="min-w-0">
                  <p className="flex items-center gap-1.5 text-sm font-bold">
                    {emp.company_name}
                    {emp.warm_intro_by ? <BadgeCheck size={13} className="text-good" /> : null}
                  </p>
                  <p className="text-xs text-muted">
                    {emp.company_domain ?? "no domain"} · trust {emp.trust_level ?? "—"} ·{" "}
                    <span className="font-semibold text-ink">{emp.credit_balance} credit{emp.credit_balance === 1 ? "" : "s"}</span>
                  </p>
                </div>
                <GrantCreditsButton employerId={emp.id} companyName={emp.company_name} balance={emp.credit_balance} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
