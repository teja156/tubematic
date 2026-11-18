import { type NextRequest, NextResponse } from "next/server";
import { apiToken, isAuthenticated } from "@/lib/session";

const RENDERER_URL = process.env.RENDERER_URL ?? "http://localhost:4000";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ path: string[] }> };

// An installed external style's preview loop and poster (TMDEV-252): built-in
// previews are static files of this image (/style-previews/), an external one
// lives in its package behind the API. /api/proxy carries JSON only, so this
// route streams the two files through. Anything else is a 404 before Flask is asked.
// Keep in sync: tubematic_core/external_styles.py::ID_RE.
const ID = /^ext_[a-z0-9_]{1,40}$/;
const FILES = new Map([["preview.mp4", "video/mp4"], ["preview.webp", "image/webp"]]);

function error(status: number, message: string): NextResponse {
  return NextResponse.json({ error: message }, { status, headers: { "Cache-Control": "no-store" } });
}

export async function GET(req: NextRequest, { params }: Ctx): Promise<NextResponse> {
  // The same lock as /api/proxy: the session signature, checked here because
  // middleware only redirects page loads.
  if (!(await isAuthenticated(req))) return error(401, "unauthorized");
  const { path } = await params;
  if (path.length !== 2 || !ID.test(path[0]) || !FILES.has(path[1])) return error(404, "Not found");

  let upstream: Response;
  try {
    upstream = await fetch(`${RENDERER_URL}/visual-styles/${path[0]}/${path[1]}`, {
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
  if (upstream.status !== 200 || type !== FILES.get(path[1]) || !upstream.body) {
    return error(upstream.status === 404 ? 404 : 502, "Preview not available");
  }
  // Streamed through, never buffered.
  return new NextResponse(upstream.body, {
    status: 200,
    headers: { "Content-Type": type, "Cache-Control": "private, max-age=300" },
  });
}
