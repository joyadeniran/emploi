import { NextResponse } from "next/server";
import {
  ADMIN_COOKIE, TTL, isAllowedAdminEmail, verifyAdminPassword, signAdminToken,
} from "@/lib/admin";

// Dedicated admin login — email (must be allow-listed) + shared password. On
// success, sets a signed httpOnly cookie. Deliberately vague error so it can't
// be used to enumerate which emails are admins.
export async function POST(req: Request) {
  const { email, password } = await req.json().catch(() => ({}));
  const ok =
    typeof email === "string" &&
    typeof password === "string" &&
    isAllowedAdminEmail(email) &&
    verifyAdminPassword(password);

  if (!ok) {
    return NextResponse.json({ error: "Invalid email or password." }, { status: 401 });
  }

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
