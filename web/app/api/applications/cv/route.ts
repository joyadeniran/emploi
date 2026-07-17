import { NextResponse } from "next/server";
import { ApiUnavailableError, apiFetch } from "@/lib/api";

// Submission only — returns {job_id, status:"pending"} immediately. A tailored
// CV is one Gemini call, but it goes through the same async job + poll path as
// /applications/generate so a slow provider can't blow past Render's ~100s
// proxy limit. Poll /api/applications/generate/[jobId] for the result.
export async function POST(req: Request) {
  const body = await req.json().catch(() => ({}));
  try {
    const data = await apiFetch<{ job_id: string; status: string }>("/applications/cv", {
      method: "POST",
      body: JSON.stringify({ job: body.job ?? {} }),
    });
    return NextResponse.json(data, { status: 202 });
  } catch (error) {
    if (error instanceof ApiUnavailableError) return NextResponse.json({ error: "api offline" }, { status: 503 });
    const err = error as Error & { status?: number };
    return NextResponse.json({ error: err.message }, { status: err.status ?? 500 });
  }
}
