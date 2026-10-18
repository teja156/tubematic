// @vitest-environment node
/**
 * POST /api/auth/login and /api/auth/logout (TMDEV-152).
 *
 *  1. The password goes to Flask with the API token; only a 200 sets a cookie
 *  2. Wrong password (401) and the backoff (429 + Retry-After) pass through
 *  3. Flask refusing the dashboard's TOKEN is a 502, not "wrong password"
 *  4. Logout clears the cookie
 *  5. Both refuse a request from another origin (Sec-Fetch-Site) with 403 and
 *     a non-JSON body with 415, before Flask is called (TMDEV-156)
 */
import { mkdtempSync, rmSync, writeFileSync } from "fs";
import { tmpdir } from "os";
import path from "path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { POST as login } from "@/app/api/auth/login/route";
import { POST as logout } from "@/app/api/auth/logout/route";
import { verifySession } from "@/lib/session";
import { SESSION_COOKIE } from "@/lib/sessionCookie";

let dir: string;

beforeEach(() => {
  dir = mkdtempSync(path.join(tmpdir(), "tm-secrets-"));
  writeFileSync(path.join(dir, "session_secret"), "secret-0123456789abcdef");
  writeFileSync(path.join(dir, "api_token"), "api-token-xyz");
  process.env.TUBEMATIC_SECRETS_DIR = dir;
});

afterEach(() => {
  vi.restoreAllMocks();
  rmSync(dir, { recursive: true, force: true });
  delete process.env.TUBEMATIC_SECRETS_DIR;
});

function req(body: unknown, headers: Record<string, string> = {}) {
  return new NextRequest("http://localhost:3000/api/auth/login", {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json", ...headers },
  });
}

function upstream(status: number, body: unknown, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), { status, headers });
}

describe("login", () => {
  it("checks the password with Flask using the API token, then sets the cookie", async () => {
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(upstream(200, { ok: true }));
    const res = await login(req({ password: "pw pw pw pw pw" }));
    expect(res.status).toBe(200);
    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toMatch(/\/auth\/login$/);
    expect((init as RequestInit).headers).toMatchObject({ Authorization: "Bearer api-token-xyz" });
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({ password: "pw pw pw pw pw" });
    const cookie = res.cookies.get(SESSION_COOKIE);
    expect(cookie?.httpOnly).toBe(true);
    expect(cookie?.sameSite).toBe("strict");
    expect(cookie?.secure).toBe(false);
    expect(await verifySession(cookie?.value)).toBe(true);
  });

  it("marks the cookie Secure behind an HTTPS reverse proxy", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(upstream(200, { ok: true }));
    const res = await login(req({ password: "pw" }, { "x-forwarded-proto": "https" }));
    expect(res.cookies.get(SESSION_COOKIE)?.secure).toBe(true);
  });

  it("passes a wrong password through as 401 with no cookie", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(upstream(401, { error: "wrong password" }));
    const res = await login(req({ password: "nope" }));
    expect(res.status).toBe(401);
    expect(res.cookies.get(SESSION_COOKIE)).toBeUndefined();
  });

  it("passes the backoff through with its Retry-After", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      upstream(429, { error: "too many failed logins" }, { "Retry-After": "32" }));
    const res = await login(req({ password: "nope" }));
    expect(res.status).toBe(429);
    expect(res.headers.get("Retry-After")).toBe("32");
  });

  it("reports a refused dashboard token as a 502, not a wrong password", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(upstream(401, { error: "unauthorized" }));
    const res = await login(req({ password: "pw" }));
    expect(res.status).toBe(502);
    expect((await res.json()).error).toContain("docker compose restart");
  });

  it("refuses an empty body without calling Flask", async () => {
    const fetchSpy = vi.spyOn(global, "fetch");
    expect((await login(req({}))).status).toBe(400);
    expect((await login(req({ password: 5 }))).status).toBe(400);
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

describe("logout", () => {
  it("clears the cookie", async () => {
    const res = await logout(new NextRequest("http://localhost:3000/api/auth/logout", { method: "POST" }));
    const cookie = res.cookies.get(SESSION_COOKIE);
    expect(cookie?.value).toBe("");
    expect(cookie?.maxAge).toBe(0);
  });
});

describe("cross-site and non-JSON requests (TMDEV-156)", () => {
  for (const site of ["same-site", "cross-site"]) {
    it(`login refuses Sec-Fetch-Site: ${site} with 403 and never calls Flask`, async () => {
      const fetchSpy = vi.spyOn(global, "fetch");
      const res = await login(req({ password: "pw" }, { "Sec-Fetch-Site": site }));
      expect(res.status).toBe(403);
      expect(res.cookies.get(SESSION_COOKIE)).toBeUndefined();
      expect(fetchSpy).not.toHaveBeenCalled();
    });
  }

  it("login passes a same-origin request and one with no Sec-Fetch-Site", async () => {
    vi.spyOn(global, "fetch").mockImplementation(async () => upstream(200, { ok: true }));
    expect((await login(req({ password: "pw" }, { "Sec-Fetch-Site": "same-origin" }))).status).toBe(200);
    expect((await login(req({ password: "pw" }))).status).toBe(200);
  });

  it("login refuses a text/plain body with 415 and never calls Flask", async () => {
    const fetchSpy = vi.spyOn(global, "fetch");
    const res = await login(req({ password: "pw" }, { "Content-Type": "text/plain" }));
    expect(res.status).toBe(415);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("logout refuses a same-site request with 403 and leaves the cookie alone", async () => {
    const res = await logout(new NextRequest("http://localhost:3000/api/auth/logout", {
      method: "POST", headers: { "Sec-Fetch-Site": "same-site" },
    }));
    expect(res.status).toBe(403);
    expect(res.cookies.get(SESSION_COOKIE)).toBeUndefined();
  });

  it("logout refuses an empty form post with 415", async () => {
    const res = await logout(new NextRequest("http://localhost:3000/api/auth/logout", {
      method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: "",
    }));
    expect(res.status).toBe(415);
  });

  it("logout passes the dashboard's own bodiless same-origin POST", async () => {
    const res = await logout(new NextRequest("http://localhost:3000/api/auth/logout", {
      method: "POST", headers: { "Sec-Fetch-Site": "same-origin" },
    }));
    expect(res.status).toBe(200);
    expect(res.cookies.get(SESSION_COOKIE)?.maxAge).toBe(0);
  });
});
