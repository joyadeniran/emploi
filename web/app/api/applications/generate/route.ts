import { NextResponse } from "next/server";
import { ApiUnavailableError, apiFetch } from "@/lib/api";

// Submission only — returns {job_id, status:"pending"} immediately. The
// generation itself runs async on the API; the client polls
// /api/applications/generate/[jobId] for the result. See api/main.py: a
// reviewed draft is two sequential Gemini calls, easily slow enough to blow
// past any single request's timeout (ours or Render's own ~100s proxy).
export async function POST(req: Request) {
  const body = await req.json().catch(() => ({}));
  try {
    const data = await apiFetch<{ job_id: string; status: string }>("/applications/generate", {
      method: "POST",
      body: JSON.stringify({ job: body.job ?? {}, include_review: body.include_review !== false }),
    });
    return NextResponse.json(data, { status: 202 });
  } catch (error) {
    if (error instanceof ApiUnavailableError) return NextResponse.json({ error: "api offline" }, { status: 503 });
    const err = error as Error & { status?: number };
    return NextResponse.json({ error: err.message }, { status: err.status ?? 500 });
  }
}
