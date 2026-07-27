import { NextResponse } from "next/server";
import { ApiUnavailableError, apiFetch } from "@/lib/api";

// Employer triage of an inbound applicant's status ('reviewed' | 'rejected').
// apiFetch asserts the session and forwards X-User-Id; ownership + validation
// are enforced by the API.
export async function PATCH(
  req: Request,
  { params }: { params: Promise<{ id: string; candidate: string }> },
) {
  const { id, candidate } = await params;
  let body: unknown = {};
  try {
    body = await req.json();
  } catch {
    /* empty body -> API returns 422 */
  }
  try {
    const data = await apiFetch(
      `/employer/roles/${encodeURIComponent(id)}/applicants/${encodeURIComponent(candidate)}`,
      { method: "PATCH", body: JSON.stringify(body) },
    );
    return NextResponse.json(data);
  } catch (error) {
    if (error instanceof ApiUnavailableError)
      return NextResponse.json({ error: "api offline" }, { status: 503 });
    const err = error as Error & { status?: number };
    return NextResponse.json({ error: err.message }, { status: err.status ?? 500 });
  }
}
