import Link from "next/link";
import { BadgeCheck, ShieldCheck, Sparkles, Zap } from "lucide-react";
import { Logo } from "@/components/Logo";

export const metadata = {
  title: "Emploi for Employers — post one role free, first hire on us",
  description:
    "Post a role, get an AI-curated shortlist of verified, opted-in candidates, and invite them to interview. Your first hiring experience is completely free.",
};

const EXAMPLE_CANDIDATES = [
  { headline: "Senior Backend Engineer", location: "Lagos · Remote", fit: 92,
    skills: ["Python", "PostgreSQL", "AWS"], blurb: "8 yrs building fintech APIs at scale" },
  { headline: "Product Designer", location: "Nairobi · Remote", fit: 88,
    skills: ["Figma", "Design systems", "UX research"], blurb: "Led design for two B2B SaaS products" },
  { headline: "Data Analyst", location: "Accra · Hybrid", fit: 85,
    skills: ["SQL", "dbt", "Looker"], blurb: "Turned messy ops data into board dashboards" },
];

export default function EmployersLandingPage() {
  return (
    <div className="min-h-dvh bg-surface">
      <header className="mx-auto flex max-w-5xl items-center justify-between px-6 py-6">
        <Link href="/" aria-label="Emploi home"><Logo markSize={22} /></Link>
        <Link href="/login" className="text-sm font-bold text-muted hover:text-brand">
          Job seeker? Sign in
        </Link>
      </header>

      <main className="mx-auto max-w-5xl px-6 pb-20">
        <section className="pt-10 text-center sm:pt-16">
          <p className="inline-flex items-center gap-2 rounded-full bg-brand-soft px-4 py-1.5 text-xs font-bold text-brand">
            <Sparkles size={13} /> Emploi Employer Portal
          </p>
          <h1 className="mx-auto mt-5 max-w-2xl text-3xl font-extrabold tracking-tight sm:text-5xl">
            Post one role free. Your first hire is on us.
          </h1>
          <p className="mx-auto mt-4 max-w-xl text-base leading-relaxed text-muted">
            No job-board noise, no CV pile. Emploi curates a ranked shortlist of
            verified, opted-in candidates for your role — you just invite the
            ones you want to interview.
          </p>
          <Link
            href="/login?callbackUrl=/employer/onboarding"
            className="mt-8 inline-block rounded-full bg-brand px-8 py-3.5 text-sm font-bold text-white shadow-pop transition-transform hover:-translate-y-0.5"
          >
            Post your first role — free
          </Link>
          <p className="mt-3 text-xs text-faint">
            Free role includes unlimited shortlisted candidates and up to 10 interview invites.
          </p>
        </section>

        <section className="mt-16 grid gap-4 sm:grid-cols-3">
          {[
            { icon: Zap, title: "Paste a link, get a shortlist",
              body: "Drop your Greenhouse, Lever, Ashby, Workable, or SmartRecruiters posting — or paste the JD. Emploi extracts the role and ranks candidates for it." },
            { icon: ShieldCheck, title: "Verified both ways",
              body: "Every employer is trust-checked before candidates see an invite, and every candidate explicitly opted in to being discovered." },
            { icon: BadgeCheck, title: "Interview-ready, not CV spam",
              body: "You see structured Career Twins — skills, experience, fit score, and why. Invite the ones worth an hour of your time." },
          ].map(({ icon: Icon, title, body }) => (
            <div key={title} className="rounded-2xl border border-line bg-card p-6 shadow-card">
              <Icon className="text-brand" size={22} />
              <h2 className="mt-3 font-extrabold">{title}</h2>
              <p className="mt-2 text-sm leading-relaxed text-muted">{body}</p>
            </div>
          ))}
        </section>

        <section className="mt-16">
          <h2 className="text-center text-xl font-extrabold">What your shortlist looks like</h2>
          <p className="mt-1 text-center text-xs text-faint">Illustrative examples — real candidates appear once you post a role.</p>
          <div className="mt-6 grid gap-4 sm:grid-cols-3">
            {EXAMPLE_CANDIDATES.map((candidate) => (
              <div key={candidate.headline} className="rounded-2xl border border-line bg-card p-5 shadow-card">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="font-bold">{candidate.headline}</p>
                    <p className="text-xs text-muted">{candidate.location}</p>
                  </div>
                  <span className="rounded-full bg-brand-soft px-2.5 py-1 text-xs font-extrabold text-brand">
                    {candidate.fit}/100
                  </span>
                </div>
                <p className="mt-2 text-xs text-muted">{candidate.blurb}</p>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {candidate.skills.map((skill) => (
                    <span key={skill} className="rounded-full bg-surface px-2.5 py-0.5 text-[11px] font-semibold text-muted">
                      {skill}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="mt-16 rounded-3xl border border-line bg-card p-8 text-center shadow-card">
          <h2 className="text-xl font-extrabold">Simple pricing</h2>
          <p className="mx-auto mt-2 max-w-lg text-sm leading-relaxed text-muted">
            Your first role is completely free, from posting to interviewing.
            From your second role, unlock the candidates you want to invite at
            ₦1,000 per candidate — packs start at 5 unlocks (₦5,000). No
            subscriptions, no per-seat fees.
          </p>
          <Link
            href="/login?callbackUrl=/employer/onboarding"
            className="mt-6 inline-block rounded-full bg-brand px-8 py-3.5 text-sm font-bold text-white shadow-pop transition-transform hover:-translate-y-0.5"
          >
            Post your first role
          </Link>
        </section>
      </main>

      <footer className="border-t border-line px-6 py-6 text-center text-xs text-faint">
        <a href="/privacy" className="hover:text-brand">Privacy</a>
        <span className="mx-2">·</span>
        <a href="/terms" className="hover:text-brand">Terms</a>
        <span className="mx-2">·</span>
        © 2026 Crost Limited (RC 9526947)
      </footer>
    </div>
  );
}
