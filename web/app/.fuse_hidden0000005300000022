"use client";

import { LogoMark } from "@/components/Logo";

export default function GlobalError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="relative flex min-h-dvh items-center justify-center overflow-hidden bg-surface px-4">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -left-32 -top-32 h-96 w-96 rounded-full bg-brand-violet/20 blur-3xl"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -bottom-32 -right-32 h-96 w-96 rounded-full bg-brand-indigo/20 blur-3xl"
      />

      <div className="rise-in w-full max-w-sm text-center">
        <div className="rounded-3xl border border-white/70 bg-white/70 p-8 shadow-card backdrop-blur-xl sm:p-10">
          <div className="flex justify-center">
            <LogoMark size={36} />
          </div>
          <h1 className="mt-6 text-xl font-extrabold tracking-tight">
            Something went wrong
          </h1>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            An unexpected error occurred. Your data is safe — try again, or head
            back to your dashboard.
          </p>
          <div className="mt-8 space-y-3">
            <button
              onClick={reset}
              className="flex w-full items-center justify-center rounded-full bg-gradient-to-r from-brand-violet to-brand-indigo px-6 py-3.5 text-sm font-bold text-white shadow-pop transition-transform hover:-translate-y-0.5"
            >
              Try again
            </button>
            <a
              href="/dashboard"
              className="flex w-full items-center justify-center rounded-full border border-line bg-white px-6 py-3.5 text-sm font-bold transition-all hover:-translate-y-0.5 hover:shadow-card"
            >
              Go to dashboard
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}
