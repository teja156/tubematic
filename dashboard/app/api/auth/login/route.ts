import { type NextRequest, NextResponse } from "next/server";
import { guardRequest } from "@/lib/requestGuard";
import { apiToken, createSession, isHttps, sessionCookie } from "@/lib/session";

const RENDERER_URL = process.env.RENDERER_URL ?? "http://localhost:4000";

export const dynamic = "force-dynamic";

/**
 * Check the password with the API, then set the session cookie (TMDEV-152).
 *
 * The password hash lives in the database, which this container cannot read,
 * so Flask's POST /auth/login does the check -- and owns the backoff after
 * repeated failures, whose 429 and Retry-After are passed straight through.
 */
export async function POST(req: NextRequest): Promise<NextResponse> {
  const noStore = { "Cache-Control": "no-store" };
  // Same-origin JSON only, so another page on this site cannot sign the
  // browser in to a session of its choosing (TMDEV-156).
  const guarded = await guardRequest(req);
  if ("refusal" in guarded) return guarded.refusal;
  let password: unknown;
  try {
    password = JSON.parse(guarded.body)?.password;
  } catch {
    password = undefined;
  }
  if (typeof password !== "string" || !password) {
    return NextResponse.json({ error: "password required" }, { status: 400, headers: noStore });
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${RENDERER_URL}/auth/login`, {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${apiToken()}` },
      body: JSON.stringify({ password }),
    });
  } catch (e) {
    return NextResponse.json(
      { error: `Upstream unreachable: ${e instanceof Error ? e.message : e}` },
      { status: 502, headers: noStore },
    );
  }

  if (!upstream.ok) {
    let body: { error?: string } = { error: `login failed (HTTP ${upstream.status})` };
    try {
      body = await upstream.json();
    } catch {
      // keep the generic message
    }
    // Flask says "unauthorized" when it refuses the dashboard's token, and
    // "wrong password" for the password. Only the second is the user's to fix.
    if (upstream.status === 401 && body.error === "unauthorized") {
      return NextResponse.json(
        { error: "The API refused the dashboard's token. Restart both so they read the same "
               + "one: docker compose restart tubematic-api tubematic-dashboard" },
        { status: 502, headers: noStore },
      );
    }
    const headers: Record<string, string> = { ...noStore };
    const retry = upstream.headers.get("Retry-After");
    if (retry) headers["Retry-After"] = retry;
    return NextResponse.json(body, { status: upstream.status, headers });
  }

  const res = NextResponse.json({ ok: true }, { headers: noStore });
  res.cookies.set(sessionCookie(await createSession(), isHttps(req)));
  return res;
}
