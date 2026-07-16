import { proxy } from "@/lib/proxy";
export async function GET(req: Request) {
  const status = new URL(req.url).searchParams.get("status");
  return proxy(`/employer/roles${status ? `?status=${encodeURIComponent(status)}` : ""}`);
}
export async function POST(req: Request) {
  // URL fetch or Gemini extraction — allow extra time.
  return proxy("/employer/roles", { method: "POST", body: await req.text() }, 55_000);
}
