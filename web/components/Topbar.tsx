"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Bell, Search, Menu, LogOut, ChevronDown, User, Loader2, Sparkles } from "lucide-react";

type MatchNotice = { id: number; title?: string; company_name?: string; fit_score?: number };

export function Topbar({
  user,
  onMenu,
  signOutAction,
}: {
  user: { name?: string | null; email?: string | null; image?: string | null };
  onMenu: () => void;
  signOutAction: () => Promise<void>;
}) {
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);
  const [bellOpen, setBellOpen] = useState(false);
  const [notices, setNotices] = useState<MatchNotice[] | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const bellRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
      if (bellRef.current && !bellRef.current.contains(e.target as Node)) {
        setBellOpen(false);
      }
    }
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        searchRef.current?.focus();
      }
    }
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  async function openBell() {
    const next = !bellOpen;
    setBellOpen(next);
    if (next && notices === null) {
      try {
        const res = await fetch("/api/matches?limit=5");
        const data = res.ok ? await res.json() : { matches: [] };
        setNotices(Array.isArray(data.matches) ? data.matches : []);
      } catch {
        setNotices([]);
      }
    }
  }

  const initials =
    user.name
      ?.split(/\s+/)
      .slice(0, 2)
      .map((p) => p[0])
      .join("")
      .toUpperCase() ?? "U";

  return (
    <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-line bg-card-glass px-4 py-3 backdrop-blur-md lg:px-8">
      <button
        onClick={onMenu}
        className="rounded-xl border border-line p-2 text-muted hover:bg-surface lg:hidden"
        aria-label="Open menu"
      >
        <Menu size={18} />
      </button>

      <form
        className="relative hidden max-w-md flex-1 sm:block"
        onSubmit={(e) => {
          e.preventDefault();
          const q = searchRef.current?.value.trim();
          router.push(q ? `/jobs?q=${encodeURIComponent(q)}` : "/jobs");
        }}
      >
        <Search
          size={16}
          className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-faint"
        />
        <input
          ref={searchRef}
          type="search"
          placeholder="Search jobs, companies or skills..."
          className="w-full rounded-full border border-line bg-surface py-2.5 pl-10 pr-12 text-sm outline-none transition-colors placeholder:text-faint focus:border-brand/40 focus:bg-card"
        />
        <kbd className="pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2 rounded-md border border-line bg-card px-1.5 py-0.5 text-[10px] font-semibold text-faint">
          ⌘K
        </kbd>
      </form>

      <div className="ml-auto flex items-center gap-2">
        <div className="relative" ref={bellRef}>
          <button
            onClick={openBell}
            className="relative rounded-full border border-line p-2.5 text-muted hover:bg-surface"
            aria-label="Notifications"
            aria-expanded={bellOpen}
            aria-haspopup="menu"
          >
            <Bell size={17} />
            {notices === null || notices.length > 0 ? (
              <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-brand ring-2 ring-white" />
            ) : null}
          </button>
          {bellOpen ? (
            <div role="menu" className="absolute right-0 top-12 z-40 w-80 rounded-2xl border border-line bg-card p-2 shadow-pop">
              <p className="px-3 py-2 text-xs font-bold uppercase tracking-wide text-faint">Latest matches</p>
              {notices === null ? (
                <p className="flex items-center gap-2 px-3 py-3 text-sm text-muted">
                  <Loader2 size={14} className="animate-spin" /> Checking…
                </p>
              ) : notices.length === 0 ? (
                <p className="px-3 py-3 text-sm text-muted">
                  Nothing yet — your Career Twin scans new jobs every night and you&apos;ll see matches here.
                </p>
              ) : (
                <>
                  {notices.map((n) => (
                    <Link key={n.id} href="/matches" role="menuitem" onClick={() => setBellOpen(false)}
                      className="flex items-start gap-2.5 rounded-xl px-3 py-2.5 hover:bg-surface">
                      <Sparkles size={15} className="mt-0.5 shrink-0 text-brand" />
                      <span className="min-w-0 text-sm">
                        <span className="block truncate font-bold">{n.title || "New match"}</span>
                        <span className="block truncate text-muted">
                          {n.company_name || "Unknown company"}{typeof n.fit_score === "number" ? ` · fit ${n.fit_score}/100` : ""}
                        </span>
                      </span>
                    </Link>
                  ))}
                  <Link href="/matches" role="menuitem" onClick={() => setBellOpen(false)}
                    className="mt-1 block rounded-xl bg-brand-soft/60 px-3 py-2.5 text-center text-sm font-bold text-brand hover:bg-brand-soft">
                    View all matches
                  </Link>
                </>
              )}
            </div>
          ) : null}
        </div>

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
              className="absolute right-0 mt-2 w-56 rounded-2xl border border-line bg-card p-1.5 shadow-card"
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
