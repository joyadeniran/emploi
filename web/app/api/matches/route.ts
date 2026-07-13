import { NextResponse } from "next/server";
import { apiFetch, ApiUnavailableError } from "@/lib/api";

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const limit = Number(searchParams.get("limit") ?? 50);

  try {
    const data = await apiFetch<{ matches: unknown[] }>(
      `/matches?limit=${limit}`,
    );
    return NextResponse.json(data);
  } catch (e) {
    if (e instanceof ApiUnavailableError) {
      return NextResponse.json({ error: "api offline" }, { status: 503 });
    }
    const err = e as Error & { status?: number };
    return NextResponse.json(
      { error: err.message },
      { status: err.status ?? 500 },
    );
  }
}
