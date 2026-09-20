import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { apiFetch, ensureUserSession } from "@/lib/api";

export default async function Home() {
  const session = await auth();
  if (!session?.user) redirect("/login");

  // Heal split identities (Google sub vs email-as-id) before we ask which
  // portal this person belongs to — otherwise a poster looks like a seeker.
  await ensureUserSession();

  // IMPORTANT: never call redirect() inside this try. Next.js implements
  // redirect() by throwing; a catch here swallows it and every signed-in
  // user — including posters — falls through to /dashboard. That is the
  // "emploi can't tell a job poster from a seeker" bug.
  let home = "/dashboard";
  try {
    const portal = await apiFetch<{ home: string }>("/user/portal");
    home = portal.home || "/dashboard";
  } catch (error) {
    if ((error as { status?: number }).status === 401) redirect("/login");
  }
  redirect(home);
}
