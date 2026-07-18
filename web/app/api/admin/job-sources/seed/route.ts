import { NextResponse } from "next/server";
import { isAdmin } from "@/lib/admin";
import { proxyAdmin } from "@/lib/proxy";
export async function POST(req: Request) {
  if (!(await isAdmin())) return NextResponse.json({ error: "not found" }, { status: 404 });
  const sync = new URL(req.url).searchParams.get("sync") ?? "true";
  return proxyAdmin(`/admin/job-sources/seed?sync=${sync}`, { method: "POST" }, 30_000);
}
