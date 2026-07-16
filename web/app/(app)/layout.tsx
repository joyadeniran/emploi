import { auth, signOut } from "@/auth";
import { AppShell } from "@/components/AppShell";
import ClientRedirectToLogin from "@/components/ClientRedirectToLogin";

export default async function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await auth();
  if (!session?.user) {
    // Server cannot reliably know the original client path here; render a
    // tiny client-side redirect that preserves the current path as
    // `callbackUrl` so sign-in returns the user to their intended page.
    return <ClientRedirectToLogin />;
  }

  async function signOutAction() {
    "use server";
    await signOut({ redirectTo: "/login" });
  }

  return (
    <AppShell user={session.user} signOutAction={signOutAction}>
      {children}
    </AppShell>
  );
}
