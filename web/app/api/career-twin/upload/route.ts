import { NextResponse } from "next/server";
import { apiFetch, ApiUnavailableError, DEMO_MODE } from "@/lib/api";

const DEMO_CAREER_TWIN = {
  name: "Joy Adesola",
  headline: "Product Designer",
  current_role: "Product Designer at Paystack",
  experience_years: "4",
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

/**
 * Accepts a multipart/form-data upload with a `file` field (PDF).
 * TODO: Extract text from the PDF server-side (e.g. via pdf-parse or by
 * forwarding the binary to the FastAPI /career-twin/extract endpoint).
 * For now we send the filename as a placeholder so the UI flow works.
 */
export async function POST(req: Request) {
  if (DEMO_MODE) {
    return NextResponse.json({ career_twin: DEMO_CAREER_TWIN });
  }

  let filename = "resume.pdf";
  try {
    const formData = await req.formData();
    const file = formData.get("file");
    if (file && typeof file === "object" && "name" in file) {
      filename = (file as File).name;
    }
  } catch {
    /* non-multipart request — fall through with placeholder */
  }

  // TODO: Replace with real PDF→text extraction. Currently sends filename
  // as cv_text which will produce an empty/error profile from the backend.
  const cv_text = `[PDF upload: ${filename}]`;

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
