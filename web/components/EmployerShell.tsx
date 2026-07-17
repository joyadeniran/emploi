"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Plus,
  CreditCard,
  Menu,
  X,
  LogOut,
  ArrowLeftRight,
} from "lucide-react";
import { Logo } from "./Logo";
import { ThemeToggle } from "./ThemeToggle";

const employerNav = [
  { href: "/employer", label: "Dashboard", icon: LayoutDashboard },
  { href: "/employer/roles/new", label: "Post a role", icon: Plus },
  { href: "/employer/billing", label: "Credits & billing", icon: CreditCard },
];

function EmployerNav({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <nav className="flex-1 space-y-0.5 px-3" aria-label="Employer">
      {employerNav.map(({ href, label, icon: Icon }) => {
        const active = href === "/employer" ? pathname === href : pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={`flex items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm font-semibold transition-colors ${
              active ? "bg-brand-soft text-brand" : "text-muted hover:bg-surface hover:text-ink"
            }`}
          >
            <Icon size={18} strokeWidth={2} />
            <span className="flex-1">{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

export function EmployerShell({
  user,
  signOutAction,
  children,
}: {
  user: { name?: string | null; email?: string | null };
  signOutAction: () => Promise<void>;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);

  const sidebarBody = (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between px-5 pb-4 pt-6">
        <Link href="/employer" aria-label="Emploi for employers" className="flex items-center gap-2">
          <Logo markSize={22} />
          <span className="rounded-lg bg-surface px-2 py-0.5 text-[11px] font-medium text-muted">
            employers
          </span>
        </Link>
        <button
          onClick={() => setOpen(false)}
          className="rounded-lg p-1.5 text-muted hover:bg-surface lg:hidden"
          aria-label="Close menu"
        >
          <X size={18} />
        </button>
      </div>

      <EmployerNav onNavigate={() => setOpen(false)} />

      <div className="space-y-3 p-4">
        <Link
          href="/dashboard"
          className="flex items-center gap-2.5 rounded-xl border border-line px-3.5 py-2.5 text-sm font-semibold text-muted transition-colors hover:bg-surface hover:text-ink"
        >
          <ArrowLeftRight size={16} /> Switch to job search
        </Link>
        <div className="flex justify-center">
          <ThemeToggle />
        </div>
      </div>
    </div>
  );

  return (
    <div className="flex min-h-dvh">
      {/* mobile overlay */}
      <div
        className={`fixed inset-0 z-40 bg-ink/30 backdrop-blur-sm transition-opacity lg:hidden ${
          open ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
        onClick={() => setOpen(false)}
        aria-hidden="true"
      />
      <aside
        className={`fixed inset-y-0 left-0 z-50 w-72 border-r border-line bg-card transition-transform lg:sticky lg:top-0 lg:z-auto lg:h-dvh lg:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
        aria-label="Employer sidebar"
      >
        {sidebarBody}
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-line bg-card-glass px-4 py-3 backdrop-blur-md lg:px-8">
          <button
            onClick={() => setOpen(true)}
            className="rounded-xl border border-line p-2 text-muted hover:bg-surface lg:hidden"
            aria-label="Open menu"
          >
            <Menu size={18} />
          </button>
          <div className="ml-auto flex items-center gap-3">
            <span className="hidden text-right sm:block">
              <span className="block text-sm font-bold leading-tight">{user.name ?? "Account"}</span>
              <span className="block text-[11px] leading-tight text-muted">Employer</span>
            </span>
            <form action={signOutAction}>
              <button
                type="submit"
                className="flex items-center gap-2 rounded-full border border-line px-3 py-2 text-sm font-semibold text-warn hover:bg-warn-soft"
              >
                <LogOut size={15} /> Sign out
              </button>
            </form>
          </div>
        </header>

        <main className="flex-1 px-4 py-6 lg:px-8">{children}</main>

        <footer className="border-t border-line px-4 py-3 text-center text-xs text-faint lg:px-8">
          <a href="/privacy" className="hover:text-brand">Privacy Policy</a>
          <span className="mx-2">·</span>
          <a href="/terms" className="hover:text-brand">Terms of Service</a>
          <span className="mx-2">·</span>
          © 2026 Crost Limited
        </footer>
      </div>
    </div>
  );
}
