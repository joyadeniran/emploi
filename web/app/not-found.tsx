import { LogoMark } from "@/components/Logo";

export default function NotFound() {
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
        <div className="glass-card p-8 sm:p-10">
          <div className="flex justify-center">
            <LogoMark size={36} />
          </div>
          <p className="mt-6 text-5xl font-extrabold tracking-tight text-brand">404</p>
          <h1 className="mt-2 text-lg font-extrabold tracking-tight">
            Page not found
          </h1>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            This page doesn&apos;t exist — but your next opportunity might.
          </p>
          <a
            href="/dashboard"
            className="mt-8 flex w-full items-center justify-center rounded-full bg-gradient-to-r from-brand-violet to-brand-indigo px-6 py-3.5 text-sm font-bold text-white shadow-pop transition-transform hover:-translate-y-0.5"
          >
            Go to dashboard
          </a>
        </div>
      </div>
    </div>
  );
}
