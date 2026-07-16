import type { LucideIcon } from "lucide-react";

export function PagePlaceholder({
  icon: Icon,
  title,
  blurb,
  note = "This section is on the way — your Career Twin is already collecting the data behind it.",
}: {
  icon: LucideIcon;
  title: string;
  blurb: string;
  note?: string;
}) {
  return (
    <div className="mx-auto max-w-7xl">
      <h1 className="rise-in text-2xl font-extrabold tracking-tight sm:text-3xl">{title}</h1>
      <p className="mt-1 max-w-xl text-sm text-muted">{blurb}</p>
      <div className="rise-in mt-8 flex flex-col items-center rounded-3xl border border-dashed border-line bg-white/60 px-6 py-16 text-center">
        <span className="flex h-16 w-16 items-center justify-center rounded-2xl bg-brand-soft">
          <Icon size={28} className="text-brand" />
        </span>
        <p className="mt-5 max-w-sm text-sm font-semibold leading-relaxed text-muted">{note}</p>
      </div>
    </div>
  );
}
