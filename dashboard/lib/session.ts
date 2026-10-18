/**
 * The dashboard's login session and the API token (TMDEV-152). Server-only:
 * it reads the secret files Compose mounts at /run/secrets.
 *
 * The session is an HS256 JWT in an HttpOnly cookie, signed with
 * `session_secret`. Both secrets are read on every call rather than cached:
 * `onboard.py --set-password` rotates `session_secret` to sign every browser
 * out, and `--rotate-tokens` replaces the API token, and neither should need
 * the container restarted to take effect. A missing or unreadable secret
 * means no session is valid -- the check fails closed.
 */
import { readFileSync } from "fs";
import path from "path";
import { SignJWT, jwtVerify } from "jose";
import { SESSION_COOKIE, SESSION_MAX_AGE_S } from "@/lib/sessionCookie";

const SUBJECT = "admin";

export function readSecret(name: "api_token" | "session_secret"): string {
  const dir = process.env.TUBEMATIC_SECRETS_DIR ?? "/run/secrets";
  const value = readFileSync(path.join(dir, name), "utf8").trim();
  if (!value) throw new Error(`${name} is empty`);
  return value;
}

function signingKey(): Uint8Array {
  return new TextEncoder().encode(readSecret("session_secret"));
}

export async function createSession(): Promise<string> {
  return new SignJWT({})
    .setProtectedHeader({ alg: "HS256" })
    .setSubject(SUBJECT)
    .setIssuedAt()
    .setExpirationTime(`${SESSION_MAX_AGE_S}s`)
    .sign(signingKey());
}

export async function verifySession(token: string | undefined): Promise<boolean> {
  if (!token) return false;
  try {
    await jwtVerify(token, signingKey(), { algorithms: ["HS256"], subject: SUBJECT });
    return true;
  } catch {
    return false;
  }
}

type CookieReader = { cookies: { get(name: string): { value: string } | undefined } };

export async function isAuthenticated(req: CookieReader): Promise<boolean> {
  return verifySession(req.cookies.get(SESSION_COOKIE)?.value);
}

/** The bearer token every request to the Flask API must carry. */
export function apiToken(): string {
  return readSecret("api_token");
}

type HeaderReader = { headers: { get(name: string): string | null }; nextUrl?: { protocol?: string } };

/**
 * `Secure` only when the browser reached us over HTTPS. A reverse proxy that
 * terminates TLS says so in X-Forwarded-Proto; plain http on localhost or a LAN
 * must still be able to log in, which a Secure cookie would prevent.
 */
export function isHttps(req: HeaderReader): boolean {
  const forwarded = req.headers.get("x-forwarded-proto")?.split(",")[0]?.trim().toLowerCase();
  return forwarded === "https" || req.nextUrl?.protocol === "https:";
}

export function sessionCookie(value: string, secure: boolean, maxAge = SESSION_MAX_AGE_S) {
  return {
    name: SESSION_COOKIE,
    value,
    httpOnly: true,
    sameSite: "strict" as const,
    secure,
    path: "/",
    maxAge,
  };
}
