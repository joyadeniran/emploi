import { BadgeCheck, Bookmark } from "lucide-react";
import { matches } from "@/lib/data";
import { FitRing } from "@/components/ProgressRing";
import { ApplyButton } from "@/components/ApplyButton";

export const metadata = { title: "Job Matches — Emploi" };

export default function MatchesPage() {
  return (
    <div className="mx-auto max-w-5xl">
      <h1 className="rise-in text-2xl font-extrabold tracking-tight sm:text-3xl">Job Matches</h1>
      <p className="mt-1 text-sm text-muted">
        Every opportunity is scored honestly against your real experience — and
        every employer is verified before you see it.
      </p>

      <div className="mt-6 space-y-4">
        {matches.map((m) => (
          <article
            key={m.id}
            className="rise-in rounded-2xl border border-line bg-white p-5 shadow-card sm:p-6"
          >
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
                    <span className="rounded-full bg-brand-soft px-2 py-0.5 text-[10px] font-bold uppercase text-brand">
                      New
                    </span>
                  ) : null}
                </div>
                <p className="text-sm text-muted">
                  {m.company} · {m.location} ({m.workMode}) · {m.employment} · {m.salary}
                </p>
                {m.verified ? (
                  <span className="mt-2 inline-flex items-center gap-1 rounded-md bg-good-soft px-2 py-0.5 text-xs font-bold text-good">
                    <BadgeCheck size={12} /> Employer verified
                  </span>
                ) : null}
                <p className="mt-3 rounded-xl bg-surface px-4 py-3 text-sm leading-relaxed text-muted">
                  <span className="font-bold text-ink">Why this match: </span>
                  {m.reason}
                </p>
              </div>
              <div className="flex items-center gap-3 sm:flex-col sm:items-end">
                <FitRing fit={m.fit} size={56} />
                <div className="flex gap-2">
                  <button
                    className="rounded-xl border border-line p-2.5 text-muted hover:bg-surface hover:text-brand"
                    aria-label={`Save ${m.title}`}
                  >
                    <Bookmark size={16} />
                  </button>
                  <ApplyButton match={m} />
                </div>
              </div>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
