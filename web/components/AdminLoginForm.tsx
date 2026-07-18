"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Lock } from "lucide-react";

export function AdminLoginForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/admin/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim(), password }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || "Sign-in failed.");
      }
      router.replace("/admin");
      router.refresh();
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mt-6 space-y-3">
      <div>
        <label htmlFor="admin-email" className="mb-1 block text-xs font-bold text-muted">Email</label>
        <input
          id="admin-email" type="email" autoComplete="username" required value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full rounded-xl border border-line bg-card px-3.5 py-2.5 text-sm outline-none focus:border-brand"
        />
      </div>
      <div>
        <label htmlFor="admin-pw" className="mb-1 block text-xs font-bold text-muted">Password</label>
        <input
          id="admin-pw" type="password" autoComplete="current-password" required value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full rounded-xl border border-line bg-card px-3.5 py-2.5 text-sm outline-none focus:border-brand"
        />
      </div>
      {error ? <p role="alert" className="text-sm font-semibold text-warn">{error}</p> : null}
      <button
        type="submit" disabled={busy || !email.trim() || !password}
        className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-brand-violet to-brand-indigo px-5 py-3 text-sm font-bold text-white shadow-pop disabled:opacity-60"
      >
        {busy ? <Loader2 size={16} className="animate-spin" /> : <Lock size={16} />}
        Sign in
      </button>
    </form>
  );
}
