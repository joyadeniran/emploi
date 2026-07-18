import { NextResponse } from "next/server";
import { isAdmin } from "@/lib/admin";
import { proxyAdmin } from "@/lib/proxy";
export async function PATCH(req: Request, { params }: { params: Promise<{ id: string }> }) {
  if (!(await isAdmin())) return NextResponse.json({ error: "not found" }, { status: 404 });
  const { id } = await params;
  const active = new URL(req.url).searchParams.get("active") ?? "true";
  return proxyAdmin(`/admin/job-sources/${encodeURIComponent(id)}/toggle?active=${active}`, { method: "PATCH" });
}
