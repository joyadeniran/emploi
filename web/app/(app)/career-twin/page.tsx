import { redirect } from "next/navigation";
import { Info, Sparkles } from "lucide-react";
import { ApiUnavailableError, apiFetch, DEMO_MODE } from "@/lib/api";
import { PagePlaceholder } from "@/components/PagePlaceholder";

export const metadata = { title: "Career Twin — Emploi" };

type Twin = Record<string, unknown>;
function stringList(value: unknown): string[] { return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && item.trim().length > 0) : []; }
function details(value: unknown): string[] { if (typeof value === "string" && value.trim().length > 0) return [value]; if (value && typeof value === "object") return Object.values(value).filter((item): item is string => typeof item === "string" && item.trim().length > 0); return []; }

export default async function CareerTwinPage() {
  if (DEMO_MODE) return <PagePlaceholder icon={Sparkles} title="Career Twin" blurb="Your living profile is ready in demo mode." note="Connect the API to see a saved Career Twin." />;
  let twin: Twin;
  try {
    const result = await apiFetch<{ career_twin: Twin }>("/career-twin");
    twin = result.career_twin ?? {};
  } catch (error) {
    if (error instanceof ApiUnavailableError) return <PagePlaceholder icon={Info} title="Career Twin unavailable" blurb="We can’t reach your saved profile right now." note="Please refresh in a moment. Your data has not been changed." />;
    redirect("/create-career-twin");
  }
  if (!Object.keys(twin).length || !twin.onboarding_complete) redirect("/create-career-twin");
  const skills = stringList(twin.skills);
  const experience = Array.isArray(twin.experience) ? twin.experience : [];
  const education = Array.isArray(twin.education) ? twin.education : [];
  const goals = stringList(twin.career_goals ?? twin.goals ?? twin.preferred_roles);
  return <div className="mx-auto max-w-4xl space-y-6"><header><p className="flex items-center gap-2 text-sm font-bold text-brand"><Sparkles size={16} /> Your Career Twin</p><h1 className="mt-1 text-3xl font-extrabold tracking-tight">{typeof twin.name === "string" ? twin.name : "Your profile"}</h1><p className="mt-2 text-muted">{typeof twin.headline === "string" ? twin.headline : "A living profile built from your real experience."}</p></header>{typeof twin.bio === "string" && twin.bio ? <section className="rounded-2xl border border-line bg-white p-6 shadow-card"><h2 className="font-extrabold">About</h2><p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-muted">{twin.bio}</p></section> : null}<section className="rounded-2xl border border-line bg-white p-6 shadow-card"><h2 className="font-extrabold">Skills</h2>{skills.length ? <div className="mt-3 flex flex-wrap gap-2">{skills.map((skill) => <span key={skill} className="rounded-full bg-brand-soft px-3 py-1.5 text-sm font-semibold text-brand">{skill}</span>)}</div> : <p className="mt-3 text-sm text-muted">No skills have been added yet.</p>}</section><section className="grid gap-6 md:grid-cols-2"><ProfileSection title="Experience" rows={experience.flatMap(details)} empty="No experience entries have been added yet." /><ProfileSection title="Education" rows={education.flatMap(details)} empty="No education entries have been added yet." /></section><section className="rounded-2xl border border-line bg-white p-6 shadow-card"><h2 className="font-extrabold">Career goals</h2>{goals.length ? <ul className="mt-3 list-inside list-disc space-y-1 text-sm text-muted">{goals.map((goal) => <li key={goal}>{goal}</li>)}</ul> : <p className="mt-3 text-sm text-muted">No career goals have been added yet.</p>}</section></div>;
}

function ProfileSection({ title, rows, empty }: { title: string; rows: string[]; empty: string }) { return <section className="rounded-2xl border border-line bg-white p-6 shadow-card"><h2 className="font-extrabold">{title}</h2>{rows.length ? <ul className="mt-3 space-y-3 text-sm text-muted">{rows.map((row, index) => <li key={`${row}-${index}`} className="border-l-2 border-brand-soft pl-3">{row}</li>)}</ul> : <p className="mt-3 text-sm text-muted">{empty}</p>}</section>; }
