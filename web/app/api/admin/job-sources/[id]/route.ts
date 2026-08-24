import { NextResponse } from "next/server";
import { isAdmin } from "@/lib/admin";
import { proxyAdmin } from "@/lib/proxy";

async function sourcePath(params: Promise<{ id: string }>) {
  const { id } = await params;
  return `/admin/job-sources/${encodeURIComponent(id)}`;
}

export async function PATCH(req: Request, { params }: { params: Promise<{ id: string }> }) {
  if (!(await isAdmin())) return NextResponse.json({ error: "not found" }, { status: 404 });
  return proxyAdmin(await sourcePath(params), { method: "PATCH", body: (await req.text()) || "{}" });
}

export async function DELETE(_: Request, { params }: { params: Promise<{ id: string }> }) {
  if (!(await isAdmin())) return NextResponse.json({ error: "not found" }, { status: 404 });
  return proxyAdmin(await sourcePath(params), { method: "DELETE" });
}
