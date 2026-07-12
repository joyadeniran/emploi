import { NextResponse } from "next/server";
import { apiFetch, ApiUnavailableError } from "@/lib/api";

export async function POST(req: Request) {
  const body = await req.json().catch(() => ({}));
  const query = String(body.query ?? "").trim();
  if (!query) {
    return NextResponse.json({ error: "empty query" }, { status: 422 });
  }

  // A query containing @ or a dot is treated as a contact/domain; otherwise
  // it's a company name only (which verify.py reports as unverified).
  const isContact = query.includes("@") || query.includes(".");
  const payload = {
    company: isContact ? String(body.company ?? "") : query,
    contact: isContact ? query : "",
    job_text: String(body.job_text ?? ""),
    role: "",
  };

  try {
    const result = await apiFetch<Record<string, unknown>>("/verify", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    return NextResponse.json(result);
  } catch (e) {
    if (e instanceof ApiUnavailableError) {
      return NextResponse.json(
        { error: "The trust engine is offline right now — try again shortly." },
        { status: 503 },
      );
    }
    const err = e as Error & { status?: number };
    return NextResponse.json(
      { error: err.message },
      { status: err.status ?? 500 },
    );
  }
}
