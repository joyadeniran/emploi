"use client";

import { useRouter } from "next/navigation";
import { LogOut } from "lucide-react";

export function AdminSignOut() {
  const router = useRouter();
  async function signOut() {
    await fetch("/api/admin/logout", { method: "POST" });
    router.replace("/admin/login");
  }
  return (
    <button
      onClick={signOut}
      className="inline-flex items-center gap-2 rounded-full border border-line px-4 py-2 text-sm font-semibold text-warn hover:bg-warn-soft"
    >
      <LogOut size={15} /> Sign out
    </button>
  );
}
