import { type NextRequest, NextResponse } from "next/server";
import { apiToken, isAuthenticated } from "@/lib/session";

const RENDERER_URL = process.env.RENDERER_URL ?? "http://localhost:4000";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ path: string[] }> };

// <id>/versions/<n>/sheets/<name> is the only thing this route serves: the
// mascot sheets are PNG/JPEG, which /api/proxy (JSON only) cannot carry and
// /stream (mp4/mp3 only) will not. Anything else is a 404 before Flask is asked.
const ID = /^[a-z0-9][a-z0-9-]{0,63}$/;
const VERSION = /^[0-9]{1,6}$/;
const SHEETS = new Set(["turn", "feels", "act"]);
const IMAGE_TYPES = new Set(["image/png", "image/jpeg"]);

function error(status: number, message: string): NextResponse {
  return NextResponse.json({ error: message }, { status, headers: { "Cache-Control": "no-store" } });
}

export async function GET(req: NextRequest, { params }: Ctx): Promise<NextResponse> {
  // The same lock as /api/proxy: the session signature, checked here because
  // middleware only redirects page loads.
  if (!(await isAuthenticated(req))) return error(401, "unauthorized");
  const { path } = await params;
  if (
    path.length !== 5 || !ID.test(path[0]) || path[1] !== "versions" || !VERSION.test(path[2])
    || path[3] !== "sheets" || !SHEETS.has(path[4])
  ) {
    return error(404, "Not found");
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${RENDERER_URL}/mascots/${path.join("/")}`, {
      cache: "no-store",
      headers: { Authorization: `Bearer ${apiToken()}` },
    });
  } catch (e) {
    return error(502, `Upstream unreachable: ${e instanceof Error ? e.message : e}`);
  }
  if (upstream.status === 401) {
    return error(502, "The API refused the dashboard's token. Restart both so they read the same "
      + "one: docker compose restart tubematic-api tubematic-dashboard");
  }
  const type = (upstream.headers.get("content-type") ?? "").split(";")[0].trim().toLowerCase();
  if (upstream.status !== 200 || !IMAGE_TYPES.has(type) || !upstream.body) {
    return error(upstream.status === 200 ? 502 : upstream.status === 404 ? 404 : 502, "Sheet not available");
  }
  // Streamed through, never buffered.
  return new NextResponse(upstream.body, {
    status: 200,
    headers: { "Content-Type": type, "Cache-Control": "private, no-cache" },
  });
}
