import { NextResponse } from "next/server";
import { ApiUnavailableError, apiFetch } from "@/lib/api";

export const maxDuration = 60;

export async function POST(req: Request) {
  const body = await req.json().catch(() => ({}));
  try {
    const data = await apiFetch<{ generated: unknown }>("/applications/generate", {
      method: "POST",
      body: JSON.stringify({ job: body.job ?? {}, include_review: body.include_review !== false }),
    });
    return NextResponse.json(data);
  } catch (error) {
    if (error instanceof ApiUnavailableError) return NextResponse.json({ error: "api offline" }, { status: 503 });
    const err = error as Error & { status?: number };
    return NextResponse.json({ error: err.message }, { status: err.status ?? 500 });
  }
}
