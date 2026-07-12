import { NextResponse } from "next/server";
import { apiFetch, ApiUnavailableError, DEMO_MODE } from "@/lib/api";

export async function POST() {
  if (DEMO_MODE) {
    return NextResponse.json({ ok: true });
  }

  try {
    const data = await apiFetch<{ ok: boolean }>("/career-twin/complete", {
      method: "POST",
    });
    return NextResponse.json(data);
  } catch (e) {
    if (e instanceof ApiUnavailableError) {
      return NextResponse.json({ error: "api offline" }, { status: 503 });
    }
    const err = e as Error & { status?: number };
    return NextResponse.json({ error: err.message }, { status: err.status ?? 500 });
  }
}
