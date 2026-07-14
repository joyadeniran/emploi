import { NextResponse } from "next/server";
import { apiFetch, ApiUnavailableError } from "@/lib/api";

type Params = { params: Promise<{ jobId: string }> };

async function forward(method: "PUT" | "DELETE", jobId: string) {
  const id = Number(jobId);
  if (!Number.isInteger(id) || id < 1) {
    return NextResponse.json({ error: "invalid job id" }, { status: 422 });
  }
  try {
    const data = await apiFetch<{ ok: boolean; saved: boolean }>(`/saved-jobs/${id}`, { method });
    return NextResponse.json(data);
  } catch (e) {
    if (e instanceof ApiUnavailableError) return NextResponse.json({ error: "api offline" }, { status: 503 });
    const err = e as Error & { status?: number };
    return NextResponse.json({ error: err.message }, { status: err.status ?? 500 });
  }
}

export async function PUT(_req: Request, { params }: Params) {
  return forward("PUT", (await params).jobId);
}

export async function DELETE(_req: Request, { params }: Params) {
  return forward("DELETE", (await params).jobId);
}
