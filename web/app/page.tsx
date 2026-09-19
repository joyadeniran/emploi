import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { ApiUnavailableError, apiFetch, ensureUserSession } from "@/lib/api";

export default async function Home() {
  const session = await auth();
  if (!session?.user) redirect("/login");

  // Heal split identities (Google sub vs email-as-id) before we ask which
  // portal this person belongs to — otherwise a poster looks like a seeker.
  await ensureUserSession();
  try {
    const portal = await apiFetch<{ home: string }>("/user/portal");
    redirect(portal.home || "/dashboard");
  } catch (error) {
    if (error instanceof ApiUnavailableError) redirect("/dashboard");
    if ((error as { status?: number }).status === 401) redirect("/login");
    redirect("/dashboard");
  }
}
