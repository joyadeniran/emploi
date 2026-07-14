"use client";

import { useState } from "react";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

export function AppShell({
  user,
  signOutAction,
  children,
}: {
  user: { name?: string | null; email?: string | null; image?: string | null };
  signOutAction: () => Promise<void>;
  children: React.ReactNode;
}) {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div className="flex min-h-dvh">
      <Sidebar open={menuOpen} onClose={() => setMenuOpen(false)} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar
          user={user}
          onMenu={() => setMenuOpen(true)}
          signOutAction={signOutAction}
        />
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
