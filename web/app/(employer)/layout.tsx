import { auth, signOut } from "@/auth";
import { EmployerShell } from "@/components/EmployerShell";
import ClientRedirectToLogin from "@/components/ClientRedirectToLogin";

export default async function EmployerLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await auth();
  if (!session?.user) {
    return <ClientRedirectToLogin loginPath="/employer/login" />;
  }

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
