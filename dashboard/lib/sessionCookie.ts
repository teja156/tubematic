/**
 * The login cookie's name and the post-login redirect rule (TMDEV-152).
 *
 * Kept apart from lib/session.ts because middleware.ts imports it: middleware
 * runs on the Edge runtime, which cannot read the secret files lib/session.ts
 * reads, so it may only ask whether the cookie is present.
 */
export const SESSION_COOKIE = "tm_session";

/** Seven days, fixed: a login is not extended by use. */
export const SESSION_MAX_AGE_S = 7 * 24 * 60 * 60;

/**
 * Where to go after logging in. Only a same-site path is honoured -- a `next`
 * of `//evil.example` or `https://...` would make the login page an open
 * redirect -- and anything else falls back to the pipeline.
 */
export function safeNext(next: string | null | undefined): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) {
    return "/";
  }
  if (next === "/login" || next.startsWith("/login?")) return "/";
  return next;
}
