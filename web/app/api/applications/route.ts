import { NextResponse } from "next/server";
import { apiFetch, ApiUnavailableError } from "@/lib/api";

export async function GET() {
  try {
    const data = await apiFetch<{ applications: unknown[] }>("/applications");
    return NextResponse.json(data);
  } catch (e) {
    if (e instanceof ApiUnavailableError) {
      return NextResponse.json({ error: "api offline" }, { status: 503 });
    }
    const err = e as Error & { status?: number };
    return NextResponse.json({ error: err.message }, { status: err.status ?? 500 });
  }
}

export async function POST(req: Request) {
  const body = await req.json().catch(() => ({}));
  try {
    const data = await apiFetch<{ id: number }>("/applications", {
      method: "POST",
      body: JSON.stringify({
        company: String(body.company ?? ""),
        role: String(body.role ?? ""),
        status: String(body.status ?? "applied"),
        extra: body.extra ?? {},
      }),
    });
    return NextResponse.json(data, { status: 201 });
  } catch (e) {
    if (e instanceof ApiUnavailableError) {
      return NextResponse.json({ error: "api offline" }, { status: 503 });
    }
    const err = e as Error & { status?: number };
    return NextResponse.json({ error: err.message }, { status: err.status ?? 500 });
  }
}
