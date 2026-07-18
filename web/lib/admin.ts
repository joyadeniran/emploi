/**
 * Admin auth — a DEDICATED portal, separate from the candidate Google/NextAuth
 * session. Login is email (must be in ADMIN_EMAILS) + a shared password
 * (ADMIN_PASSWORD), which mints a signed, httpOnly cookie. No Google, no career
 * twin. `isAdmin()` (used by the /api/admin/* routes) now checks that cookie.
 */
import "server-only";
import crypto from "crypto";
import { cookies } from "next/headers";

export const ADMIN_COOKIE = "emploi_admin";
const TTL_SECONDS = 12 * 60 * 60; // 12h

function secret(): string {
  // AUTH_SECRET already exists in prod; fall back so a missing secret fails
  // closed (empty secret → every token verification fails).
  return process.env.AUTH_SECRET || process.env.EMPLOI_API_KEY || "";
}

export function adminEmails(): string[] {
  return (process.env.ADMIN_EMAILS ?? "")
    .split(",")
    .map((e) => e.trim().toLowerCase())
    .filter(Boolean);
}

export function isAllowedAdminEmail(email: string): boolean {
  return adminEmails().includes(email.trim().toLowerCase());
}

/** Constant-time password check against ADMIN_PASSWORD. Empty env → always false. */
export function verifyAdminPassword(password: string): boolean {
  const expected = process.env.ADMIN_PASSWORD ?? "";
  if (!expected || !password) return false;
  const a = Buffer.from(password);
  const b = Buffer.from(expected);
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}

export function signAdminToken(email: string): string {
  const payload = Buffer.from(
    JSON.stringify({ email: email.toLowerCase(), exp: Date.now() + TTL_SECONDS * 1000 }),
  ).toString("base64url");
  const sig = crypto.createHmac("sha256", secret()).update(payload).digest("base64url");
  return `${payload}.${sig}`;
}

export function verifyAdminToken(token?: string): string | null {
  if (!token || !secret()) return null;
  const [payload, sig] = token.split(".");
  if (!payload || !sig) return null;
  const expected = crypto.createHmac("sha256", secret()).update(payload).digest("base64url");
  const sigBuf = Buffer.from(sig);
  const expBuf = Buffer.from(expected);
  if (sigBuf.length !== expBuf.length || !crypto.timingSafeEqual(sigBuf, expBuf)) return null;
  try {
    const { email, exp } = JSON.parse(Buffer.from(payload, "base64url").toString());
    if (!email || !exp || Date.now() > exp) return null;
    // Re-check the allow-list on every request: removing an email from
    // ADMIN_EMAILS revokes any live session immediately.
    if (!isAllowedAdminEmail(email)) return null;
    return email as string;
  } catch {
    return null;
  }
}

/** The signed-in admin's email, or null. Reads the admin cookie only. */
export async function getAdminEmail(): Promise<string | null> {
  const store = await cookies();
  return verifyAdminToken(store.get(ADMIN_COOKIE)?.value);
}

export async function isAdmin(): Promise<boolean> {
  return (await getAdminEmail()) !== null;
}

export const TTL = TTL_SECONDS;
