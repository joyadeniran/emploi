import Link from "next/link";
import { redirect } from "next/navigation";
import {
  ArrowRight,
  Bookmark,
  CheckCircle2,
  Circle,
  ShieldCheck,
  BadgeCheck,
  Send,
  CalendarCheck,
  Trophy,
  Percent,
  MoreVertical,
  Loader2,
} from "lucide-react";
import { auth } from "@/auth";
import {
  applications,
  firstName,
  greeting,
  matches,
  overview,
  profile,
  statusMeta,
  trustCheck,
  twinSummary,
} from "@/lib/data";
import { FitRing, ProgressRing } from "@/components/ProgressRing";
import { CareerTwinBot } from "@/components/CareerTwinBot";
import { apiFetch, ApiUnavailableError, DEMO_MODE } from "@/lib/api";

function matchTone(fit: number) {
  if (fit >= 85) return { label: "Great Match", cls: "text-good" };
  if (fit >= 60) return { label: "Good Match", cls: "text-amber" };
  return { label: "Fair Match", cls: "text-warn" };
}

export default async function DashboardPage() {
  const session = await auth();
  const name = firstName(session?.user?.name);

  // Onboarding gate: fetch career twin and redirect if not complete
  if (!DEMO_MODE) {
    let twinComplete = false;
    try {
      const { career_twin } = await apiFetch<{ career_twin: Record<string, unknown> }>("/career-twin");
      twinComplete = !!(career_twin && Object.keys(career_twin).length > 0 && career_twin.onboarding_complete);
    } catch (e) {
      // API unavailable → don't block; any other error → treat as not complete
      if (e instanceof ApiUnavailableError) twinComplete = true;
    }
    // redirect() must be called outside try/catch — it throws a special Next.js error internally
    if (!twinComplete) redirect("/create-career-twin");
  }

  // If twin is complete but has no matches yet, show the "getting to work" state.
  // For now we always show the full dashboard (demo data); swap this flag when
  // the backend can return real match counts.
  const hasMatches = true;

  // Empty state — Career Twin is set up but hasn't found matches yet
  if (!hasMatches) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <h1 className="text-2xl font-extrabold tracking-tight sm:text-3xl">
          {greeting()}, {name}.
        </h1>
        <p className="mt-3 text-lg font-semibold text-muted">Your Career Twin is getting to work.</p>
        <div className="mt-8 w-full max-w-sm space-y-3 text-left">
          {[
            "Scanning new opportunities...",
            "Building your first recommendations...",
            "Verifying employers...",
          ].map((line) => (
            <div key={line} className="flex items-center gap-3 rounded-xl border border-line bg-white px-4 py-3 shadow-card">
              <Loader2 size={16} className="shrink-0 animate-spin text-brand" />
              <span className="text-sm font-semibold">{line}</span>
            </div>
          ))}
        </div>
        <p className="mt-8 text-sm text-muted">
          We&apos;ll notify you when your first matches are ready.
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto grid max-w-7xl gap-6 xl:grid-cols-[1fr_360px]">
      {/* ============ main column ============ */}
      <div className="min-w-0 space-y-6">
        <div className="rise-in">
          <h1 className="text-2xl font-extrabold tracking-tight sm:text-3xl">
            {greeting()}, {name} 👋
          </h1>
          <p className="mt-1 text-sm text-muted">
            Your Career Twin is working for you. Here&apos;s what&apos;s
            happening today.
          </p>
        </div>

        {/* Career Twin hero */}
        <section className="rise-in overflow-hidden rounded-3xl border border-brand-soft bg-gradient-to-br from-brand-soft/70 via-white to-white shadow-card">
          <div className="flex flex-col gap-6 p-6 sm:flex-row sm:items-center sm:p-8">
            <div className="min-w-0 flex-1">
              <p className="text-sm font-bold text-brand">Your Career Twin</p>
              <h2 className="mt-1.5 text-xl font-extrabold tracking-tight sm:text-2xl">
                I found {twinSummary.newMatches} new job matches
              </h2>
              <p className="mt-2 max-w-md text-sm leading-relaxed text-muted">
                I&apos;ve analyzed thousands of opportunities and found these
                matches that fit you best.
              </p>
              <ul className="mt-4 space-y-2">
                {[
                  `${twinSummary.highMatches} high match opportunities`,
                  `${twinSummary.mediumMatches} medium match opportunity`,
                  twinSummary.allVerified ? "All companies verified" : "Verification in progress",
                ].map((line) => (
                  <li key={line} className="flex items-center gap-2 text-sm font-semibold">
                    <CheckCircle2 size={16} className="shrink-0 text-good" />
                    {line}
                  </li>
                ))}
              </ul>
              <Link
                href="/matches"
                className="mt-5 inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-brand-violet to-brand-indigo px-5 py-2.5 text-sm font-bold text-white shadow-pop transition-transform hover:-translate-y-0.5"
              >
                View Matches <ArrowRight size={15} />
              </Link>
            </div>
            <div className="hidden shrink-0 sm:block">
              <CareerTwinBot />
            </div>
          </div>
        </section>

        {/* Top job matches */}
        <section className="rise-in">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h3 className="flex items-center gap-2.5 text-lg font-extrabold tracking-tight">
              Top Job Matches
              <span className="rounded-full bg-brand-soft px-2.5 py-0.5 text-xs font-bold text-brand">
                {twinSummary.newMatches} new
              </span>
            </h3>
            <Link
              href="/matches"
              className="inline-flex items-center gap-1.5 text-sm font-bold text-brand hover:underline"
            >
              View all matches <ArrowRight size={14} />
            </Link>
          </div>

          <div className="space-y-3">
            {matches.map((m) => {
              const tone = matchTone(m.fit);
              return (
                <article
                  key={m.id}
                  className="flex flex-col gap-4 rounded-2xl border border-line bg-white p-4 shadow-card transition-shadow hover:shadow-pop/20 sm:flex-row sm:items-center sm:p-5"
                >
                  <div className="flex min-w-0 flex-1 items-center gap-4">
                    <span
                      className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl text-lg font-extrabold text-white"
                      style={{ background: m.companyColor }}
                    >
                      {m.companyInitial}
                    </span>
                    <div className="min-w-0">
                      <h4 className="truncate font-bold">{m.title}</h4>
                      <p className="truncate text-sm text-muted">
                        {m.company} · {m.location} ({m.workMode})
                      </p>
                      <div className="mt-1.5 flex flex-wrap gap-1.5">
                        <span className="rounded-md bg-surface px-2 py-0.5 text-xs font-semibold text-muted">
                          {m.employment}
                        </span>
                        <span className="rounded-md bg-surface px-2 py-0.5 text-xs font-semibold text-muted">
                          {m.salary}
                        </span>
                        {m.verified ? (
                          <span className="inline-flex items-center gap-1 rounded-md bg-good-soft px-2 py-0.5 text-xs font-bold text-good">
                            <BadgeCheck size={12} /> Verified
                          </span>
                        ) : null}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-4 sm:border-l sm:border-line sm:pl-5">
                    <div className="flex items-center gap-2.5">
                      <FitRing fit={m.fit} />
                      <div>
                        <p className={`text-sm font-extrabold ${tone.cls}`}>{tone.label}</p>
                        <details className="group">
                          <summary className="cursor-pointer list-none text-xs font-semibold text-muted hover:text-brand">
                            Why this match? ▾
                          </summary>
                        </details>
                      </div>
                    </div>
                    <div className="ml-auto flex items-center gap-2">
                      <button
                        className="rounded-xl border border-line p-2.5 text-muted hover:bg-surface hover:text-brand"
                        aria-label={`Save ${m.title}`}
                      >
                        <Bookmark size={16} />
                      </button>
                      <Link
                        href="/matches"
                        className="rounded-xl bg-brand px-5 py-2.5 text-sm font-bold text-white transition-transform hover:-translate-y-0.5"
                      >
                        View
                      </Link>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>

          <Link
            href="/matches"
            className="mt-3 block rounded-xl bg-brand-soft/60 py-3 text-center text-sm font-bold text-brand transition-colors hover:bg-brand-soft"
          >
            View all job matches
          </Link>
        </section>

        {/* Recent applications */}
        <section className="rise-in rounded-2xl border border-line bg-white shadow-card">
          <div className="flex items-center justify-between gap-3 px-5 pt-5">
            <h3 className="text-lg font-extrabold tracking-tight">Recent Applications</h3>
            <Link
              href="/applications"
              className="inline-flex items-center gap-1.5 text-sm font-bold text-brand hover:underline"
            >
              View all <ArrowRight size={14} />
            </Link>
          </div>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead>
                <tr className="border-y border-line bg-surface/60 text-left text-xs font-bold uppercase tracking-wide text-faint">
                  <th className="px-5 py-3">Role</th>
                  <th className="px-5 py-3">Company</th>
                  <th className="px-5 py-3">Applied On</th>
                  <th className="px-5 py-3">Status</th>
                  <th className="px-5 py-3">Next Step</th>
                  <th className="px-2 py-3" aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {applications.slice(0, 3).map((a) => (
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
                      <span
                        className={`rounded-full px-3 py-1 text-xs font-bold ${statusMeta[a.status].className}`}
                      >
                        {statusMeta[a.status].label}
                      </span>
                    </td>
                    <td className="px-5 py-4">
                      {a.nextStep ? (
                        <>
                          <span className="block font-semibold">{a.nextStep}</span>
                          <span className="text-xs text-muted">{a.nextStepDate}</span>
                        </>
                      ) : (
                        <span className="text-faint">—</span>
                      )}
                    </td>
                    <td className="px-2 py-4">
                      <button className="rounded-lg p-1.5 text-faint hover:bg-surface" aria-label="More actions">
                        <MoreVertical size={16} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      {/* ============ right rail ============ */}
      <div className="space-y-6">
        {/* Career Twin profile strength */}
        <section className="rise-in rounded-2xl border border-line bg-white p-6 shadow-card">
          <div className="flex items-center justify-between gap-3">
            <h3 className="font-extrabold tracking-tight">Your Career Twin</h3>
            <Link
              href="/career-twin"
              className="inline-flex items-center gap-1 text-xs font-bold text-brand hover:underline"
            >
              View profile <ArrowRight size={12} />
            </Link>
          </div>
          <div className="mt-5 flex items-center gap-6">
            <ProgressRing
              value={profile.strength}
              size={116}
              label={`${profile.strength}%`}
              sublabel="Profile strength"
            />
            <ul className="space-y-2">
              {profile.checklist.map((item) => (
                <li key={item.label} className="flex items-center gap-2 text-xs font-semibold">
                  {item.done ? (
                    <CheckCircle2 size={15} className="shrink-0 text-good" />
                  ) : (
                    <Circle size={15} className="shrink-0 text-line" />
                  )}
                  <span className={item.done ? "" : "text-muted"}>{item.label}</span>
                </li>
              ))}
            </ul>
          </div>
          <p className="mt-5 rounded-xl bg-good-soft px-4 py-3 text-xs font-semibold leading-relaxed text-ink">
            Great job! A complete profile gets you 3x more interview chances.
          </p>
        </section>

        {/* Trust check */}
        <section className="rise-in rounded-2xl border border-line bg-white p-6 shadow-card">
          <div className="flex items-center justify-between gap-3">
            <h3 className="font-extrabold tracking-tight">Trust Check</h3>
            <Link
              href="/trust-check"
              className="inline-flex items-center gap-1 text-xs font-bold text-brand hover:underline"
            >
              View all <ArrowRight size={12} />
            </Link>
          </div>
          <div className="mt-4 flex items-center gap-3">
            <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-good-soft">
              <ShieldCheck size={22} className="text-good" />
            </span>
            <div>
              <p className="text-xs text-muted">Company you&apos;re applying to</p>
              <p className="flex items-center gap-1.5 font-extrabold">
                {trustCheck.company}
                <BadgeCheck size={15} className="text-brand" />
              </p>
            </div>
          </div>
          <p className="mt-4 text-2xl font-extrabold">
            {trustCheck.score}
            <span className="text-base font-bold text-faint">/100</span>
            <span className="ml-2 text-base font-extrabold text-good">
              {trustCheck.verdict}
            </span>
          </p>
          <p className="mt-3 text-xs font-bold uppercase tracking-wide text-faint">Reasons:</p>
          <ul className="mt-2 space-y-1.5">
            {trustCheck.reasons.map((r) => (
              <li key={r} className="flex items-center gap-2 text-xs font-semibold">
                <CheckCircle2 size={14} className="shrink-0 text-good" />
                {r}
              </li>
            ))}
          </ul>
          <Link
            href="/trust-check"
            className="mt-4 inline-flex items-center gap-1.5 rounded-xl bg-surface px-4 py-2.5 text-xs font-bold text-brand hover:bg-brand-soft"
          >
            View full trust report <ArrowRight size={13} />
          </Link>
        </section>

        {/* Application overview */}
        <section className="rise-in rounded-2xl border border-line bg-white p-6 shadow-card">
          <div className="flex items-center justify-between gap-3">
            <h3 className="font-extrabold tracking-tight">Your Application Overview</h3>
            <span className="text-xs font-semibold text-muted">This month</span>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3">
            {[
              { value: overview.applied, label: "Applied", icon: Send },
              { value: overview.interviews, label: "Interviews", icon: CalendarCheck },
              { value: overview.offers, label: "Offers", icon: Trophy },
              { value: overview.interviewRate, label: "Interview rate", icon: Percent },
            ].map(({ value, label, icon: Icon }) => (
              <div key={label} className="rounded-xl border border-line bg-surface/50 p-4">
                <div className="flex items-start justify-between">
                  <p className="text-2xl font-extrabold">{value}</p>
                  <Icon size={16} className="text-faint" />
                </div>
                <p className="mt-1 text-xs font-semibold text-muted">{label}</p>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
