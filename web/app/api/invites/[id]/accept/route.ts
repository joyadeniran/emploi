import { proxy } from "@/lib/proxy";
export async function POST(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return proxy(`/invites/${encodeURIComponent(id)}/accept`, { method: "POST" });
}
