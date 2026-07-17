import Link from "next/link";
import { redirect } from "next/navigation";
import { ArrowRight, CheckCircle2, Circle, Info, ShieldCheck, Sparkles } from "lucide-react";
import { auth } from "@/auth";
import { applications as demoApplications, firstName, greeting, matches as demoMatches, statusMeta, type ApplicationStatus } from "@/lib/data";
import { apiFetch, DEMO_MODE, toMatchCard, type ApiMatch } from "@/lib/api";
import { FitRing, ProgressRing } from "@/components/ProgressRing";
import { CareerTwinBot } from "@/components/CareerTwinBot";
import { RecruiterVisibilityBanner } from "@/components/RecruiterVisibilityBanner";

type Twin = Record<string, unknown>;
type ApiApplication = { id: number; company: string | null; role: string | null; status: string | null; created_at: string };
const statuses: ApplicationStatus[] = ["applied", "interview", "offer", "rejected", "withdrawn"];

const STRENGTH_FIELDS: { key: string; label: string }[] = [
  { key: "name", label: "Name" },
  { key: "headline", label: "Headline" },
  { key: "skills", label: "Skills" },
  { key: "experience", label: "Experience" },
  { key: "education", label: "Education" },
  { key: "career_goals", label: "Goals" },
];

function fieldDone(twin: Twin, key: string) {
  const value = twin[key];
  return Array.isArray(value) ? value.length > 0 : Boolean(value);
}

function strength(twin: Twin) {
  return Math.round((STRENGTH_FIELDS.filter((f) => fieldDone(twin, f.key)).length / STRENGTH_FIELDS.length) * 100);
}

