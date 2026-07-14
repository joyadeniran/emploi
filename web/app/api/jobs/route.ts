import { NextResponse } from "next/server";
import { apiFetch, ApiUnavailableError } from "@/lib/api";

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const remote_only = searchParams.get("remote_only") === "true";
  const category = searchParams.get("category") ?? undefined;
  const q = searchParams.get("q") ?? undefined;
  const limit = Number(searchParams.get("limit") ?? 50);
  const offset = Number(searchParams.get("offset") ?? 0);

  const qs = new URLSearchParams();
  if (remote_only) qs.set("remote_only", "true");
  if (category) qs.set("category", category);
  if (q) qs.set("q", q);
  qs.set("limit", String(limit));
  qs.set("offset", String(offset));

  try {
    const data = await apiFetch<{
      jobs: unknown[];
      total: number;
      limit: number;
      offset: number;
    }>(`/jobs?${qs.toString()}`);
    return NextResponse.json(data);
  } catch (e) {
    if (e instanceof ApiUnavailableError) {
      return NextResponse.json({ error: "api offline" }, { status: 503 });
    }
    const err = e as Error & { status?: number };
    return NextResponse.json({ error: err.message }, { status: err.status ?? 500 });
  }
}
