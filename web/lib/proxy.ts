/**
 * Shared route-handler proxy to the FastAPI backend (Phase 2 endpoints).
 * Same error shaping as the hand-rolled handlers elsewhere in app/api/.
 */
import { NextResponse } from "next/server";
import { ApiUnavailableError, apiFetch } from "@/lib/api";

export async function proxy(
  path: string,
  init: RequestInit = {},
  timeoutMs = 15_000,
) {
  try {
    const data = await apiFetch<unknown>(path, {
      ...init,
      signal: AbortSignal.timeout(timeoutMs),
    });
    return NextResponse.json(data);
  } catch (error) {
    if (error instanceof ApiUnavailableError)
      return NextResponse.json({ error: "api offline" }, { status: 503 });
    const err = error as Error & { status?: number };
    return NextResponse.json(
      { error: err.message },
      { status: err.status ?? 500 },
    );
  }
}
