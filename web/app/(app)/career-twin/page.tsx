import { redirect } from "next/navigation";
import { Info, Sparkles } from "lucide-react";
import { ApiUnavailableError, apiFetch, DEMO_MODE } from "@/lib/api";
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
  } catch (error) {
    if (error instanceof ApiUnavailableError) return <PagePlaceholder icon={Info} title="Career Twin unavailable" blurb="We can’t reach your saved profile right now." note="Please refresh in a moment. Your data has not been changed." />;
    redirect("/create-career-twin");
  }
  if (!Object.keys(twin).length || !twin.onboarding_complete) redirect("/create-career-twin");
  return <CareerTwinEditor twin={twin} />;
}
