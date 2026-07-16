import { proxy } from "@/lib/proxy";
export async function POST(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return proxy(`/employer/roles/${encodeURIComponent(id)}/unlocks`, { method: "POST", body: await req.text() });
}
