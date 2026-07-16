import Link from "next/link";
import { BadgeCheck, Bookmark, Info } from "lucide-react";
import { ApiUnavailableError, apiFetch, DEMO_MODE, toJobCard, type ApiJob } from "@/lib/api";
import { ApplyButton } from "@/components/ApplyButton";
import { SaveJobButton } from "@/components/SaveJobButton";
import { PagePlaceholder } from "@/components/PagePlaceholder";

export const metadata = { title: "Saved Jobs — Emploi" };

type SavedJob = ApiJob & { saved_at?: string };

export default async function SavedPage() {
  if (DEMO_MODE) {
    return <PagePlaceholder icon={Bookmark} title="Saved Jobs" blurb="Roles you bookmarked to come back to." note="Connect the API to see saved jobs." />;
  }

  let saved: SavedJob[] = [];
  let offline = false;
  try {
    const data = await apiFetch<{ saved: SavedJob[] }>("/saved-jobs");
    saved = data.saved;
  } catch (e) {
    if (e instanceof ApiUnavailableError) offline = true;
    else throw e;
  }

  if (offline) {
    return <PagePlaceholder icon={Info} title="Saved jobs unavailable" blurb="We can’t reach your bookmarks right now." note="Please refresh in a moment. Nothing has been lost." />;
  }

  return (
    <div className="mx-auto max-w-5xl">
      <h1 className="rise-in text-2xl font-extrabold tracking-tight sm:text-3xl">Saved Jobs</h1>
      <p className="mt-1 text-sm text-muted">
        Roles you bookmarked to come back to. Unsave one and it leaves this list immediately.
      </p>

      <div className="mt-6 space-y-3">
        {saved.length === 0 ? (
          <div className="rounded-2xl border border-line bg-card p-10 text-center shadow-card">
            <Bookmark className="mx-auto text-brand" size={28} />
            <p className="mt-3 font-bold">Nothing saved yet</p>
            <p className="mt-1 text-sm text-muted">
              Tap the bookmark on any job in{" "}
              <Link href="/matches" className="font-bold text-brand hover:underline">Job Matches</Link> or{" "}
              <Link href="/jobs" className="font-bold text-brand hover:underline">Browse Jobs</Link> and it lands here.
            </p>
          </div>
        ) : (
          saved.map((row) => {
            const card = toJobCard(row);
            return (
              <article key={card.id}
                className="flex flex-col gap-4 rounded-2xl border border-line bg-card p-4 shadow-card sm:flex-row sm:items-center sm:p-5">
                <div className="flex min-w-0 flex-1 items-center gap-4">
                  <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl text-lg font-extrabold text-white"
                    style={{ background: card.companyColor }}>
                    {card.companyInitial}
                  </span>
                  <div className="min-w-0">
                    <h2 className="truncate font-bold">{card.title}</h2>
                    <p className="truncate text-sm text-muted">{card.company} · {card.location}</p>
                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                      {card.workMode === "Remote" ? (
                        <span className="inline-flex items-center gap-1 rounded-md bg-good-soft px-2 py-0.5 text-xs font-bold text-good">
                          <BadgeCheck size={12} /> Remote
                        </span>
                      ) : null}
                      <span className="rounded-md bg-surface px-2 py-0.5 text-xs font-semibold text-muted">{card.salary}</span>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2 sm:border-l sm:border-line sm:pl-5">
                  <SaveJobButton jobId={card.jobId} title={card.title} initialSaved />
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
