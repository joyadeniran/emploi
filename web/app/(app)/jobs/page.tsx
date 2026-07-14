import Link from "next/link";
import { BadgeCheck, ClipboardPaste, Info, Search } from "lucide-react";
import { ApiUnavailableError, apiFetch, DEMO_MODE, toJobCard, type ApiJob } from "@/lib/api";
import { ApplyButton } from "@/components/ApplyButton";
import { SaveJobButton } from "@/components/SaveJobButton";
import { PagePlaceholder } from "@/components/PagePlaceholder";

export const metadata = { title: "Browse Jobs — Emploi" };

export default async function JobsPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; remote?: string }>;
}) {
  const params = await searchParams;
  const q = (params.q ?? "").trim();
  const remoteOnly = params.remote === "true";

  if (DEMO_MODE) {
    return <PagePlaceholder icon={Search} title="Browse Jobs" blurb="Search the live job pool in demo mode." note="Connect the API to browse ingested jobs." />;
  }

  let jobs: ApiJob[] = [];
  let total = 0;
  let offline = false;
  let savedIds = new Set<number>();
  try {
    const qs = new URLSearchParams({ limit: "30" });
    if (q) qs.set("q", q);
    if (remoteOnly) qs.set("remote_only", "true");
    const [data, savedRes] = await Promise.all([
      apiFetch<{ jobs: ApiJob[]; total: number }>(`/jobs?${qs.toString()}`),
      apiFetch<{ saved: { id: number }[] }>("/saved-jobs"),
    ]);
    jobs = data.jobs;
    total = data.total;
    savedIds = new Set(savedRes.saved.map((s) => s.id));
  } catch (e) {
    if (e instanceof ApiUnavailableError) offline = true;
    else throw e;
  }

  if (offline) {
    return <PagePlaceholder icon={Info} title="Job pool unavailable" blurb="We can’t reach the job pool right now." note="Please refresh in a moment." />;
  }

  return (
    <div className="mx-auto max-w-5xl">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="rise-in text-2xl font-extrabold tracking-tight sm:text-3xl">Browse Jobs</h1>
          <p className="mt-1 text-sm text-muted">
            {total.toLocaleString()} live openings from verified job boards, refreshed hourly.
          </p>
        </div>
        <Link href="/import-job"
          className="inline-flex items-center gap-1.5 rounded-xl border border-line bg-white px-4 py-2.5 text-sm font-bold text-brand shadow-card hover:bg-brand-soft">
          <ClipboardPaste size={15} /> Found a job elsewhere? Import it
        </Link>
      </div>

      {/* Plain GET form — works without JS, keeps state in the URL. */}
      <form method="get" className="mt-5 flex flex-wrap items-center gap-3">
        <div className="relative min-w-64 flex-1">
          <Search size={16} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-faint" />
          <input type="search" name="q" defaultValue={q}
            placeholder="Search title, company or keywords…"
            className="w-full rounded-full border border-line bg-white py-2.5 pl-10 pr-4 text-sm outline-none focus:border-brand/40" />
        </div>
        <label className="inline-flex items-center gap-2 text-sm font-semibold text-muted">
          <input type="checkbox" name="remote" value="true" defaultChecked={remoteOnly}
            className="h-4 w-4 rounded border-line accent-[--color-brand]" />
          Remote only
        </label>
        <button type="submit" className="rounded-xl bg-brand px-5 py-2.5 text-sm font-bold text-white">
          Search
        </button>
      </form>

      <div className="mt-6 space-y-3">
        {jobs.length === 0 ? (
          <p className="rounded-2xl border border-line bg-white p-8 text-center text-sm text-muted shadow-card">
            {q ? <>No jobs match &ldquo;{q}&rdquo; yet — try broader keywords, or <Link href="/import-job" className="font-bold text-brand hover:underline">import one you found elsewhere</Link>.</>
              : "The job pool is refreshing — check back shortly."}
          </p>
        ) : (
          jobs.map((row) => {
            const card = toJobCard(row);
            return (
              <article key={card.id}
                className="flex flex-col gap-4 rounded-2xl border border-line bg-white p-4 shadow-card sm:flex-row sm:items-center sm:p-5">
                <div className="flex min-w-0 flex-1 items-center gap-4">
                  <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl text-lg font-extrabold text-white"
                    style={{ background: card.companyColor }}>
                    {card.companyInitial}
                  </span>
                  <div className="min-w-0">
                    <h2 className="truncate font-bold">{card.title}</h2>
                    <p className="truncate text-sm text-muted">
                      {card.company} · {card.location}
                    </p>
                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                      {card.workMode === "Remote" ? (
                        <span className="inline-flex items-center gap-1 rounded-md bg-good-soft px-2 py-0.5 text-xs font-bold text-good">
                          <BadgeCheck size={12} /> Remote
                        </span>
                      ) : null}
                      <span className="rounded-md bg-surface px-2 py-0.5 text-xs font-semibold text-muted">{card.salary}</span>
                      {row.category ? <span className="rounded-md bg-surface px-2 py-0.5 text-xs font-semibold text-muted">{row.category}</span> : null}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2 sm:border-l sm:border-line sm:pl-5">
                  <SaveJobButton jobId={card.jobId} title={card.title} initialSaved={card.jobId ? savedIds.has(card.jobId) : false} />
                  <ApplyButton match={card} />
                </div>
              </article>
            );
          })
        )}
      </div>
    </div>
  );
}
