import { type NextRequest, NextResponse } from "next/server";
import { guardRequest } from "@/lib/requestGuard";
import { isHttps, sessionCookie } from "@/lib/session";

export const dynamic = "force-dynamic";

/**
 * Clear the session cookie. POST only, so a link or an image cannot sign anyone
 * out, and same-origin only, so another page on this site cannot (TMDEV-156).
 */
export async function POST(req: NextRequest): Promise<NextResponse> {
  const guarded = await guardRequest(req);
  if ("refusal" in guarded) return guarded.refusal;
  const res = NextResponse.json({ ok: true }, { headers: { "Cache-Control": "no-store" } });
  res.cookies.set(sessionCookie("", isHttps(req), 0));
  return res;
}
