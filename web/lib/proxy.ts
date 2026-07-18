/**
 * Shared route-handler proxy to the FastAPI backend (Phase 2 endpoints).
 * Same error shaping as the hand-rolled handlers elsewhere in app/api/.
 */
import { NextResponse } from "next/server";
import { ApiUnavailableError, apiFetch, publicApiFetch } from "@/lib/api";

function shape(error: unknown) {
  if (error instanceof ApiUnavailableError)
    return NextResponse.json({ error: "api offline" }, { status: 503 });
  const err = error as Error & { status?: number };
  return NextResponse.json({ error: err.message }, { status: err.status ?? 500 });
}

/** Proxy that forwards the candidate/employer session (X-User-Id). */
export async function proxy(
  path: string,
  init: RequestInit = {},
  timeoutMs = 15_000,
) {
  try {
    const data = await apiFetch<unknown>(path, { ...init, signal: AbortSignal.timeout(timeoutMs) });
    return NextResponse.json(data);
  } catch (error) {
    return shape(error);
  }
}

/**
 * Proxy for admin endpoints, which are `admin_key_auth` on the API (shared key,
 * NO X-User-Id). Admins authenticate with the admin cookie, not a NextAuth
 * session, so `apiFetch` (which asserts a session) would 401. The caller must
 * already have verified the admin cookie (isAdmin) before calling this.
 */
export async function proxyAdmin(
  path: string,
  init: RequestInit = {},
  timeoutMs = 15_000,
) {
  try {
    const data = await publicApiFetch<unknown>(path, { ...init, signal: AbortSignal.timeout(timeoutMs) });
    return NextResponse.json(data);
  } catch (error) {
    return shape(error);
  }
}
