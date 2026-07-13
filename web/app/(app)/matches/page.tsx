import { BadgeCheck, Bookmark, Info } from "lucide-react";
import { FitRing } from "@/components/ProgressRing";
import { ApplyButton } from "@/components/ApplyButton";
import { matches as demoMatches } from "@/lib/data";
import { ApiUnavailableError, apiFetch, DEMO_MODE, toMatchCard, type ApiMatch } from "@/lib/api";

export const metadata = { title: "Job Matches — Emploi" };

export default async function MatchesPage() {
  let matchData = DEMO_MODE ? demoMatches : [];
  let sampleData = DEMO_MODE;
  let error = "";

  if (!DEMO_MODE) {
    try {
      const { matches } = await apiFetch<{ matches: ApiMatch[] }>("/matches?limit=50");
      matchData = matches.map(toMatchCard);
    } catch (caught) {
      if (caught instanceof ApiUnavailableError) {
        matchData = demoMatches;
        sampleData = true;
      } else {
        error = "We couldn't load your matches just now. Please refresh in a moment.";
      }
    }
  }

  return (
    <div className="mx-auto max-w-5xl">
      <h1 className="rise-in text-2xl font-extrabold tracking-tight sm:text-3xl">Job Matches</h1>
      <p className="mt-1 text-sm text-muted">
        Every opportunity is scored honestly against your real experience. Trust checks remain visible evidence, never an assumption.
      </p>
      {sampleData ? <p className="mt-4 inline-flex items-center gap-2 rounded-xl bg-amber-soft px-4 py-2.5 text-xs font-semibold text-ink"><Info size={14} />Showing sample data — the Emploi API is unavailable.</p> : null}
      {error ? <p role="alert" className="mt-4 rounded-xl bg-warn-soft px-4 py-3 text-sm font-semibold text-warn">{error}</p> : null}

      <div className="mt-6 space-y-4">
        {matchData.map((m) => (
          <article key={m.id} className="rise-in rounded-2xl border border-line bg-white p-5 shadow-card sm:p-6">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
              <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl text-lg font-extrabold text-white" style={{ background: m.companyColor }}>{m.companyInitial}</span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2"><h2 className="font-bold">{m.title}</h2>{m.isNew ? <span className="rounded-full bg-brand-soft px-2 py-0.5 text-[10px] font-bold uppercase text-brand">New</span> : null}</div>
                <p className="text-sm text-muted">{m.company} · {m.location} ({m.workMode}) · {m.employment} · {m.salary}</p>
                {m.verified ? <span className="mt-2 inline-flex items-center gap-1 rounded-md bg-good-soft px-2 py-0.5 text-xs font-bold text-good"><BadgeCheck size={12} /> Employer verified</span> : null}
                <p className="mt-3 rounded-xl bg-surface px-4 py-3 text-sm leading-relaxed text-muted"><span className="font-bold text-ink">Why this match: </span>{m.reason}</p>
              </div>
              <div className="flex items-center gap-3 sm:flex-col sm:items-end"><FitRing fit={m.fit} size={56} /><div className="flex gap-2"><button className="rounded-xl border border-line p-2.5 text-muted hover:bg-surface hover:text-brand" aria-label={`Save ${m.title}`}><Bookmark size={16} /></button><ApplyButton match={m} /></div></div>
            </div>
          </article>
        ))}
        {!sampleData && !error && matchData.length === 0 ? <div className="rounded-2xl border border-line bg-white p-10 text-center shadow-card"><h2 className="font-extrabold">Your Career Twin is getting to work</h2><p className="mt-2 text-sm text-muted">No matches yet. We’ll show verified opportunities here after the next matching run.</p></div> : null}
      </div>
    </div>
  );
}
