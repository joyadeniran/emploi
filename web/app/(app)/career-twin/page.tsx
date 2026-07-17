import { redirect } from "next/navigation";
import { Info, Sparkles } from "lucide-react";
import { apiFetch, DEMO_MODE } from "@/lib/api";
import { PagePlaceholder } from "@/components/PagePlaceholder";
import { CareerTwinEditor } from "@/components/CareerTwinEditor";

export const metadata = { title: "Career Twin — Emploi" };

type Twin = Record<string, unknown>;

export default async function CareerTwinPage() {
  if (DEMO_MODE) return <PagePlaceholder icon={Sparkles} title="Career Twin" blurb="Your living profile is ready in demo mode." note="Connect the API to see a saved Career Twin." />;
  let twin: Twin;
  try {
    const result = await apiFetch<{ career_twin: Twin }>("/career-twin");
    twin = result.career_twin ?? {};
  } catch {
    // Backend unreachable OR errored: show a soft "unavailable" state. Never
    // redirect to onboarding on a transient error — a returning user with an
    // activated twin must not be bounced back into the wizard.
    return <PagePlaceholder icon={Info} title="Career Twin unavailable" blurb="We can’t reach your saved profile right now." note="Please refresh in a moment. Your data has not been changed." />;
  }
  // Genuinely missing or not-yet-activated twin → onboarding (this is the only
  // path that should ever send the user to the wizard).
  if (!Object.keys(twin).length || !twin.onboarding_complete) redirect("/create-career-twin");
  return <CareerTwinEditor twin={twin} />;
}
