"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Home,
  Sparkles,
  Briefcase,
  FileText,
  MessageSquare,
  Bookmark,
  Mic,
  BarChart3,
  Search,
  ShieldCheck,
  Users,
  Settings,
  X,
} from "lucide-react";
import { Logo } from "./Logo";
import { PlanCard } from "./PlanCard";

const mainNav = [
  { href: "/dashboard", label: "Home", icon: Home },
  { href: "/career-twin", label: "Career Twin", icon: Sparkles, badge: "New" },
  { href: "/matches", label: "Job Matches", icon: Briefcase },
  { href: "/jobs", label: "Browse Jobs", icon: Search },
  { href: "/applications", label: "Applications", icon: FileText },
  { href: "/messages", label: "Messages", icon: MessageSquare },
  { href: "/saved", label: "Saved Jobs", icon: Bookmark },
  { href: "/interview-prep", label: "Interview Prep", icon: Mic },
  { href: "/insights", label: "Career Insights", icon: BarChart3 },
  { href: "/trust-check", label: "Trust Check", icon: ShieldCheck },
  { href: "/settings", label: "Settings", icon: Settings },
];

const recruiterNav = [
  { href: "/recruiter", label: "Recruiter Workspace", icon: Users, badge: "Beta" },
];

function NavLink({
  href,
  label,
  icon: Icon,
  badge,
  active,
  onNavigate,
}: {
  href: string;
  label: string;
  icon: typeof Home;
  badge?: string;
  active: boolean;
  onNavigate?: () => void;
}) {
  return (
    <Link
      href={href}
      onClick={onNavigate}
      className={`flex items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm font-semibold transition-colors ${
        active
          ? "bg-brand-soft text-brand"
          : "text-muted hover:bg-surface hover:text-ink"
      }`}
      aria-current={active ? "page" : undefined}
    >
      <Icon size={18} strokeWidth={2} />
      <span className="flex-1">{label}</span>
      {badge ? (
        <span className="rounded-full bg-brand px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white">
          {badge}
        </span>
      ) : null}
    </Link>
  );
}

export function Sidebar({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const pathname = usePathname();

  const content = (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between px-5 pb-4 pt-6">
        <Link href="/dashboard" aria-label="Emploi home">
          <Logo markSize={22} />
        </Link>
        <button
          onClick={onClose}
          className="rounded-lg p-1.5 text-muted hover:bg-surface lg:hidden"
          aria-label="Close menu"
        >
          <X size={18} />
        </button>
      </div>

      <nav className="nav-scroll flex-1 space-y-0.5 overflow-y-auto px-3" aria-label="Main">
        {mainNav.map((item) => (
          <NavLink
            key={item.href}
            {...item}
            active={pathname === item.href}
            onNavigate={onClose}
          />
        ))}
        <div className="px-3.5 pb-1 pt-6 text-[11px] font-bold uppercase tracking-widest text-faint">
          For recruiters
        </div>
        {recruiterNav.map((item) => (
          <NavLink
            key={item.href}
            {...item}
            active={pathname === item.href}
            onNavigate={onClose}
          />
        ))}
      </nav>

      <div className="p-4">
        <PlanCard />
      </div>
    </div>
  );

  return (
    <>
      {/* mobile overlay */}
      <div
        className={`fixed inset-0 z-40 bg-ink/30 backdrop-blur-sm transition-opacity lg:hidden ${
          open ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
        onClick={onClose}
        aria-hidden="true"
      />
      <aside
        className={`fixed inset-y-0 left-0 z-50 w-72 border-r border-line bg-white transition-transform lg:sticky lg:top-0 lg:z-auto lg:h-dvh lg:translate-x-0 lg:overflow-hidden ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
        aria-label="Sidebar"
      >
        {content}
      </aside>
    </>
  );
}
