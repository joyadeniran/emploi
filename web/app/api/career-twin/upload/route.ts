import { NextResponse } from "next/server";
import { auth } from "@/auth";
import { DEMO_MODE } from "@/lib/api";

const API_URL = process.env.EMPLOI_API_URL ?? "http://localhost:8000";
const API_KEY = process.env.EMPLOI_API_KEY ?? "";

// Gemini extraction takes 10-30s; without this Vercel kills the function at
// its default limit and the wizard sees a failed upload.
export const maxDuration = 60;

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

/**
 * Forwards the uploaded PDF to the FastAPI /career-twin/upload endpoint,
 * which runs core.pdf_to_text() + core.extract_profile() server-side.
 * Returns the extracted career twin data.
 */
export async function POST(req: Request) {
  if (DEMO_MODE) {
    return NextResponse.json({ career_twin: DEMO_CAREER_TWIN });
  }

  const session = await auth();
  const userId =
    (session?.user as { id?: string } | undefined)?.id ?? session?.user?.email;
  if (!userId) {
    return NextResponse.json({ error: "not authenticated" }, { status: 401 });
  }

  let formData: FormData;
  try {
    formData = await req.formData();
  } catch {
    return NextResponse.json({ error: "expected multipart/form-data" }, { status: 400 });
  }

  // Forward the raw form data (with the PDF file) straight to FastAPI
  const upstream = new FormData();
  const file = formData.get("file");
  if (!file || !(file instanceof Blob)) {
    return NextResponse.json({ error: "no file provided" }, { status: 400 });
  }
  upstream.append("file", file, (file as File).name ?? "resume.pdf");

  let res: Response;
  try {
    res = await fetch(`${API_URL}/career-twin/upload`, {
      method: "POST",
      headers: {
        "X-API-Key": API_KEY,
        "X-User-Id": userId,
        // Do NOT set Content-Type — let fetch set it with the boundary
      },
      body: upstream,
    });
  } catch {
    return NextResponse.json({ error: "API unreachable" }, { status: 503 });
  }

  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch { /* non-JSON */ }
    return NextResponse.json({ error: detail }, { status: res.status });
  }

  const data = await res.json();
  return NextResponse.json(data);
}
