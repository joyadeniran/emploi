import { NextResponse } from "next/server";
import { ApiUnavailableError, apiFetch } from "@/lib/api";

function shape(error: unknown) {
  if (error instanceof ApiUnavailableError) return NextResponse.json({ error: "api offline" }, { status: 503 });
  const err = error as Error & { status?: number };
  return NextResponse.json({ error: err.message }, { status: err.status ?? 500 });
}

export async function GET() {
  try {
    return NextResponse.json(
      await apiFetch<{
        email: string;
        name: string | null;
        notifications_enabled: boolean;
      }>("/user"),
    );
  } catch (error) {
    return shape(error);
  }
}

export async function PATCH(req: Request) {
  try {
    const body = await req.text();
    return NextResponse.json(
      await apiFetch("/user/notifications", { method: "PATCH", body }),
    );
  } catch (error) {
    return shape(error);
  }
}

export async function DELETE() {
  try {
    return NextResponse.json(await apiFetch<{ ok: boolean }>("/user", { method: "DELETE" }));
  } catch (error) {
    return shape(error);
  }
}
