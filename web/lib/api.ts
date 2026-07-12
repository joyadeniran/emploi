/**
 * Server-side client for the Emploi API (FastAPI).
 *
 * Only ever called from server components / route handlers — the shared
 * secret must never reach the browser. The authenticated user's id is
 * asserted here from the NextAuth session.
 */
import "server-only";
import { auth } from "@/auth";

const API_URL = process.env.EMPLOI_API_URL ?? "http://localhost:8000";
const API_KEY = process.env.EMPLOI_API_KEY ?? "";

/** When true, API routes return hardcoded demo data without hitting the real API. */
export const DEMO_MODE = process.env.DEMO_MODE === "true";

export class ApiUnavailableError extends Error {}

export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const session = await auth();
  const userId =
    (session?.user as { id?: string } | undefined)?.id ?? session?.user?.email;
  if (!userId) throw new Error("not authenticated");

  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY,
        "X-User-Id": userId,
        ...init.headers,
      },
      cache: "no-store",
    });
  } catch {
    throw new ApiUnavailableError(`Emploi API unreachable at ${API_URL}`);
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    const err = new Error(detail) as Error & { status?: number };
    err.status = res.status;
    throw err;
  }
  return res.json() as Promise<T>;
}

/** True when the API answers its health check (used for demo-data fallback). */
export async function apiAvailable(): Promise<boolean> {
  try {
    const res = await fetch(`${API_URL}/health`, {
      cache: "no-store",
      signal: AbortSignal.timeout(1500),
    });
    return res.ok;
  } catch {
    return false;
  }
}
