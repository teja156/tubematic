import { type NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE } from "@/lib/sessionCookie";

/**
 * Send a browser with no session cookie to /login (TMDEV-152).
 *
 * Only a presence check, deliberately: middleware runs on the Edge runtime,
 * which cannot read the secret the cookie is signed with. It is a convenience
 * redirect, not the lock. Every page fetches its data client-side through
 * /api/proxy, and that route -- like /stream -- verifies the signature itself
 * on every request, which is where Next.js's own guidance puts the real check.
 */
export function middleware(req: NextRequest) {
  if (req.cookies.get(SESSION_COOKIE)?.value) return NextResponse.next();
  const url = new URL("/login", req.url);
  const next = req.nextUrl.pathname + req.nextUrl.search;
  if (next !== "/") url.searchParams.set("next", next);
  return NextResponse.redirect(url);
}

export const config = {
  // Pages only. The API routes and /stream answer 401 themselves, and a
  // redirect there would hand a fetch() or a <video> an HTML page instead.
  matcher: ["/((?!api/|stream/|_next/|login$|.*\\..*).*)"],
};
