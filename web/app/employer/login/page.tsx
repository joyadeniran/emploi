import { redirect } from "next/navigation";
import { auth, signIn, googleConfigured } from "@/auth";
import { Logo } from "@/components/Logo";

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M23.5 12.27c0-.85-.08-1.66-.22-2.45H12v4.64h6.45a5.52 5.52 0 0 1-2.39 3.62v3h3.87c2.26-2.09 3.57-5.17 3.57-8.81Z"
      />
      <path
        fill="#34A853"
        d="M12 24c3.24 0 5.96-1.07 7.93-2.92l-3.87-3c-1.07.72-2.44 1.15-4.06 1.15-3.12 0-5.77-2.11-6.71-4.95H1.29v3.1A12 12 0 0 0 12 24Z"
      />
      <path
        fill="#FBBC05"
        d="M5.29 14.28a7.2 7.2 0 0 1 0-4.56v-3.1H1.29a12 12 0 0 0 0 10.76l4-3.1Z"
      />
      <path
        fill="#EA4335"
        d="M12 4.77c1.76 0 3.34.6 4.58 1.79l3.44-3.44C17.95 1.19 15.23 0 12 0A12 12 0 0 0 1.29 6.62l4 3.1C6.23 6.88 8.88 4.77 12 4.77Z"
      />
    </svg>
  );
}

export default async function EmployerLoginPage() {
  const session = await auth();
  if (session?.user) redirect("/employer");

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

      <div className="rise-in w-full max-w-md">
        <div className="glass-card p-8 sm:p-10">
          {/* Logo + "for employers" badge */}
          <div className="flex items-center justify-center gap-2">
            <Logo markSize={24} />
            <span className="rounded-lg bg-surface px-2 py-0.5 text-[11px] font-medium text-muted">
              for employers
            </span>
          </div>

          <h1 className="mt-6 text-center text-2xl font-extrabold tracking-tight">
            Hire with Emploi.
          </h1>
          <p className="mt-2 text-center text-sm leading-relaxed text-muted">
            Post a role and get matched with verified candidates.
            Your first role is free.
          </p>

          <div className="mt-8 space-y-4">
            {/* Google sign-in */}
            {googleConfigured ? (
              <form
                action={async () => {
                  "use server";
                  await signIn("google", { redirectTo: "/employer" });
                }}
              >
                <button
                  type="submit"
                  className="flex w-full items-center justify-center gap-3 rounded-full border border-line bg-card px-6 py-3.5 text-sm font-bold transition-all hover:-translate-y-0.5 hover:shadow-card"
                >
                  <GoogleIcon />
                  Continue with Google
                </button>
              </form>
            ) : (
              <div className="rounded-2xl border border-amber/30 bg-amber-soft px-4 py-3 text-xs leading-relaxed text-ink">
                Google sign-in isn&apos;t configured yet — set{" "}
                <code className="font-mono font-bold">GOOGLE_CLIENT_ID</code> and{" "}
                <code className="font-mono font-bold">GOOGLE_CLIENT_SECRET</code>{" "}
                (see <code className="font-mono font-bold">.env.example</code>).
              </div>
            )}

            {/* No email/password form here. It was a stub: the button was
                disabled and the "sign up" link was a <span>, so employers typed
                real (often reused) passwords into a field that went nowhere.
                Google is the product's auth method (see auth.ts) — work email
                works through it via Google Workspace. Real credentials sign-in
                needs a design pass (password storage, verification, reset,
                login rate-limiting), not a form that lies. */}
            <p className="text-center text-xs leading-relaxed text-faint">
              Emploi uses Google to sign in — your work email works here if your
              company uses Google Workspace. Signing in creates your employer
              account.
            </p>
          </div>

          {/* Cross-link to candidate login */}
          <p className="mt-6 text-center text-xs text-faint">
            Looking for jobs instead?{" "}
            <a href="/login" className="font-bold text-muted hover:text-brand">
              Sign in as a candidate
            </a>
          </p>
        </div>

        <p className="mt-6 text-center text-xs leading-relaxed text-faint">
          By continuing you agree to our{" "}
          <a href="/terms" className="font-semibold text-muted hover:text-brand">
            Terms
          </a>{" "}
          and{" "}
          <a href="/privacy" className="font-semibold text-muted hover:text-brand">
            Privacy Policy
          </a>
          .<br />© 2026 Crost Limited · Emploi is a brand of Crost Limited (RC 9526947)
        </p>
      </div>
    </div>
  );
}
