/**
 * Admin gate for the MVP /admin dashboard. Comma-separated ADMIN_EMAILS env
 * var (server-side only); empty list = nobody is admin — fails closed.
 */
import "server-only";
import { auth } from "@/auth";

export async function isAdmin(): Promise<boolean> {
  const session = await auth();
  const email = session?.user?.email?.trim().toLowerCase() ?? "";
  const allowed = (process.env.ADMIN_EMAILS ?? "")
    .split(",")
    .map((e) => e.trim().toLowerCase())
    .filter(Boolean);
  return Boolean(email) && allowed.includes(email);
}
