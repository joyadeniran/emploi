"use client";

import { useState, useRef, useEffect } from "react";
import { Bell, Search, Menu, LogOut, ChevronDown, User } from "lucide-react";

export function Topbar({
  user,
  onMenu,
  signOutAction,
}: {
  user: { name?: string | null; email?: string | null; image?: string | null };
  onMenu: () => void;
  signOutAction: () => Promise<void>;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  const initials =
    user.name
      ?.split(/\s+/)
      .slice(0, 2)
      .map((p) => p[0])
      .join("")
      .toUpperCase() ?? "U";

  return (
    <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-line bg-white/80 px-4 py-3 backdrop-blur-md lg:px-8">
      <button
        onClick={onMenu}
        className="rounded-xl border border-line p-2 text-muted hover:bg-surface lg:hidden"
        aria-label="Open menu"
      >
        <Menu size={18} />
      </button>

      <div className="relative hidden max-w-md flex-1 sm:block">
        <Search
          size={16}
          className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-faint"
        />
        <input
          type="search"
          placeholder="Search jobs, companies or skills..."
          className="w-full rounded-full border border-line bg-surface py-2.5 pl-10 pr-12 text-sm outline-none transition-colors placeholder:text-faint focus:border-brand/40 focus:bg-white"
        />
        <kbd className="pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2 rounded-md border border-line bg-white px-1.5 py-0.5 text-[10px] font-semibold text-faint">
          ⌘K
        </kbd>
      </div>

      <div className="ml-auto flex items-center gap-2">
        <button
          className="relative rounded-full border border-line p-2.5 text-muted hover:bg-surface"
          aria-label="Notifications"
        >
          <Bell size={17} />
          <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-brand ring-2 ring-white" />
        </button>

        <div className="relative" ref={menuRef}>
          <button
            onClick={() => setMenuOpen((v) => !v)}
            className="flex items-center gap-2.5 rounded-full border border-line py-1 pl-1 pr-2.5 hover:bg-surface"
            aria-expanded={menuOpen}
            aria-haspopup="menu"
          >
            {user.image ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={user.image}
                alt=""
                className="h-8 w-8 rounded-full object-cover"
              />
            ) : (
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-brand-violet to-brand-indigo text-xs font-bold text-white">
                {initials}
              </span>
            )}
            <span className="hidden text-left md:block">
              <span className="block text-sm font-bold leading-tight">
                {user.name ?? "Account"}
              </span>
              <span className="block text-[11px] leading-tight text-muted">
                Career Twin
              </span>
            </span>
            <ChevronDown size={14} className="text-faint" />
          </button>

          {menuOpen ? (
            <div
              role="menu"
              className="absolute right-0 mt-2 w-56 rounded-2xl border border-line bg-white p-1.5 shadow-card"
            >
              <div className="px-3 py-2">
                <p className="text-sm font-bold">{user.name}</p>
                <p className="truncate text-xs text-muted">{user.email}</p>
              </div>
              <div className="my-1 h-px bg-line" />
              <a
                href="/career-twin"
                role="menuitem"
                className="flex items-center gap-2.5 rounded-xl px-3 py-2 text-sm font-semibold text-muted hover:bg-surface hover:text-ink"
              >
                <User size={15} /> View profile
              </a>
              <form action={signOutAction}>
                <button
                  type="submit"
                  role="menuitem"
                  className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-left text-sm font-semibold text-warn hover:bg-warn-soft"
                >
                  <LogOut size={15} /> Sign out
                </button>
              </form>
            </div>
          ) : null}
        </div>
      </div>
    </header>
  );
}
