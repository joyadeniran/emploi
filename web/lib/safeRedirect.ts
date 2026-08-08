/**
 * Sanitise a `?callbackUrl=` before it reaches `redirect()` / NextAuth's
 * `redirectTo`.
 *
 * A bare `startsWith("/")` test is not enough: `//evil.com` and `/\evil.com`
 * both start with a slash and both are treated by browsers as PROTOCOL-RELATIVE
 * absolute URLs, so they send the visitor off-site. That turns the sign-in page
 * into an open redirect — a phishing primitive, since the link genuinely
 * originates from app.emploihq.com and carries a real login flow.
 *
 * Only a single-slash, same-site path is honoured; anything else falls back to
 * the caller's default landing page.
 */
export function safeCallbackPath(
  callbackUrl: string | undefined | null,
  fallback: string,
): string {
  if (!callbackUrl) return fallback;
  // Must be a rooted path, and must not be protocol-relative ("//host") or a
  // backslash variant ("/\host") that browsers normalise to "//host".
  if (!callbackUrl.startsWith("/")) return fallback;
  if (callbackUrl.startsWith("//") || callbackUrl.startsWith("/\\")) return fallback;
  return callbackUrl;
}
