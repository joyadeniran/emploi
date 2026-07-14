import { NextResponse } from "next/server";
import { apiFetch, ApiUnavailableError } from "@/lib/api";

export async function GET() {
  try {
    const data = await apiFetch<{ saved: unknown[] }>("/saved-jobs");
    return NextResponse.json(data);
  } catch (e) {
    if (e instanceof ApiUnavailableError) return NextResponse.json({ error: "api offline" }, { status: 503 });
    const err = e as Error & { status?: number };
    return NextResponse.json({ error: err.message }, { status: err.status ?? 500 });
  }
}
