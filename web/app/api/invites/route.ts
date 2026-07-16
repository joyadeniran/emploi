import { proxy } from "@/lib/proxy";
export async function GET(req: Request) {
  const status = new URL(req.url).searchParams.get("status") ?? "pending";
  return proxy(`/invites?status=${encodeURIComponent(status)}`);
}
