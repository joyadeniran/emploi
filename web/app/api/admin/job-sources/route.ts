import { NextResponse } from "next/server";
import { isAdmin } from "@/lib/admin";
import { proxyAdmin } from "@/lib/proxy";

export async function GET(req: Request) {
  if (!(await isAdmin())) return NextResponse.json({ error: "not found" }, { status: 404 });
  const qs = new URL(req.url).searchParams.toString();
  return proxyAdmin(`/admin/job-sources${qs ? `?${qs}` : ""}`);
}

export async function POST(req: Request) {
  if (!(await isAdmin())) return NextResponse.json({ error: "not found" }, { status: 404 });
  const body = await req.text();
  return proxyAdmin("/admin/job-sources", { method: "POST", body: body || "{}" });
}
