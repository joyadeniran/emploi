/**
 * Server-side client for the Emploi API (FastAPI).
 *
 * Only ever called from server components / route handlers — the shared
 * secret must never reach the browser. The authenticated user's id is
 * asserted here from the NextAuth session.
 */
import "server-only";
import { auth } from "@/auth";
import type { JobMatch } from "@/lib/data";

const API_URL = process.env.EMPLOI_API_URL ?? "http://localhost:8000";
const API_KEY = process.env.EMPLOI_API_KEY ?? "";

/** When true, API routes return hardcoded demo data without hitting the real API. */
export const DEMO_MODE = process.env.DEMO_MODE === "true";

export class ApiUnavailableError extends Error {}

export interface ApiMatch {
  id: number;
  job_id: number;
  title?: string | null;
  company_name?: string | null;
  description?: string | null;
  location?: string | null;
  is_remote?: number | boolean | null;
  salary_text?: string | null;
  apply_url?: string | null;
  fit_score?: number | null;
  reason?: string | null;
}

const COMPANY_COLORS = ["#04114d", "#5b4ffd", "#f79009", "#0e9f6e", "#1570ef", "#d92d20"];

function stableNumber(value: string): number {
  let result = 0;
  for (let i = 0; i < value.length; i += 1) result = (result << 5) - result + value.charCodeAt(i);
  return Math.abs(result);
}

/** Convert the database/API shape into the presentation-only match-card shape. */
export function toMatchCard(row: ApiMatch): JobMatch {
  const company = row.company_name?.trim() || "Unknown company";
  const fit = Math.max(0, Math.min(100, Number(row.fit_score) || 0));
  const remote = Boolean(row.is_remote);
  return {
    id: String(row.id), jobId: Number(row.job_id), applyUrl: row.apply_url || undefined,
    description: row.description || undefined,
    title: row.title?.trim() || "Untitled role", company,
    companyInitial: (company[0] || "?").toUpperCase(),
    companyColor: COMPANY_COLORS[stableNumber(company) % COMPANY_COLORS.length],
    location: row.location?.trim() || (remote ? "Remote" : "Location not listed"),
    workMode: remote ? "Remote" : "On-site", employment: "Employment type not listed",
    salary: row.salary_text?.trim() || "Salary not listed", fit,
    level: fit >= 85 ? "great" : fit >= 60 ? "good" : "fair",
    reason: row.reason?.trim() || "Your Career Twin found a relevant overlap to review.",
    // Never claim verification until a trust record has actually been joined.
    verified: false, isNew: true,
  };
}

export interface ApiJob {
  id: number;
  title?: string | null;
  company_name?: string | null;
  description?: string | null;
  location?: string | null;
  is_remote?: number | boolean | null;
  salary_text?: string | null;
  apply_url?: string | null;
  category?: string | null;
}

/** Convert a raw ingested-job row (no fit score yet) into the card shape. */
export function toJobCard(row: ApiJob): JobMatch {
  return toMatchCard({ ...row, job_id: row.id, fit_score: null, reason: null });
}

export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const session = await auth();
  const userId =
    (session?.user as { id?: string } | undefined)?.id ?? session?.user?.email;
  if (!userId) {
    const err = new Error("not authenticated") as Error & { status?: number };
    err.status = 401;
    throw err;
  }

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
      // A hung backend must not hang the server render with it. Long AI calls
      // (extract/upload) go through their route handlers' own fetches, not this.
      signal: init.signal ?? AbortSignal.timeout(10_000),
    });
  } catch {
    // network refusal and timeout both mean "backend not answering right now"
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

/**
 * Fetch a PUBLIC API endpoint — no session required. For the public job pages
 * (/public/roles/{id}), which anyone on the internet can view. Sends the shared
 * secret (server-side only) but never asserts a user. Throws with a `.status`
 * so a caller can distinguish 404 from a soft error.
 */
export async function publicApiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", "X-API-Key": API_KEY, ...init.headers },
      cache: "no-store",
      signal: init.signal ?? AbortSignal.timeout(10_000),
    });
  } catch {
    throw new ApiUnavailableError(`Emploi API unreachable at ${API_URL}`);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch { /* non-JSON */ }
    const err = new Error(detail) as Error & { status?: number };
    err.status = res.status;
    throw err;
  }
  return res.json() as Promise<T>;
}

/**
 * Same auth/error posture as apiFetch, but hands back the raw Response so a
 * caller can stream a binary body (document exports). apiFetch always parses
 * JSON, which would corrupt a PDF/DOCX.
 */
export async function apiFetchRaw(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const session = await auth();
  const userId =
    (session?.user as { id?: string } | undefined)?.id ?? session?.user?.email;
  if (!userId) {
    const err = new Error("not authenticated") as Error & { status?: number };
    err.status = 401;
    throw err;
  }

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
      signal: init.signal ?? AbortSignal.timeout(30_000),
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
  return res;
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
