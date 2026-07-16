import { proxy } from "@/lib/proxy";
export async function POST(req: Request) {
  return proxy("/employer/billing/checkout", { method: "POST", body: await req.text() }, 30_000);
}
