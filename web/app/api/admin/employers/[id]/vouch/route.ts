import { NextResponse } from "next/server";
import { isAdmin } from "@/lib/admin";
import { proxy } from "@/lib/proxy";
export async function POST(req: Request, { params }: { params: Promise<{ id: string }> }) {
  if (!(await isAdmin())) return NextResponse.json({ error: "not found" }, { status: 404 });
  const { id } = await params;
  const body = await req.text();
  return proxy(`/admin/employers/${encodeURIComponent(id)}/vouch`, { method: "POST", body: body || "{}" });
}
