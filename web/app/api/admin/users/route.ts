import { NextResponse } from "next/server";
import { isAdmin } from "@/lib/admin";
import { proxyAdmin } from "@/lib/proxy";

export async function GET() {
  if (!(await isAdmin())) return NextResponse.json({ error: "not found" }, { status: 404 });
  return proxyAdmin("/admin/users");
}
