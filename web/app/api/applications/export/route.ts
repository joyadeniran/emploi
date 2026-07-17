import { NextResponse } from "next/server";
import { ApiUnavailableError, apiFetchRaw } from "@/lib/api";

// Renders generated text into a real .pdf / .docx. Streams the binary body
// straight through — no model call, nothing persisted. Callers must send only
// exportable sections (cover letter / CV); the fit evaluation is screen-only
// because it contains the candidate's own gap analysis.
export async function POST(req: Request) {
  const body = await req.json().catch(() => ({}));
  try {
    const upstream = await apiFetchRaw("/applications/export", {
      method: "POST",
      body: JSON.stringify({
        text: body.text ?? "",
        format: body.format ?? "pdf",
        title: body.title ?? "Application",
      }),
    });
    return new NextResponse(upstream.body, {
      status: 200,
      headers: {
        "Content-Type": upstream.headers.get("content-type") ?? "application/octet-stream",
        "Content-Disposition": upstream.headers.get("content-disposition") ?? "attachment",
      },
    });
  } catch (error) {
    if (error instanceof ApiUnavailableError) return NextResponse.json({ error: "api offline" }, { status: 503 });
    const err = error as Error & { status?: number };
    return NextResponse.json({ error: err.message }, { status: err.status ?? 500 });
  }
}
