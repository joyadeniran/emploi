import { NextResponse } from "next/server";
import { ApiUnavailableError, apiFetch } from "@/lib/api";

type Params = { params: Promise<{ jobId: string }> };

export async function GET(_req: Request, { params }: Params) {
  const { jobId } = await params;
  try {
    const data = await apiFetch<{ status: string; generated?: unknown; error?: string }>(
      `/applications/generate/${encodeURIComponent(jobId)}`,
    );
    return NextResponse.json(data);
  } catch (error) {
    if (error instanceof ApiUnavailableError) return NextResponse.json({ error: "api offline" }, { status: 503 });
    const err = error as Error & { status?: number };
    return NextResponse.json({ error: err.message }, { status: err.status ?? 500 });
  }
}
