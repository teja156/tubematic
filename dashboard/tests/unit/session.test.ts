// @vitest-environment node
/**
 * lib/session.ts and lib/sessionCookie.ts (TMDEV-152).
 *
 *  1. A session signed with session_secret verifies; anything else does not
 *  2. Rotating session_secret (what --set-password does) signs every browser out
 *  3. A missing secret fails closed, never open
 *  4. The cookie is HttpOnly + SameSite=Strict, Secure only behind HTTPS
 *  5. The post-login redirect is same-site only (no open redirect)
 */
import { mkdtempSync, rmSync, writeFileSync } from "fs";
import { tmpdir } from "os";
import path from "path";
import { SignJWT } from "jose";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  apiToken, createSession, isAuthenticated, isHttps, sessionCookie, verifySession,
} from "@/lib/session";
import { SESSION_COOKIE, SESSION_MAX_AGE_S, safeNext } from "@/lib/sessionCookie";

let dir: string;

beforeEach(() => {
  dir = mkdtempSync(path.join(tmpdir(), "tm-secrets-"));
  writeFileSync(path.join(dir, "session_secret"), "first-secret-0123456789abcdef\n");
  writeFileSync(path.join(dir, "api_token"), "api-token-xyz\n");
  process.env.TUBEMATIC_SECRETS_DIR = dir;
});

afterEach(() => {
  rmSync(dir, { recursive: true, force: true });
  delete process.env.TUBEMATIC_SECRETS_DIR;
});

const cookies = (value?: string) => ({
  cookies: { get: (n: string) => (n === SESSION_COOKIE && value ? { value } : undefined) },
});

describe("sessions", () => {
  it("verifies a session it created", async () => {
    expect(await verifySession(await createSession())).toBe(true);
    expect(await isAuthenticated(cookies(await createSession()))).toBe(true);
  });

  it("refuses no cookie, garbage, and a token signed with another key", async () => {
    expect(await isAuthenticated(cookies())).toBe(false);
    expect(await verifySession("not.a.jwt")).toBe(false);
    const forged = await new SignJWT({}).setProtectedHeader({ alg: "HS256" }).setSubject("admin")
      .setExpirationTime("1h").sign(new TextEncoder().encode("some-other-key"));
    expect(await verifySession(forged)).toBe(false);
  });

  it("refuses an expired session", async () => {
    const key = new TextEncoder().encode("first-secret-0123456789abcdef");
    const old = await new SignJWT({}).setProtectedHeader({ alg: "HS256" }).setSubject("admin")
      .setIssuedAt(1).setExpirationTime(2).sign(key);
    expect(await verifySession(old)).toBe(false);
  });

  it("refuses alg=none", async () => {
    const header = Buffer.from(JSON.stringify({ alg: "none" })).toString("base64url");
    const payload = Buffer.from(JSON.stringify({ sub: "admin", exp: 9999999999 })).toString("base64url");
    expect(await verifySession(`${header}.${payload}.`)).toBe(false);
  });

  it("signs every browser out when session_secret is rotated", async () => {
    const token = await createSession();
    writeFileSync(path.join(dir, "session_secret"), "second-secret-0123456789abcdef");
    expect(await verifySession(token)).toBe(false);
  });

  it("fails closed when session_secret is missing", async () => {
    const token = await createSession();
    rmSync(path.join(dir, "session_secret"));
    expect(await verifySession(token)).toBe(false);
    await expect(createSession()).rejects.toThrow();
  });

  it("lasts seven days", async () => {
    const payload = JSON.parse(Buffer.from((await createSession()).split(".")[1], "base64url").toString());
    expect(payload.exp - payload.iat).toBe(SESSION_MAX_AGE_S);
    expect(SESSION_MAX_AGE_S).toBe(7 * 24 * 60 * 60);
  });

  it("reads the API token fresh, so a rotation needs no restart", () => {
    expect(apiToken()).toBe("api-token-xyz");
    writeFileSync(path.join(dir, "api_token"), "rotated");
    expect(apiToken()).toBe("rotated");
  });
});

describe("the cookie", () => {
  const req = (proto: string | null, protocol = "http:") => ({
    headers: { get: (h: string) => (h === "x-forwarded-proto" ? proto : null) },
    nextUrl: { protocol },
  });

  it("is HttpOnly and SameSite=Strict on every path", () => {
    expect(sessionCookie("v", false)).toMatchObject({
      name: SESSION_COOKIE, httpOnly: true, sameSite: "strict", path: "/", maxAge: SESSION_MAX_AGE_S,
    });
  });

  it("is Secure only when the browser came over HTTPS", () => {
    expect(isHttps(req(null))).toBe(false);
    expect(isHttps(req("https"))).toBe(true);
    expect(isHttps(req("https, http"))).toBe(true);
    expect(isHttps(req("http"))).toBe(false);
    expect(isHttps(req(null, "https:"))).toBe(true);
  });
});

describe("safeNext", () => {
  it.each([
    ["/settings", "/settings"],
    ["/library?x=1", "/library?x=1"],
    [null, "/"],
    ["", "/"],
    ["https://evil.example/", "/"],
    ["//evil.example/", "/"],
    ["/\\evil.example", "/"],
    ["/login", "/"],
    ["/login?next=/x", "/"],
  ])("%s → %s", (input, expected) => {
    expect(safeNext(input as string | null)).toBe(expected);
  });
});
