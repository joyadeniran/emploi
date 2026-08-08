import { auth, signOut } from "@/auth";
import { EmployerShell } from "@/components/EmployerShell";
import ClientRedirectToLogin from "@/components/ClientRedirectToLogin";
import { ensureUserSession } from "@/lib/api";

export default async function EmployerLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await auth();
  if (!session?.user) {
    return <ClientRedirectToLogin loginPath="/employer/login" />;
  }

  // The poster's `users` row is what the notify worker reads as `poster_email`
  // to tell them someone applied — there is no fallback for it, so without
  // this the employer digest silently skips every poster.
  await ensureUserSession();

  async function signOutAction() {
    "use server";
    await signOut({ redirectTo: "/employer/login" });
  }

  return (
    <EmployerShell user={session.user} signOutAction={signOutAction}>
      {children}
    </EmployerShell>
  );
}
