// @vitest-environment node
/**
 * middleware.ts (TMDEV-152): a page load with no session cookie goes to /login.
 *
 * Presence only, by design -- the signature is checked by /api/proxy and
 * /stream, which every page's data and media go through. The matcher keeps it
 * off those routes, so a fetch() or a <video> gets a 401, never an HTML page.
 */
import { describe, expect, it } from "vitest";
import { NextRequest } from "next/server";
import { config, middleware } from "@/middleware";
import { SESSION_COOKIE } from "@/lib/sessionCookie";

function page(url: string, cookie?: string) {
  return new NextRequest(url, { headers: cookie ? { cookie: `${SESSION_COOKIE}=${cookie}` } : {} });
}

describe("middleware", () => {
  it("redirects a page load without the cookie to /login, keeping where it was going", () => {
    const res = middleware(page("http://localhost:3000/settings?tab=costs"));
    expect(res.status).toBe(307);
    const to = new URL(res.headers.get("location")!);
    expect(to.pathname).toBe("/login");
    expect(to.searchParams.get("next")).toBe("/settings?tab=costs");
  });

  it("sends the root to a bare /login", () => {
    const to = new URL(middleware(page("http://localhost:3000/")).headers.get("location")!);
    expect(to.search).toBe("");
  });

  it("lets a request with the cookie through", () => {
    const res = middleware(page("http://localhost:3000/settings", "x.y.z"));
    expect(res.headers.get("location")).toBeNull();
  });

  it("matches pages, never the API, /stream, Next's assets or the login page", () => {
    const [pattern] = config.matcher;
    const re = new RegExp(`^${pattern}$`);
    for (const p of ["/", "/settings", "/library", "/new-video"]) expect(re.test(p)).toBe(true);
    for (const p of ["/api/proxy/settings", "/api/auth/login", "/stream/a.mp4", "/_next/static/x.js",
                     "/login", "/favicon.svg", "/logo-mark.svg"]) {
      expect(re.test(p)).toBe(false);
    }
  });
});
