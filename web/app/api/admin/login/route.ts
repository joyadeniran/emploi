import { NextResponse } from "next/server";
import {
  ADMIN_COOKIE, TTL, isAllowedAdminEmail, verifyAdminPassword, signAdminToken,
} from "@/lib/admin";

const WINDOW_MS = 15 * 60 * 1000;
const MAX_ATTEMPTS = 5;
const attempts = new Map<string, { n: number; until: number }>();

function clientKey(req: Request, email: string): string {
  const fwd = req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "unknown";
  return `${fwd}:${email.trim().toLowerCase()}`;
}

function isLocked(key: string): boolean {
  const rec = attempts.get(key);
  if (!rec) return false;
  if (Date.now() > rec.until) {
    attempts.delete(key);
    return false;
  }
  return rec.n >= MAX_ATTEMPTS;
}

function recordFailure(key: string): void {
  const now = Date.now();
  const rec = attempts.get(key);
  if (!rec || now > rec.until) {
    attempts.set(key, { n: 1, until: now + WINDOW_MS });
    return;
  }
  rec.n += 1;
}

export async function POST(req: Request) {
  if (!process.env.AUTH_SECRET && !process.env.EMPLOI_API_KEY) {
    return NextResponse.json({ error: "Invalid email or password." }, { status: 401 });
  }
  const { email, password } = await req.json().catch(() => ({}));
  const emailStr = typeof email === "string" ? email : "";
  const key = clientKey(req, emailStr);
  if (isLocked(key)) {
    return NextResponse.json({ error: "Invalid email or password." }, { status: 401 });
  }
  const ok =
    typeof email === "string" &&
    typeof password === "string" &&
    isAllowedAdminEmail(email) &&
    verifyAdminPassword(password);

  if (!ok) {
    recordFailure(key);
    return NextResponse.json({ error: "Invalid email or password." }, { status: 401 });
  }
  attempts.delete(key);

  const res = NextResponse.json({ ok: true });
  res.cookies.set(ADMIN_COOKIE, signAdminToken(email), {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: TTL,
  });
  return res;
}