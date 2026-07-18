import { auth } from "@/auth";
import { EmployerOnboardingForm } from "@/components/EmployerOnboardingForm";

// Server component: read the signed-in identity here and hand it to the client
// form as a prop. Prefilling the domain from a work email (Google already
// verified that mailbox) needs no client effect or meta-tag hop this way.
export default async function EmployerOnboardingPage() {
  const session = await auth();
  return <EmployerOnboardingForm email={session?.user?.email ?? ""} />;
}
