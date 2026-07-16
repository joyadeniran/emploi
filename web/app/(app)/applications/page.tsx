"use client";

import { useEffect, useState } from "react";
import { Info, Loader2 } from "lucide-react";
import {
  applications as demoApplications,
  statusMeta,
  type ApplicationStatus,
} from "@/lib/data";

interface Row {
  id: number | string;
  role: string;
  company: string;
  companyInitial: string;
  companyColor: string;
  appliedOn: string;
  status: ApplicationStatus;
  nextStep?: string;
  nextStepDate?: string;
}

interface ApiRow {
  id: number;
  company: string | null;
  role: string | null;
  status: string | null;
  created_at: string;
  [k: string]: unknown;
}

const FILTERS: ("all" | ApplicationStatus)[] = [
  "all",
  "applied",
  "interview",
  "offer",
  "rejected",
  "withdrawn",
];

const STATUSES: ApplicationStatus[] = [
  "applied",
  "interview",
  "offer",
  "rejected",
  "withdrawn",
];

const PALETTE = ["#04114d", "#5b4ffd", "#f79009", "#0e9f6e", "#1570ef", "#d92d20"];

function fromApi(r: ApiRow): Row {
  const company = r.company ?? "Unknown";
  return {
    id: r.id,
    role: r.role ?? "—",
    company,
    companyInitial: (company[0] ?? "?").toUpperCase(),
    companyColor: PALETTE[Math.abs(hash(company)) % PALETTE.length],
    appliedOn: (r.created_at ?? "").slice(0, 10),
    status: (STATUSES as string[]).includes(r.status ?? "")
      ? (r.status as ApplicationStatus)
      : "applied",
    nextStep: typeof r.next_step === "string" ? r.next_step : undefined,
  };
}

function hash(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h << 5) - h + s.charCodeAt(i);
  return h;
}

export default function ApplicationsPage() {
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("all");
  const [rows, setRows] = useState<Row[] | null>(null);
  const [live, setLive] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/applications");
        if (!res.ok) throw new Error("offline");
        const data = (await res.json()) as { applications: ApiRow[] };
        if (!cancelled) {
          setRows(data.applications.map(fromApi));
          setLive(true);
        }
      } catch {
        if (!cancelled) {
          setRows(demoApplications as Row[]);
          setLive(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function changeStatus(row: Row, status: ApplicationStatus) {
    const prev = row.status;
    setRows((rs) =>
      rs ? rs.map((r) => (r.id === row.id ? { ...r, status } : r)) : rs,
    );
    if (!live) return; // demo data: local-only change
    try {
      const res = await fetch(`/api/applications/${row.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      if (!res.ok) throw new Error();
    } catch {
      // network failure or API error — revert the optimistic update
      setRows((rs) =>
        rs ? rs.map((r) => (r.id === row.id ? { ...r, status: prev } : r)) : rs,
      );
    }
  }

  const visible =
    rows === null
      ? null
      : filter === "all"
        ? rows
        : rows.filter((a) => a.status === filter);

  return (
    <div className="mx-auto max-w-6xl">
      <h1 className="rise-in text-2xl font-extrabold tracking-tight sm:text-3xl">
        Applications
      </h1>
      <p className="mt-1 text-sm text-muted">
        Everything your Career Twin has sent, and where each one stands.
      </p>

      {rows !== null && !live ? (
        <p className="mt-4 inline-flex items-center gap-2 rounded-xl bg-amber-soft px-4 py-2.5 text-xs font-semibold text-ink">
          <Info size={14} className="shrink-0" />
          Showing sample data — the Emploi API isn&apos;t reachable, so changes
          here won&apos;t be saved.
        </p>
      ) : null}

      <div className="mt-6 flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`rounded-full px-4 py-2 text-xs font-bold capitalize transition-colors ${
              filter === f
                ? "bg-brand text-white"
                : "border border-line bg-card text-muted hover:bg-surface"
            }`}
            aria-pressed={filter === f}
          >
            {f === "all" ? "All" : statusMeta[f].label}
          </button>
        ))}
      </div>

      <div className="rise-in mt-4 overflow-x-auto rounded-2xl border border-line bg-card shadow-card">
        <table className="w-full min-w-[680px] text-sm">
          <thead>
            <tr className="border-b border-line bg-surface/60 text-left text-xs font-bold uppercase tracking-wide text-faint">
              <th className="px-5 py-3.5">Role</th>
              <th className="px-5 py-3.5">Company</th>
              <th className="px-5 py-3.5">Applied On</th>
              <th className="px-5 py-3.5">Status</th>
              <th className="px-5 py-3.5">Next Step</th>
            </tr>
          </thead>
          <tbody>
            {visible === null ? (
              <tr>
                <td colSpan={5} className="px-5 py-12 text-center">
                  <Loader2 size={18} className="mx-auto animate-spin text-faint" />
                </td>
              </tr>
            ) : visible.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-5 py-12 text-center text-sm text-muted">
                  {filter === "all"
                    ? "No applications yet — apply to a match and it appears here."
                    : "No applications with this status yet."}
                </td>
              </tr>
            ) : (
              visible.map((a) => (
                <tr key={a.id} className="border-b border-line last:border-0">
                  <td className="px-5 py-4 font-bold">{a.role}</td>
                  <td className="px-5 py-4">
                    <span className="flex items-center gap-2.5">
                      <span
                        className="flex h-7 w-7 items-center justify-center rounded-lg text-xs font-extrabold text-white"
                        style={{ background: a.companyColor }}
                      >
                        {a.companyInitial}
                      </span>
                      {a.company}
                    </span>
                  </td>
                  <td className="px-5 py-4 text-muted">{a.appliedOn}</td>
                  <td className="px-5 py-4">
                    <select
                      value={a.status}
                      onChange={(e) =>
                        changeStatus(a, e.target.value as ApplicationStatus)
                      }
                      aria-label={`Status for ${a.role} at ${a.company}`}
                      className={`cursor-pointer rounded-full border-0 px-3 py-1.5 text-xs font-bold outline-none ${statusMeta[a.status].className}`}
                    >
                      {STATUSES.map((s) => (
                        <option key={s} value={s}>
                          {statusMeta[s].label}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-5 py-4">
                    {a.nextStep ? (
                      <>
                        <span className="block font-semibold">{a.nextStep}</span>
                        {a.nextStepDate ? (
                          <span className="text-xs text-muted">{a.nextStepDate}</span>
                        ) : null}
                      </>
                    ) : (
                      <span className="text-faint">—</span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
