import Link from "next/link";
import { BadgeCheck, Info, ChevronLeft, ChevronRight } from "lucide-react";
import { FitRing } from "@/components/ProgressRing";
import { ApplyButton } from "@/components/ApplyButton";
import { SaveJobButton } from "@/components/SaveJobButton";
import { matches as demoMatches } from "@/lib/data";
import { ApiUnavailableError, apiFetch, DEMO_MODE, toMatchCard, type ApiMatch } from "@/lib/api";

export const metadata = { title: "Job Matches — Emploi" };

const PAGE_SIZE = 20;

export default async function MatchesPage({
  searchParams,
}: {
  searchParams: Promise<{ page?: string }>;
}) {
  const { page: pageParam } = await searchParams;
  const page = Math.max(1, Number(pageParam ?? 1));
  const offset = (page - 1) * PAGE_SIZE;

  let matchData = DEMO_MODE ? demoMatches : [];
  let sampleData = DEMO_MODE;
  let error = "";
  let savedIds = new Set<number>();
  let total = DEMO_MODE ? demoMatches.length : 0;

  if (!DEMO_MODE) {
    try {
      const [matchRes, savedRes] = await Promise.all([
        apiFetch<{ matches: ApiMatch[]; total: number }>(
          `/matches?limit=${PAGE_SIZE}&offset=${offset}`
        ),
        apiFetch<{ saved: { id: number }[] }>("/saved-jobs"),
      ]);
      matchData = matchRes.matches.map(toMatchCard);
      total = matchRes.total;
      savedIds = new Set(savedRes.saved.map((s) => s.id));
    } catch (caught) {
      if (caught instanceof ApiUnavailableError) {
        matchData = demoMatches;
        sampleData = true;
        total = demoMatches.length;
      } else {
        error = "We couldn't load your matches just now. Please refresh in a moment.";
      }
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="mx-auto max-w-5xl">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="rise-in text-2xl font-extrabold tracking-tight sm:text-3xl">Job Matches</h1>
          <p className="mt-1 text-sm text-muted">
            Every opportunity is scored honestly against your real experience. Trust checks remain visible evidence, never an assumption.
          </p>
        </div>
        <div className="flex gap-2">
          <Link href="/jobs" className="rounded-xl border border-line bg-card px-4 py-2.5 text-sm font-bold text-brand shadow-card hover:bg-brand-soft">Browse all jobs</Link>
          <Link href="/import-job" className="rounded-xl border border-line bg-card px-4 py-2.5 text-sm font-bold text-brand shadow-card hover:bg-brand-soft">Import a job</Link>
        </div>
      </div>

      {sampleData ? (
        <p className="mt-4 inline-flex items-center gap-2 rounded-xl bg-amber-soft px-4 py-2.5 text-xs font-semibold text-ink">
          <Info size={14} />Showing sample data — the Emploi API is unavailable.
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="mt-4 rounded-xl bg-warn-soft px-4 py-3 text-sm font-semibold text-warn">{error}</p>
      ) : null}

      {total > 0 ? (
        <p className="mt-4 text-xs text-muted">
          Showing {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total} matches
        </p>
      ) : null}

      <div className="mt-4 space-y-4">
        {matchData.map((m) => (
          <article key={m.id} className="rise-in rounded-2xl border border-line bg-card p-5 shadow-card sm:p-6">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
              <span
                className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl text-lg font-extrabold text-white"
                style={{ background: m.companyColor }}
              >
                {m.companyInitial}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="font-bold">{m.title}</h2>
                  {m.isNew ? (
                    <span className="rounded-full bg-brand-soft px-2 py-0.5 text-[10px] font-bold uppercase text-brand">New</span>
                  ) : null}
                </div>
                <p className="text-sm text-muted">{m.company} · {m.location} ({m.workMode}) · {m.employment} · {m.salary}</p>
                {m.verified ? (
                  <span className="mt-2 inline-flex items-center gap-1 rounded-md bg-good-soft px-2 py-0.5 text-xs font-bold text-good">
                    <BadgeCheck size={12} /> Employer verified
                  </span>
                ) : null}
                <p className="mt-3 rounded-xl bg-surface px-4 py-3 text-sm leading-relaxed text-muted">
                  <span className="font-bold text-ink">Why this match: </span>{m.reason}
                </p>
              </div>
              <div className="flex items-center gap-3 sm:flex-col sm:items-end">
                <FitRing fit={m.fit} size={56} />
                <div className="flex gap-2">
                  <SaveJobButton jobId={m.jobId} title={m.title} initialSaved={m.jobId ? savedIds.has(m.jobId) : false} />
                  <ApplyButton match={m} />
                </div>
              </div>
            </div>
          </article>
        ))}

        {!sampleData && !error && matchData.length === 0 ? (
          <div className="rounded-2xl border border-line bg-card p-10 text-center shadow-card">
            <h2 className="font-extrabold">Your Career Twin is getting to work</h2>
            <p className="mt-2 text-sm text-muted">No matches yet. We&apos;ll show verified opportunities here after the next matching run.</p>
          </div>
        ) : null}
      </div>

      {totalPages > 1 ? (
        <div className="mt-8 flex items-center justify-center gap-2">
          {page > 1 ? (
            <Link
              href={`/matches?page=${page - 1}`}
              className="flex items-center gap-1 rounded-xl border border-line bg-card px-4 py-2.5 text-sm font-bold text-brand shadow-card hover:bg-brand-soft"
            >
              <ChevronLeft size={16} /> Previous
            </Link>
          ) : (
            <span className="flex items-center gap-1 rounded-xl border border-line px-4 py-2.5 text-sm font-bold text-faint opacity-40 cursor-not-allowed">
              <ChevronLeft size={16} /> Previous
            </span>
          )}

          <span className="px-4 py-2.5 text-sm font-semibold text-muted">
            Page {page} of {totalPages}
          </span>

          {page < totalPages ? (
            <Link
              href={`/matches?page=${page + 1}`}
              className="flex items-center gap-1 rounded-xl border border-line bg-card px-4 py-2.5 text-sm font-bold text-brand shadow-card hover:bg-brand-soft"
            >
              Next <ChevronRight size={16} />
            </Link>
          ) : (
            <span className="flex items-center gap-1 rounded-xl border border-line px-4 py-2.5 text-sm font-bold text-faint opacity-40 cursor-not-allowed">
              Next <ChevronRight size={16} />
            </span>
          )}
        </div>
      ) : null}
    </div>
  );
}
