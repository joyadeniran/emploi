"use client";

import { useState } from "react";
import { Activity, BarChart3, Building2, Database, Menu, ShieldAlert, Users, X } from "lucide-react";
import { AdminSignOut } from "@/components/AdminSignOut";

const navigation = [
  { href: "#overview", label: "Overview", icon: BarChart3 },
  { href: "#operations", label: "Operations", icon: Activity },
  { href: "#sources", label: "Job sources", icon: Database },
  { href: "#trust", label: "Trust alerts", icon: ShieldAlert },
  { href: "#users", label: "Users", icon: Users },
  { href: "#employers", label: "Employers", icon: Building2 },
];

export function AdminSidebar({ email }: { email: string }) {
  const [open, setOpen] = useState(false);
  const links = (
    <nav className="space-y-1" aria-label="Admin navigation">
      {navigation.map(({ href, label, icon: Icon }) => (
        <a key={href} href={href} onClick={() => setOpen(false)}
          className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold text-muted transition-colors hover:bg-brand-soft hover:text-brand focus:bg-brand-soft focus:text-brand">
          <Icon size={17} /> {label}
        </a>
      ))}
    </nav>
  );

  return (
    <>
      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-line bg-card/95 px-4 py-3 backdrop-blur lg:hidden">
        <button onClick={() => setOpen(true)} aria-label="Open admin menu" className="rounded-lg p-2 text-muted hover:bg-surface"><Menu size={20} /></button>
        <p className="text-sm font-extrabold">Emploi Admin</p>
        <AdminSignOut />
      </header>
      {open ? <button aria-label="Close admin menu" onClick={() => setOpen(false)} className="fixed inset-0 z-40 bg-ink/30 lg:hidden" /> : null}
      <aside className={`fixed inset-y-0 left-0 z-50 flex w-72 flex-col border-r border-line bg-card p-4 transition-transform lg:sticky lg:top-0 lg:h-dvh lg:translate-x-0 ${open ? "translate-x-0" : "-translate-x-full"}`}>
        <div className="mb-8 flex items-start justify-between px-2 pt-2">
          <div>
            <p className="text-lg font-extrabold tracking-tight">Emploi Admin</p>
            <p className="mt-1 max-w-52 truncate text-xs text-muted">{email}</p>
          </div>
          <button onClick={() => setOpen(false)} aria-label="Close admin menu" className="rounded-lg p-1.5 text-muted hover:bg-surface lg:hidden"><X size={18} /></button>
        </div>
        {links}
        <div className="mt-auto border-t border-line px-2 pt-4">
          <p className="mb-3 text-xs font-semibold text-faint">Owner workspace</p>
          <AdminSignOut />
        </div>
      </aside>
    </>
  );
}
