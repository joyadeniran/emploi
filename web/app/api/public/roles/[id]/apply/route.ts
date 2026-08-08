import { NextResponse } from "next/server";
import { ApiUnavailableError, apiFetch, ensureUserSession } from "@/lib/api";

// Applying is auth-gated (the sign-in funnel). apiFetch asserts the session and
// forwards X-User-Id, so an unauthenticated POST returns 401 → the client sends
// the visitor to sign in.
export async function POST(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  // This is the one path where the applicant may never have rendered an app
  // layout: they opened a shared /jobs/{id} link, signed in, and applied. The
  // employer's Applicants list joins `users` for their name and email, so the
  // row has to exist before the application does or they arrive anonymous.
  await ensureUserSession();
  try {
    const data = await apiFetch(`/public/roles/${encodeURIComponent(id)}/apply`, { method: "POST" });
    return NextResponse.json(data, { status: 201 });
  } catch (error) {
    if (error instanceof ApiUnavailableError) return NextResponse.json({ error: "api offline" }, { status: 503 });
    const err = error as Error & { status?: number };
    return NextResponse.json({ error: err.message }, { status: err.status ?? 500 });
  }
}
