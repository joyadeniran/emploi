import { proxy } from "@/lib/proxy";
export async function GET(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const sp = new URL(req.url).searchParams;
  const limit = sp.get("limit") ?? "20";
  const offset = sp.get("offset") ?? "0";
  // Empty cache generates synchronously (one Gemini call) — allow time.
  return proxy(`/employer/roles/${encodeURIComponent(id)}/shortlist?limit=${limit}&offset=${offset}`, {}, 55_000);
}
