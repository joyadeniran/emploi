import Link from "next/link";
import { redirect } from "next/navigation";
import { ArrowRight, CheckCircle2, Circle, Info, Loader2 } from "lucide-react";
import { auth } from "@/auth";
import { applications as demoApplications, firstName, greeting, matches as demoMatches, statusMeta, type ApplicationStatus } from "@/lib/data";
import { ApiUnavailableError, apiFetch, DEMO_MODE, toMatchCard, type ApiMatch } from "@/lib/api";
import { FitRing, ProgressRing } from "@/components/ProgressRing";
import { CareerTwinBot } from "@/components/CareerTwinBot";

type Twin = Record<string, unknown>;
type ApiApplication = { id: number; company: string | null; role: string | null; status: string | null; created_at: string };
const statuses: ApplicationStatus[] = ["applied", "interview", "offer", "rejected", "withdrawn"];

function strength(twin: Twin) {
  const fields = ["name", "headline", "skills", "experience", "education", "career_goals"];
  return Math.round((fields.filter((field) => Array.isArray(twin[field]) ? twin[field].length > 0 : Boolean(twin[field])).length / fields.length) * 100);
}

export default async function DashboardPage() {
  const session = await auth();
  const name = firstName(session?.user?.name);
  let twin: Twin = {};
  let cards = DEMO_MODE ? demoMatches : [];
  let recent: ApiApplication[] = [];
  let sampleData = DEMO_MODE;
  let unavailable = false;

  if (!DEMO_MODE) {
    try {
      const twinResult = await apiFetch<{ career_twin: Twin }>("/career-twin");
      twin = twinResult.career_twin ?? {};
      if (!twin.onboarding_complete) redirect("/create-career-twin");
      const [matchResult, applicationResult] = await Promise.all([
        apiFetch<{ matches: ApiMatch[] }>("/matches?limit=5"),
        apiFetch<{ applications: ApiApplication[] }>("/applications"),
      ]);
      cards = matchResult.matches.map(toMatchCard);
      recent = applicationResult.applications.slice(0, 3);
    } catch (caught) {
      if (caught instanceof ApiUnavailableError) {
        // A backend outage should not trap a signed-in user in an error page.
        cards = demoMatches;
        sampleData = true;
        unavailable = true;
      } else {
        redirect("/create-career-twin");
      }
    }
  }

  if (!sampleData && cards.length === 0) {
    return <div className="flex flex-col items-center justify-center py-24 text-center"><h1 className="text-2xl font-extrabold tracking-tight sm:text-3xl">{greeting()}, {name}.</h1><p className="mt-3 text-lg font-semibold text-muted">Your Career Twin is getting to work.</p><div className="mt-8 w-full max-w-sm space-y-3 text-left">{["Scanning new opportunities...", "Building your first recommendations...", "Verifying employers..."].map((line) => <div key={line} className="flex items-center gap-3 rounded-xl border border-line bg-white px-4 py-3 shadow-card"><Loader2 size={16} className="animate-spin text-brand" /><span className="text-sm font-semibold">{line}</span></div>)}</div><p className="mt-8 text-sm text-muted">Come back after the next matching run for your first opportunities.</p></div>;
  }

  const completed = strength(twin);
  const high = cards.filter((match) => match.fit >= 85).length;
  const medium = cards.filter((match) => match.fit >= 60 && match.fit < 85).length;
  const displayApplications = sampleData ? demoApplications.slice(0, 3) : recent;

  return <div className="mx-auto grid max-w-7xl gap-6 xl:grid-cols-[1fr_320px]">
    <main className="min-w-0 space-y-6">
      <div><h1 className="text-2xl font-extrabold tracking-tight sm:text-3xl">{greeting()}, {name} 👋</h1><p className="mt-1 text-sm text-muted">Your Career Twin is working for you. Here’s what it found.</p></div>
      {sampleData ? <p className="inline-flex items-center gap-2 rounded-xl bg-amber-soft px-4 py-2.5 text-xs font-semibold text-ink"><Info size={14} />Showing sample data — the Emploi API is unavailable{unavailable ? "." : " (demo mode)."}</p> : null}
      <section className="overflow-hidden rounded-3xl border border-brand-soft bg-gradient-to-br from-brand-soft/70 via-white to-white shadow-card"><div className="flex gap-6 p-6 sm:p-8"><div className="min-w-0 flex-1"><p className="text-sm font-bold text-brand">Your Career Twin</p><h2 className="mt-1.5 text-xl font-extrabold">I found {cards.length} job matches</h2><ul className="mt-4 space-y-2 text-sm font-semibold"><li><CheckCircle2 className="mr-2 inline text-good" size={16} />{high} high-match opportunities</li><li><CheckCircle2 className="mr-2 inline text-good" size={16} />{medium} medium-match opportunities</li><li><Circle className="mr-2 inline text-muted" size={16} />Review trust evidence before applying</li></ul><Link href="/matches" className="mt-5 inline-flex items-center gap-2 rounded-xl bg-brand px-5 py-2.5 text-sm font-bold text-white">View matches <ArrowRight size={15} /></Link></div><div className="hidden sm:block"><CareerTwinBot /></div></div></section>
      <section><div className="mb-3 flex items-center justify-between"><h2 className="text-lg font-extrabold">Top Job Matches</h2><Link className="text-sm font-bold text-brand" href="/matches">View all <ArrowRight className="inline" size={14} /></Link></div><div className="space-y-3">{cards.map((match) => <article key={match.id} className="flex items-center gap-4 rounded-2xl border border-line bg-white p-4 shadow-card"><span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl font-extrabold text-white" style={{ background: match.companyColor }}>{match.companyInitial}</span><div className="min-w-0 flex-1"><h3 className="truncate font-bold">{match.title}</h3><p className="truncate text-sm text-muted">{match.company} · {match.location}</p><p className="mt-1 text-xs text-muted">{match.reason}</p></div><FitRing fit={match.fit} /></article>)}</div></section>
      <section className="overflow-x-auto rounded-2xl border border-line bg-white shadow-card"><div className="flex justify-between px-5 pt-5"><h2 className="font-extrabold">Recent Applications</h2><Link href="/applications" className="text-sm font-bold text-brand">View all</Link></div><table className="mt-3 w-full min-w-[520px] text-sm"><thead><tr className="border-y border-line bg-surface text-left text-xs font-bold uppercase text-faint"><th className="px-5 py-3">Role</th><th className="px-5 py-3">Company</th><th className="px-5 py-3">Status</th></tr></thead><tbody>{displayApplications.map((application) => { const status = statuses.includes(application.status as ApplicationStatus) ? application.status as ApplicationStatus : "applied"; return <tr key={application.id} className="border-b border-line last:border-0"><td className="px-5 py-4 font-bold">{application.role}</td><td className="px-5 py-4">{application.company}</td><td className="px-5 py-4"><span className={`rounded-full px-3 py-1 text-xs font-bold ${statusMeta[status].className}`}>{statusMeta[status].label}</span></td></tr>; })}</tbody></table></section>
    </main>
    <aside className="space-y-6"><section className="rounded-2xl border border-line bg-white p-6 shadow-card"><div className="flex justify-between"><h2 className="font-extrabold">Your Career Twin</h2><Link href="/career-twin" className="text-xs font-bold text-brand">View profile</Link></div><div className="mt-5 flex items-center gap-5"><ProgressRing value={completed || 0} size={104} label={`${completed}%`} sublabel="Profile strength" /><p className="text-xs text-muted">Keep your profile current so your matches stay accurate.</p></div></section><section className="rounded-2xl border border-line bg-white p-6 shadow-card"><h2 className="font-extrabold">Trust first</h2><p className="mt-2 text-sm text-muted">Never pay a fee or share bank or ID details for a job application.</p><Link href="/trust-check" className="mt-4 inline-block text-sm font-bold text-brand">Run a Trust Check →</Link></section></aside>
  </div>;
}
