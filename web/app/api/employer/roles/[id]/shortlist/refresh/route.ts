import { proxy } from "@/lib/proxy";
export async function POST(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const body = await req.text();
  return proxy(`/employer/roles/${encodeURIComponent(id)}/shortlist/refresh`, { method: "POST", body: body || "{}" });
}
