"use client";

// Error boundary inside the app shell — the sidebar/topbar keep working;
// only the page content is replaced.
export default function AppError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="mx-auto flex min-h-[60dvh] max-w-md flex-col items-center justify-center text-center">
      <h1 className="text-xl font-extrabold tracking-tight">
        This page hit a snag
      </h1>
      <p className="mt-2 text-sm leading-relaxed text-muted">
        Something went wrong loading this page. Your data is safe.
      </p>
      <button
        onClick={reset}
        className="mt-6 rounded-full bg-gradient-to-r from-brand-violet to-brand-indigo px-6 py-3 text-sm font-bold text-white shadow-pop transition-transform hover:-translate-y-0.5"
      >
        Try again
      </button>
    </div>
  );
}
