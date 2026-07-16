import { redirect } from "next/navigation";
import { auth, signOut } from "@/auth";
import { Logo } from "@/components/Logo";
import { LogOut } from "lucide-react";

export default async function SignOutPage() {
  const session = await auth();
  if (!session?.user) redirect("/login");

  async function confirmSignOut() {
    "use server";
    await signOut({ redirectTo: "/login" });
  }

  return (
    <div className="relative flex min-h-dvh items-center justify-center overflow-hidden bg-surface px-4">
      {/* brand orbs */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -left-32 -top-32 h-96 w-96 rounded-full bg-brand-violet/25 blur-3xl"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -bottom-32 -right-32 h-96 w-96 rounded-full bg-brand-indigo/25 blur-3xl"
      />

      <div className="rise-in w-full max-w-sm">
        <div className="glass-card p-8 sm:p-10">
          <div className="flex justify-center">
            <Logo markSize={24} />
          </div>

          <div className="mt-6 text-center">
            <h1 className="text-xl font-extrabold tracking-tight">
              Sign out of Emploi?
            </h1>
            <p className="mt-2 text-sm leading-relaxed text-muted">
              {session.user.name
                ? `You're signed in as ${session.user.name}.`
                : "You'll need to sign back in to access your Career Twin."}
            </p>
          </div>

          <div className="mt-8 space-y-3">
            <form action={confirmSignOut}>
              <button
                type="submit"
                className="flex w-full items-center justify-center gap-2 rounded-full bg-warn px-6 py-3.5 text-sm font-bold text-white transition-transform hover:-translate-y-0.5"
              >
                <LogOut size={16} />
                Yes, sign me out
              </button>
            </form>

            <a
              href="/dashboard"
              className="flex w-full items-center justify-center rounded-full border border-line bg-card px-6 py-3.5 text-sm font-bold transition-all hover:-translate-y-0.5 hover:shadow-card"
            >
              Go back to dashboard
            </a>
          </div>
        </div>

        <p className="mt-6 text-center text-xs text-faint">
          © 2026 Crost Limited · Emploi
        </p>
      </div>
    </div>
  );
}
