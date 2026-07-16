import { proxy } from "@/lib/proxy";
export async function GET() {
  return proxy("/career-twin/recruiter-visibility");
}
export async function PATCH(req: Request) {
  return proxy("/career-twin/recruiter-visibility", { method: "PATCH", body: await req.text() });
}
