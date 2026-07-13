import { NextResponse } from "next/server";
import { ApiUnavailableError, apiFetch } from "@/lib/api";

export async function DELETE() {
  try {
    return NextResponse.json(await apiFetch<{ ok: boolean }>("/user", { method: "DELETE" }));
  } catch (error) {
    if (error instanceof ApiUnavailableError) return NextResponse.json({ error: "api offline" }, { status: 503 });
    const err = error as Error & { status?: number };
    return NextResponse.json({ error: err.message }, { status: err.status ?? 500 });
  }
}
