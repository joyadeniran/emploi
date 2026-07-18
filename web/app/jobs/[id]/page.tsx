import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { BadgeCheck, MapPin, ShieldAlert, ShieldCheck, Sparkles, Wallet } from "lucide-react";
import { auth } from "@/auth";
import { Logo } from "@/components/Logo";
import { ApiUnavailableError, publicApiFetch } from "@/lib/api";
import { PublicApplyButton } from "@/components/PublicApplyButton";

interface PublicRole {
  id: number;
  title: string;
  description: string;
  location: string | null;
  is_remote: boolean;
  salary_text: string | null;
  company_name: string;
  created_at: string;
  trust: { verified: boolean; trust_level: string; label: string };
}

async function loadRole(id: string): Promise<PublicRole | null> {
  try {
    const { role } = await publicApiFetch<{ role: PublicRole }>(`/public/roles/${encodeURIComponent(id)}`);
    return role;
  } catch (e) {
    if (e instanceof ApiUnavailableError) return null;
    if ((e as { status?: number }).status === 404) notFound();
    throw e;
  }
}

// Open Graph so a pasted link (LinkedIn, WhatsApp, X) renders a rich card.
export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const role = await loadRole(id).catch(() => null);
  if (!role) return { title: "Job — Emploi" };
  const title = `${role.title} at ${role.company_name}`;
  const description = role.description.slice(0, 200);
  return {
    title: `${title} — Emploi`,
    description,
    openGraph: { title, description, type: "website" },
    twitter: { card: "summary", title, description },
  };
}

function TrustChip({ trust }: { trust: PublicRole["trust"] }) {
  if (trust.verified)
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-good-soft px-3 py-1 text-xs font-bold text-good">
        <BadgeCheck size={14} /> {trust.label}
      </span>
    );
  if (trust.trust_level === "medium" || trust.trust_level === "low")
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-soft px-3 py-1 text-xs font-bold text-brand">
        <ShieldCheck size={14} /> {trust.label}
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-soft px-3 py-1 text-xs font-bold text-amber">
      <ShieldAlert size={14} /> {trust.label}
    </span>
  );
}

export default async function PublicJobPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const role = await loadRole(id);
  if (!role) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-20 text-center">
        <p className="text-sm text-muted">This job can’t be loaded right now — please refresh in a moment.</p>
      </div>
    );
  }
  const session = await auth();
  const signedIn = Boolean(session?.user);

  return (
    <div className="min-h-dvh bg-surface">
      <header className="border-b border-line bg-card">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-4 py-4">
          <Link href="/" aria-label="Emploi home"><Logo markSize={22} /></Link>
          <Link href="/login" className="text-sm font-bold text-brand hover:underline">
            {signedIn ? "Dashboard" : "Sign in"}
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-4 py-8">
        <div className="rounded-3xl border border-line bg-card p-6 shadow-card sm:p-8">
          <div className="flex flex-wrap items-center gap-2">
            <TrustChip trust={role.trust} />
            {role.is_remote ? (
              <span className="rounded-full bg-brand-soft px-3 py-1 text-xs font-bold text-brand">Remote</span>
            ) : null}
          </div>

          <h1 className="mt-4 text-2xl font-extrabold tracking-tight sm:text-3xl">{role.title}</h1>
          <p className="mt-1 text-lg font-bold text-muted">{role.company_name}</p>

          <div className="mt-4 flex flex-wrap gap-4 text-sm text-muted">
            {role.location ? <span className="inline-flex items-center gap-1.5"><MapPin size={15} />{role.location}</span> : null}
            {role.salary_text ? <span className="inline-flex items-center gap-1.5"><Wallet size={15} />{role.salary_text}</span> : null}
          </div>

          <div className="mt-6">
            <PublicApplyButton roleId={role.id} signedIn={signedIn} />
          </div>

          <div className="mt-8 border-t border-line pt-6">
            <h2 className="text-sm font-extrabold uppercase tracking-wide text-faint">About this role</h2>
            <div className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-ink">{role.description}</div>
          </div>

          {/* Safety line — always on, regardless of trust tier. */}
          <p className="mt-8 rounded-xl bg-surface px-4 py-3 text-xs leading-relaxed text-muted">
            🛡️ Never pay a fee or share bank / ID details to apply for a job. If an
            employer asks, stop and report it.
          </p>
        </div>

        {/* Acquisition value prop for first-time visitors. */}
        <div className="mt-6 flex items-start gap-3 rounded-2xl border border-brand-soft bg-brand-soft/40 p-5">
          <Sparkles size={18} className="mt-0.5 shrink-0 text-brand" />
          <p className="text-sm leading-relaxed text-ink">
            <span className="font-bold">New to Emploi?</span> Sign in once with Google and your{" "}
            <span className="font-bold">Career Twin</span> applies, tailors your CV, and verifies
            employers for you — across every job, not just this one.
          </p>
        </div>

        <footer className="mt-8 text-center text-xs text-faint">
          © 2026 Crost Limited · <Link href="/privacy" className="hover:text-brand">Privacy</Link> ·{" "}
          <Link href="/terms" className="hover:text-brand">Terms</Link>
        </footer>
      </main>
    </div>
  );
}
