import { NextResponse } from "next/server";
import { isAdmin } from "@/lib/admin";
import { proxyAdmin } from "@/lib/proxy";

// Allow-list the worker triggers so the dynamic segment can't hit arbitrary
// /admin/* paths.
const WORKERS = new Set([
  "ingest", "match", "verify-employers", "notify", "expire-invites", "backup",
]);

export async function POST(req: Request, { params }: { params: Promise<{ worker: string }> }) {
  if (!(await isAdmin())) return NextResponse.json({ error: "not found" }, { status: 404 });
  const { worker } = await params;
  if (!WORKERS.has(worker)) return NextResponse.json({ error: "unknown worker" }, { status: 400 });
  const qs = new URL(req.url).searchParams.toString();
  return proxyAdmin(`/admin/run/${worker}${qs ? `?${qs}` : ""}`, { method: "POST" }, 30_000);
}
