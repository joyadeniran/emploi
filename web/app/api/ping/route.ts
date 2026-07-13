import { NextResponse } from "next/server";

const API_URL = process.env.EMPLOI_API_URL ?? "http://localhost:8000";
const API_KEY = process.env.EMPLOI_API_KEY ?? "";

// Lightweight wakeup probe — pings the Render API's /health endpoint so it
// warms up before the user reaches the CV upload step. Returns 200 regardless
// of the backend state so the client never retries.
export async function GET() {
  try {
    await fetch(`${API_URL}/health`, {
      headers: { "x-api-key": API_KEY },
      signal: AbortSignal.timeout(30_000),
    });
  } catch {
    // Render is still sleeping or offline — the real upload will wait. That's
    // fine; this ping is best-effort only.
  }
  return NextResponse.json({ ok: true });
}
