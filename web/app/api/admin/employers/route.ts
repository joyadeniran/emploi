import { NextResponse } from "next/server";
import { isAdmin } from "@/lib/admin";
import { proxy } from "@/lib/proxy";

export async function GET() {
  if (!(await isAdmin())) return NextResponse.json({ error: "not found" }, { status: 404 });
  return proxy("/admin/employers");
}
