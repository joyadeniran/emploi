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
    <>
      {/* The onboarding wizard reads these to prefill the company domain from a
          work email (Google already proved control of that mailbox) and to show
          the employer who they're signed in as. */}
      <meta name="x-user-email" content={session.user.email ?? ""} />
      <meta name="x-user-name" content={session.user.name ?? ""} />
      <EmployerShell user={session.user} signOutAction={signOutAction}>
        {children}
      </EmployerShell>
    </>
  );
}
