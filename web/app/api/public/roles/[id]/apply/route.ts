import { NextResponse } from "next/server";
import { ApiUnavailableError, apiFetch } from "@/lib/api";

// Applying is auth-gated (the sign-in funnel). apiFetch asserts the session and
// forwards X-User-Id, so an unauthenticated POST returns 401 → the client sends
// the visitor to sign in.
export async function POST(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const data = await apiFetch(`/public/roles/${encodeURIComponent(id)}/apply`, { method: "POST" });
    return NextResponse.json(data, { status: 201 });
  } catch (error) {
    if (error instanceof ApiUnavailableError) return NextResponse.json({ error: "api offline" }, { status: 503 });
    const err = error as Error & { status?: number };
    return NextResponse.json({ error: err.message }, { status: err.status ?? 500 });
  }
}
