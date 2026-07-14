import { NextResponse } from "next/server";
import { ApiUnavailableError, apiFetch } from "@/lib/api";

export async function GET() {
  try {
    const data = await apiFetch<{
      tier: string; status: string; current_period_end: string | null;
      used_this_month: number; limit: number; prices_ngn: Record<string, number>;
    }>("/billing/status");
    return NextResponse.json(data);
  } catch (e) {
    if (e instanceof ApiUnavailableError) return NextResponse.json({ error: "api offline" }, { status: 503 });
    const err = e as Error & { status?: number };
    return NextResponse.json({ error: err.message }, { status: err.status ?? 500 });
  }
}
