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
 * Upsert the signed-in user's identity (email + name) into the API's `users`
 * table via POST /user/session.
 *
 * Nothing else writes that table, and a surprising amount reads it:
 *   - the employer's Applicants list joins `users` for each applicant's
 *     name/email (an empty table renders every applicant as a nameless
 *     "Applicant" with no way to contact them);
 *   - the notify worker's employer digest reads `poster_email` from `users`
 *     with NO legacy fallback, so an absent row means the poster is never
 *     told that anyone applied;
 *   - `get_employer_owner_email` (invite accept) and the digest opt-in toggle
 *     both key off it.
 *
 * So every authenticated entry point has to call this: both app layouts, and
 * the public apply route — a candidate who opens a shared /jobs/{id} link,
 * signs in, and applies never renders either layout.
 *
 * Never throws: an identity backfill must not break a page render or block an
 * application from being submitted.
 */
const SESSION_UPSERT_TTL_MS = 60_000;
const SESSION_UPSERT_MAX_TRACKED = 5_000;
const lastSessionUpsert = new Map<string, number>();

export async function ensureUserSession(): Promise<void> {
  const session = await auth();
  const user = session?.user as
    | { id?: string; email?: string | null; name?: string | null }
    | undefined;
  const userId = user?.id ?? user?.email ?? "";
  const email = user?.email ?? "";
  // The API rejects a session row without an email, and an anonymous visitor
  // has nothing to store — both are a no-op, not an error.
  if (!userId || !email) return;

  // The upsert is idempotent but this runs on every authenticated render, so
  // an unthrottled call would add a backend round-trip to every page view.
  // One write per user per minute per instance keeps `last_seen_at` useful
  // without that cost. The Map is a cache, not a lock — a cold instance just
  // writes once more than strictly needed.
  const now = Date.now();
  const previous = lastSessionUpsert.get(userId);
  if (previous !== undefined && now - previous < SESSION_UPSERT_TTL_MS) return;
  // Bound the memory a long-lived server can hold; entries are disposable.
  if (lastSessionUpsert.size >= SESSION_UPSERT_MAX_TRACKED) lastSessionUpsert.clear();
  lastSessionUpsert.set(userId, now);

  try {
    await apiFetch("/user/session", {
      method: "POST",
      // email_verified stays false: the NextAuth session does not carry the
      // provider, so we cannot substantiate the claim here. Don't assert what
      // we haven't checked.
      body: JSON.stringify({ email, name: user?.name ?? null, email_verified: false }),
      signal: AbortSignal.timeout(5_000),
    });
  } catch {
    // Drop the throttle entry so the next render retries immediately rather
    // than leaving the user without a row for a full minute.
    lastSessionUpsert.delete(userId);
  }
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
