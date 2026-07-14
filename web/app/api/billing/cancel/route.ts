import { NextResponse } from "next/server";
import { ApiUnavailableError, apiFetch } from "@/lib/api";

export async function POST() {
  try {
    const data = await apiFetch<{ ok: boolean }>("/billing/cancel", { method: "POST", body: "{}" });
    return NextResponse.json(data);
  } catch (e) {
    if (e instanceof ApiUnavailableError) return NextResponse.json({ error: "api offline" }, { status: 503 });
    const err = e as Error & { status?: number };
    return NextResponse.json({ error: err.message }, { status: err.status ?? 500 });
  }
}
