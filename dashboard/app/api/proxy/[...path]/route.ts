import { type NextRequest, NextResponse } from "next/server";
import { guardRequest } from "@/lib/requestGuard";
import { apiToken, isAuthenticated } from "@/lib/session";

const RENDERER_URL = process.env.RENDERER_URL ?? "http://localhost:4000";

// Never cache — this proxy must always reflect live DB state.
export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ path: string[] }> };

async function handler(req: NextRequest, { params }: Ctx): Promise<NextResponse> {
  // The real lock (TMDEV-152): middleware only redirects page loads, so every
  // request through here verifies the session signature itself.
  if (!(await isAuthenticated(req))) {
    return NextResponse.json(
      { error: "unauthorized" },
      { status: 401, headers: { "Cache-Control": "no-store" } },
    );
  }
  // A same-site page gets the SameSite=Strict cookie too, so a state-changing
  // request must also come from this origin and carry JSON (TMDEV-156).
  const guarded = await guardRequest(req);
  if ("refusal" in guarded) return guarded.refusal;
  const { path } = await params;
  const target = `${RENDERER_URL}/${path.join("/")}${req.nextUrl.search}`;

  // Every Flask route but /health needs the API token. Read per request, so a
  // rotated token is used without a restart.
  const headers: Record<string, string> = { Authorization: `Bearer ${apiToken()}` };
  const init: RequestInit = {
    method: req.method,
    // Bypass Next.js Data Cache so every call hits the live Flask API.
    cache: "no-store",
    headers,
  };
  // The guard has already refused a body that is not JSON, so the browser's own
  // Content-Type is forwarded. A bodiless POST or DELETE is forwarded bodiless.
  if (guarded.body !== "") {
    init.body = guarded.body;
    headers["Content-Type"] = guarded.contentType ?? "application/json";
  }

  let upstream: Response;
  try {
    upstream = await fetch(target, init);
  } catch (e) {
    return NextResponse.json(
      { error: `Upstream unreachable: ${e instanceof Error ? e.message : e}` },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }

  // The browser's session was checked above, so a 401 from Flask can only mean
  // it refused the dashboard's own token. Passed on as a 401 it would bounce
  // the browser to /login forever; it is a server fault, so say what fixes it.
  if (upstream.status === 401) {
    return NextResponse.json(
      { error: "The API refused the dashboard's token. Restart both so they read the same "
             + "one: docker compose restart tubematic-api tubematic-dashboard" },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }

  let data: unknown;
  try {
    data = await upstream.json();
  } catch {
    return NextResponse.json(
      { error: "Upstream returned non-JSON response" },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }

  return NextResponse.json(data, {
    status: upstream.status,
    headers: { "Cache-Control": "no-store" },
  });
}

export const GET = handler;
export const POST = handler;
export const PATCH = handler;
export const DELETE = handler;
