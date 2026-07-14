import { NextResponse } from "next/server";
import { ApiUnavailableError, apiFetch } from "@/lib/api";

export async function POST(req: Request) {
  const body = await req.json().catch(() => ({}));
  try {
    const data = await apiFetch<{ authorization_url: string; reference: string }>(
      "/billing/checkout",
      { method: "POST", body: JSON.stringify({ tier: body.tier }) },
    );
    return NextResponse.json(data);
  } catch (e) {
    if (e instanceof ApiUnavailableError) return NextResponse.json({ error: "api offline" }, { status: 503 });
    const err = e as Error & { status?: number };
    return NextResponse.json({ error: err.message }, { status: err.status ?? 500 });
  }
}
