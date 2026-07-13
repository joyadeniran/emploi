import { NextResponse } from "next/server";
import { apiFetch, ApiUnavailableError, DEMO_MODE } from "@/lib/api";

const DEMO_CAREER_TWIN = {
  name: "Joy Adesola",
  headline: "Product Designer",
  current_role: "Product Designer at Paystack",
  experience_years: "4 years",
  location: "Lagos, Nigeria",
  skills: ["Product Design", "UI/UX", "Figma", "User Research", "Prototyping", "Design Systems"],
  bio: "Product designer with 4 years of experience building user-centered digital products. I specialize in SaaS, fintech, and platforms.",
  preferred_roles: ["Product Designer", "Senior Product Designer", "UX Designer"],
  preferred_industries: ["Fintech", "SaaS", "B2B"],
  employment_type: "Full-time",
  remote_preference: "Remote or Hybrid",
  preferred_locations: ["Nigeria", "Anywhere in Africa"],
  salary_min: 1500,
  salary_max: 3500,
  currency: "USD",
  career_goals: ["Career Growth", "Remote work"],
  availability: "Open to new opportunities",
  onboarding_complete: false,
};

export async function POST(req: Request) {
  if (DEMO_MODE) {
    return NextResponse.json({ career_twin: DEMO_CAREER_TWIN });
  }

  const body = await req.json().catch(() => ({}));
  const cv_text = String(body.cv_text ?? "").trim();

  try {
    const data = await apiFetch<{ career_twin: Record<string, unknown> }>("/career-twin/extract", {
      method: "POST",
      body: JSON.stringify({ cv_text }),
    });
    return NextResponse.json(data);
  } catch (e) {
    if (e instanceof ApiUnavailableError) {
      return NextResponse.json({ error: "api offline" }, { status: 503 });
    }
    const err = e as Error & { status?: number };
    return NextResponse.json({ error: err.message }, { status: err.status ?? 500 });
  }
}
