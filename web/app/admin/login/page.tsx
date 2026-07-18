import { redirect } from "next/navigation";
import { getAdminEmail } from "@/lib/admin";
import { AdminLoginForm } from "@/components/AdminLoginForm";

// Standalone admin login — email + password, NO Google, NO career twin. If a
// valid admin cookie already exists, skip straight to the dashboard.
export default async function AdminLoginPage() {
  if (await getAdminEmail()) redirect("/admin");
  return (
    <div className="flex min-h-dvh items-center justify-center bg-surface px-4">
      <div className="w-full max-w-sm">
        <div className="rounded-3xl border border-line bg-card p-8 shadow-card">
          <h1 className="text-xl font-extrabold tracking-tight">Emploi Admin</h1>
          <p className="mt-1 text-sm text-muted">Staff sign-in. This is not the candidate or employer login.</p>
          <AdminLoginForm />
        </div>
        <p className="mt-4 text-center text-xs text-faint">Authorized personnel only.</p>
      </div>
    </div>
  );
}
