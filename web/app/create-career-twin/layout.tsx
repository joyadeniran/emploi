import { auth } from "@/auth";
import { firstName } from "@/lib/data";
import ClientRedirectToLogin from "@/components/ClientRedirectToLogin";
import { ensureUserSession } from "@/lib/api";

export default async function CreateCareerTwinLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await auth();
  if (!session?.user) {
    return <ClientRedirectToLogin />;
  }
  await ensureUserSession();

  // Inject the user's first name into a meta tag the client wizard can read
  const name = firstName(session.user.name);

  return (
    <>
      <meta name="x-user-name" content={name} />
      {children}
    </>
  );
}
