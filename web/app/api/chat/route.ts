import { NextResponse } from "next/server";
import { ApiUnavailableError, apiFetch } from "@/lib/api";

export const maxDuration = 45;

export async function POST(req: Request) {
  const body = await req.json().catch(() => ({}));
  try {
    const data = await apiFetch<{ reply: string; profile_updates: Record<string, string> }>("/chat", {
      method: "POST",
      body: JSON.stringify({
        message: String(body.message ?? ""),
        history: Array.isArray(body.history) ? body.history.slice(-30) : [],
      }),
      // One Gemini call per turn; the default 10s abort is too tight.
      signal: AbortSignal.timeout(40_000),
    });
    return NextResponse.json(data);
  } catch (error) {
    if (error instanceof ApiUnavailableError) return NextResponse.json({ error: "api offline" }, { status: 503 });
    const err = error as Error & { status?: number };
    return NextResponse.json({ error: err.message }, { status: err.status ?? 500 });
  }
}
