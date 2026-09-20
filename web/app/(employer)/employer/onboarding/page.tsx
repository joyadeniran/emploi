import { auth } from "@/auth";
import { redirect } from "next/navigation";
import { EmployerOnboardingForm } from "@/components/EmployerOnboardingForm";
import { apiFetch, ensureUserSession } from "@/lib/api";

export default async function EmployerOnboardingPage() {
  const session = await auth();
  await ensureUserSession();
  // If this Google account already owns a company (including one posted
  // under a previous identity), skip the form. Creating Supplya for the
  // sixth time is how the jobs kept vanishing.
  // redirect() must NOT sit inside try/catch — Next.js implements it by
  // throwing and the catch would swallow it.
  let hasEmployer = false;
  try {
    await apiFetch("/employer");
    hasEmployer = true;
  } catch (error) {
    const status = (error as { status?: number }).status;
    // Only a real "no company" 404 should show the form. A 500 from the
    // heal must not look like a first-time signup (that is how a sixth
    // empty Supplya got created).
    if (status && status !== 404) throw error;
  }
  if (hasEmployer) redirect("/employer");
  return <EmployerOnboardingForm email={session?.user?.email ?? ""} />;
}