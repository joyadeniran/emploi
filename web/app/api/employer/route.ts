import { proxy } from "@/lib/proxy";
export async function GET() {
  return proxy("/employer");
}
export async function POST(req: Request) {
  // Onboarding: verify.py probes DNS/HTTP, allow extra time.
  return proxy("/employer/onboarding", { method: "POST", body: await req.text() }, 40_000);
}
export async function PATCH(req: Request) {
  return proxy("/employer", { method: "PATCH", body: await req.text() }, 40_000);
}
