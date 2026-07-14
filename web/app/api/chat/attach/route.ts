import { NextResponse } from "next/server";
import { auth } from "@/auth";

const API_URL = process.env.EMPLOI_API_URL ?? "http://localhost:8000";
const API_KEY = process.env.EMPLOI_API_KEY ?? "";

// Classification + extraction + (for listings) matching: several Gemini calls.
export const maxDuration = 90;

export async function POST(req: Request) {
  const session = await auth();
  const userId =
    (session?.user as { id?: string } | undefined)?.id ?? session?.user?.email;
  if (!userId) {
    return NextResponse.json({ error: "not authenticated" }, { status: 401 });
  }

  let formData: FormData;
  try {
    formData = await req.formData();
  } catch {
    return NextResponse.json({ error: "expected multipart/form-data" }, { status: 400 });
  }
  const file = formData.get("file");
  if (!file || !(file instanceof Blob)) {
    return NextResponse.json({ error: "no file provided" }, { status: 400 });
  }
  const upstream = new FormData();
  upstream.append("file", file, (file as File).name ?? "document.pdf");

  let res: Response;
  try {
    res = await fetch(`${API_URL}/chat/attach`, {
      method: "POST",
      headers: { "X-API-Key": API_KEY, "X-User-Id": userId },
      body: upstream,
      signal: AbortSignal.timeout(85_000),
    });
  } catch {
    return NextResponse.json({ error: "API unreachable" }, { status: 503 });
  }
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch { /* non-JSON */ }
    return NextResponse.json({ error: detail }, { status: res.status });
  }
  return NextResponse.json(await res.json());
}