export default async function DashboardPage() {
  const session = await auth();
  const name = firstName(session?.user?.name);
  let twin: Twin = {};
  let cards = DEMO_MODE ? demoMatches : [];
  let recent: ApiApplication[] = [];
  let sampleData = DEMO_MODE;
  let unavailable = false;
  let pendingInvites = 0;

  if (!DEMO_MODE) {
    // 1) Gate on the Career Twin. ONLY a genuinely missing or not-yet-activated
    //    twin sends the user to onboarding. A transient backend error must not —
    //    otherwise a returning user gets thrown back into the wizard on every
    //    hiccup (the "recreate my twin each login" bug). redirect() is called
    //    AFTER the try so its internal throw is never swallowed by the catch.
    let needsOnboarding = false;
    try {
      const twinResult = await apiFetch<{ career_twin: Twin }>("/career-twin");
      twin = twinResult.career_twin ?? {};
      needsOnboarding = !twin.onboarding_complete;
    } catch {
      // Backend unreachable OR errored on the twin fetch: fall back to the
      // sample dashboard rather than nuking the session into onboarding.
      cards = demoMatches;
      sampleData = true;
      unavailable = true;
    }
    if (needsOnboarding) redirect("/create-career-twin");

    // 2) Secondary data. These NEVER gate onboarding — on error the dashboard
    //    simply shows empty/sample content.
    if (!sampleData) {
      // Backfill: twins completed before email-capture shipped have no stored
      // email, which silently starves the notification digest. One-time repair
      // per user, fire-and-forget.
      if (!twin.email && session?.user?.email) {
        apiFetch("/career-twin", {
          method: "PATCH",
          body: JSON.stringify({ data: { email: session.user.email } }),
        }).catch(() => {});
      }
      const [matchResult, applicationResult, inviteCount] = await Promise.all([
        apiFetch<{ matches: ApiMatch[] }>("/matches?limit=5").catch(() => ({ matches: [] as ApiMatch[] })),
        apiFetch<{ applications: ApiApplication[] }>("/applications").catch(() => ({ applications: [] as ApiApplication[] })),
        apiFetch<{ pending: number }>("/invites/count").catch(() => ({ pending: 0 })),
      ]);
      cards = matchResult.matches.map(toMatchCard);
      recent = applicationResult.applications.slice(0, 3);
      pendingInvites = inviteCount.pending ?? 0;
    }
  }

  if (!sampleData && cards.length === 0) {
    // Honest empty state: nothing is literally running while the user looks
    // at this page — jobs refresh hourly and matching runs nightly. Say so,
    // and give them things they CAN do right now instead of a fake spinner.
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <h1 className="text-2xl font-extrabold tracking-tight sm:text-3xl">{greeting()}, {name}.</h1>
        <p className="mt-3 text-lg font-semibold text-muted">Your Career Twin is set up and on duty.</p>
        {pendingInvites > 0 ? (
          <Link href="/invites" className="mt-6 inline-flex items-center gap-2 rounded-2xl border border-brand/25 bg-brand-soft px-5 py-3 text-sm font-extrabold text-brand shadow-card">
            You have {pendingInvites} pending interview invite{pendingInvites === 1 ? "" : "s"} 🎉 <ArrowRight size={15} />
          </Link>
        ) : null}
        <div className="mt-6 w-full max-w-md text-left"><RecruiterVisibilityBanner /></div>
        <div className="mt-8 w-full max-w-md space-y-3 text-left">
          {[
            "New jobs are pulled from verified boards every hour",
            "Your Twin scores fresh jobs against your profile every night",
            "You'll get an email digest when your first matches land",
          ].map((line) => (
            <div key={line} className="flex items-center gap-3 rounded-xl border border-line bg-card px-4 py-3 shadow-card">
              <CheckCircle2 size={16} className="shrink-0 text-good" />
              <span className="text-sm font-semibold">{line}</span>
            </div>
          ))}
        </div>
        <p className="mt-8 text-sm text-muted">Don&apos;t want to wait for the nightly run?</p>
        <div className="mt-3 flex flex-wrap items-center justify-center gap-3">
          <Link href="/jobs" className="rounded-xl bg-brand px-5 py-2.5 text-sm font-bold text-white transition-transform hover:-translate-y-0.5">
            Browse live jobs now
          </Link>
          <Link href="/import-job" className="rounded-xl border border-line bg-card px-5 py-2.5 text-sm font-bold text-brand shadow-card hover:bg-brand-soft">
            Import a job you found
          </Link>
        </div>
      </div>
    );
  }

  const completed = strength(twin);
  const profileChecklist = STRENGTH_FIELDS.map((f) => ({ label: f.label, done: fieldDone(twin, f.key) }));
  const high = cards.filter((match) => match.fit >= 85).length;
  const medium = cards.filter((match) => match.fit >= 60 && match.fit < 85).length;
  const displayApplications = sampleData ? demoApplications.slice(0, 3) : recent;

  return <div className="mx-auto grid max-w-7xl gap-6 xl:grid-cols-[1fr_320px]">
    <main className="min-w-0 space-y-6">
      <div><h1 className="text-2xl font-extrabold tracking-tight sm:text-3xl">{greeting()}, {name} 👋</h1><p className="mt-1 text-sm text-muted">Your Career Twin is working for you. Here’s what it found.</p></div>
      {pendingInvites > 0 ? <Link href="/invites" className="flex items-center justify-between rounded-2xl border border-brand/25 bg-brand-soft px-5 py-4 shadow-card transition-shadow hover:shadow-pop"><span className="text-sm font-extrabold text-brand">You have {pendingInvites} pending interview invite{pendingInvites === 1 ? "" : "s"} 🎉</span><ArrowRight size={16} className="text-brand" /></Link> : null}
      <RecruiterVisibilityBanner />
      {sampleData ? <p className="inline-flex items-center gap-2 rounded-xl bg-amber-soft px-4 py-2.5 text-xs font-semibold text-ink"><Info size={14} />Showing sample data — the Emploi API is unavailable{unavailable ? "." : " (demo mode)."}</p> : null}
      <section className="overflow-hidden rounded-3xl border border-brand-soft bg-gradient-to-br from-brand-soft/70 via-white to-white shadow-card"><div className="flex gap-6 p-6 sm:p-8"><div className="min-w-0 flex-1"><p className="text-sm font-bold text-brand">Your Career Twin</p><h2 className="mt-1.5 text-xl font-extrabold">I found {cards.length} job matches</h2><ul className="mt-4 space-y-2 text-sm font-semibold"><li><CheckCircle2 className="mr-2 inline text-good" size={16} />{high} high-match opportunities</li><li><CheckCircle2 className="mr-2 inline text-good" size={16} />{medium} medium-match opportunities</li><li><Circle className="mr-2 inline text-muted" size={16} />Review trust evidence before applying</li></ul><Link href="/matches" className="mt-5 inline-flex items-center gap-2 rounded-xl bg-brand px-5 py-2.5 text-sm font-bold text-white">View matches <ArrowRight size={15} /></Link></div><div className="hidden sm:block"><CareerTwinBot /></div></div></section>
      <section><div className="mb-3 flex items-center justify-between"><h2 className="text-lg font-extrabold">Top Job Matches</h2><Link className="text-sm font-bold text-brand" href="/matches">View all <ArrowRight className="inline" size={14} /></Link></div><div className="space-y-3">{cards.map((match) => <article key={match.id} className="flex items-center gap-4 rounded-2xl border border-line bg-card p-4 shadow-card"><span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl font-extrabold text-white" style={{ background: match.companyColor }}>{match.companyInitial}</span><div className="min-w-0 flex-1"><h3 className="truncate font-bold">{match.title}</h3><p className="truncate text-sm text-muted">{match.company} · {match.location}</p><p className="mt-1 text-xs text-muted">{match.reason}</p></div><FitRing fit={match.fit} /></article>)}</div></section>
      <section className="overflow-x-auto rounded-2xl border border-line bg-card shadow-card"><div className="flex justify-between px-5 pt-5"><h2 className="font-extrabold">Recent Applications</h2><Link href="/applications" className="text-sm font-bold text-brand">View all</Link></div><table className="mt-3 w-full min-w-[520px] text-sm"><thead><tr className="border-y border-line bg-surface text-left text-xs font-bold uppercase text-faint"><th className="px-5 py-3">Role</th><th className="px-5 py-3">Company</th><th className="px-5 py-3">Status</th></tr></thead><tbody>{displayApplications.map((application) => { const status = statuses.includes(application.status as ApplicationStatus) ? application.status as ApplicationStatus : "applied"; return <tr key={application.id} className="border-b border-line last:border-0"><td className="px-5 py-4 font-bold">{application.role}</td><td className="px-5 py-4">{application.company}</td><td className="px-5 py-4"><span className={`rounded-full px-3 py-1 text-xs font-bold ${statusMeta[status].className}`}>{statusMeta[status].label}</span></td></tr>; })}</tbody></table></section>
    </main>
    <aside className="space-y-6">
      {/* Profile strength — glass card over an ambient brand gradient */}
      <section className="relative overflow-hidden rounded-3xl border border-glass bg-card-glass-light p-6 shadow-card backdrop-blur-xl">
        <div aria-hidden className="pointer-events-none absolute -right-10 -top-12 h-40 w-40 rounded-full bg-gradient-to-br from-brand-violet/35 to-brand-indigo/25 blur-2xl" />
        <div aria-hidden className="pointer-events-none absolute -bottom-14 -left-10 h-36 w-36 rounded-full bg-brand-soft/80 blur-2xl" />
        <div className="relative">
          <div className="flex items-center justify-between">
            <h2 className="flex items-center gap-2 font-extrabold"><Sparkles size={15} className="text-brand" /> Your Career Twin</h2>
            <Link href="/career-twin" className="text-xs font-bold text-brand hover:underline">View profile</Link>
          </div>
          <div className="mt-5 flex items-center gap-5">
            <ProgressRing value={completed || 0} size={108} label={`${completed}%`} sublabel="Complete" />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-extrabold">
                {completed >= 100 ? "Profile fully tuned" : completed >= 60 ? "Almost there" : "Let's build it out"}
              </p>
              <p className="mt-1 text-xs leading-relaxed text-muted">
                {completed >= 100
                  ? "Your Twin has everything it needs to match and write for you."
                  : "The more your Twin knows, the sharper your matches and drafts get."}
              </p>
            </div>
          </div>
          <div className="mt-4 flex flex-wrap gap-1.5">
            {profileChecklist.map((item) => (
              <span key={item.label}
                className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-bold ${item.done
                  ? "bg-good-soft text-good"
                  : "border border-dashed border-line bg-card-glass text-muted"}`}>
                {item.done ? <CheckCircle2 size={11} /> : <Circle size={11} />}
                {item.label}
              </span>
            ))}
          </div>
          {completed < 100 ? (
            <Link href="/career-twin"
              className="mt-4 inline-flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-brand-violet to-brand-indigo px-4 py-2.5 text-xs font-bold text-white shadow-pop transition-transform hover:-translate-y-0.5">
              Complete your profile <ArrowRight size={13} />
            </Link>
          ) : null}
        </div>
      </section>

      {/* Trust — glass card, the product promise stays loud */}
      <section className="relative overflow-hidden rounded-3xl border border-glass bg-card-glass-light p-6 shadow-card backdrop-blur-xl">
        <div aria-hidden className="pointer-events-none absolute -right-12 -bottom-12 h-36 w-36 rounded-full bg-good-soft/90 blur-2xl" />
        <div className="relative">
          <div className="flex items-center gap-2.5">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-good-soft"><ShieldCheck size={19} className="text-good" /></span>
            <h2 className="font-extrabold">Trust first</h2>
          </div>
          <p className="mt-3 text-sm leading-relaxed text-muted">
            Never pay a fee or share bank or ID details for a job application. Every employer here can be checked.
          </p>
          <Link href="/trust-check" className="mt-4 inline-flex items-center gap-1.5 rounded-xl bg-card-glass px-4 py-2.5 text-xs font-bold text-brand shadow-card transition hover:bg-brand-soft">
            Run a Trust Check <ArrowRight size={13} />
          </Link>
        </div>
      </section>
    </aside>
  </div>;
}
