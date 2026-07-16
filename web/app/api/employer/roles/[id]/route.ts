import { proxy } from "@/lib/proxy";
export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return proxy(`/employer/roles/${encodeURIComponent(id)}`);
}
export async function PATCH(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return proxy(`/employer/roles/${encodeURIComponent(id)}`, { method: "PATCH", body: await req.text() });
}
