"use client";

/**
 * Admin directory panels with client-side filtering. The admin page renders
 * every user/employer row it got from the API; these wrap them in a search
 * box so the owner can find an account without scrolling once the lists grow.
 */
import { useMemo, useState } from "react";
import { BadgeCheck, Search } from "lucide-react";
import { GrantCreditsButton } from "@/components/GrantCreditsButton";

export interface AdminUserRow {
  id: string; email: string; name: string | null; created_at: string;
  has_twin: boolean; twin_complete: boolean;
}

export interface AdminEmployerRow {
  id: number; company_name: string; company_domain: string | null;
  trust_level: string | null; warm_intro_by: string | null; credit_balance: number;
}

function SearchBox({ value, onChange, placeholder }: {
  value: string; onChange: (v: string) => void; placeholder: string;
}) {
  return (
    <label className="flex w-full max-w-xs items-center gap-2 rounded-xl border border-line bg-surface px-3 py-2">
      <Search size={14} className="shrink-0 text-faint" />
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full bg-transparent text-xs font-semibold outline-none placeholder:text-faint"
      />
    </label>
  );
}

export function AdminUsersTable({ users }: { users: AdminUserRow[] }) {
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return users;
    return users.filter((u) =>
      u.email.toLowerCase().includes(q) || (u.name ?? "").toLowerCase().includes(q));
  }, [users, query]);

  if (users.length === 0) return <p className="mt-4 text-sm text-muted">No users yet.</p>;
  return (
    <div className="mt-4 space-y-3">
      <SearchBox value={query} onChange={setQuery} placeholder="Search name or email…" />
      {filtered.length === 0 ? (
        <p className="text-sm text-muted">No users match “{query}”.</p>
      ) : (
        <div className="overflow-x-auto">
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
              {filtered.map((u) => (
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
    </div>
  );
}

export function AdminEmployersList({ employers }: { employers: AdminEmployerRow[] }) {
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return employers;
    return employers.filter((e) =>
      e.company_name.toLowerCase().includes(q) || (e.company_domain ?? "").toLowerCase().includes(q));
  }, [employers, query]);

  if (employers.length === 0) return <p className="mt-4 text-sm text-muted">No employers yet.</p>;
  return (
    <div className="mt-4 space-y-3">
      <SearchBox value={query} onChange={setQuery} placeholder="Search company or domain…" />
      {filtered.length === 0 ? (
        <p className="text-sm text-muted">No employers match “{query}”.</p>
      ) : (
        <ul className="divide-y divide-line">
          {filtered.map((emp) => (
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
    </div>
  );
}
