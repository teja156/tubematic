/**
 * Refuse a state-changing request that another site could have made
 * (TMDEV-156). Used by /api/proxy and /api/auth/{login,logout}.
 *
 * The session cookie is SameSite=Strict, which stops a request started by a
 * different *site*. It does not stop one from the same site: another port on
 * the same host, or a sibling subdomain, is same-site, so the browser attaches
 * the cookie. Two checks close that, and neither depends on the Host header
 * (a reverse proxy in front rewrites Host, which is why there is no Origin vs
 * Host comparison here):
 *
 * 1. `Sec-Fetch-Site`. Browsers set it themselves, and a page cannot forge or
 *    remove it. Anything but `same-origin` is refused. A request with no such
 *    header (curl, an old browser) passes this check: it is not a browser
 *    acting for another page, or it is one that predates the header.
 *
 * 2. JSON only. An HTML form can only send urlencoded, multipart or text/plain,
 *    and always sends a Content-Type, even for an empty form. A cross-origin
 *    fetch() that sets `application/json` triggers a CORS preflight, which
 *    fails because nothing here answers one. So a non-GET whose Content-Type
 *    is present must be JSON, and a non-GET with a body must say it is JSON.
 *    A request with neither a body nor a Content-Type passes: the dashboard's
 *    own bodiless POSTs and DELETEs look like that. The one browser request of
 *    that shape another page can send (a no-cors fetch) carries Sec-Fetch-Site
 *    in every current browser, so check 1 refuses it.
 */
import { NextResponse } from "next/server";

const SAFE_METHODS = new Set(["GET", "HEAD"]);

export function isJsonContentType(value: string | null): boolean {
  return (value ?? "").split(";")[0].trim().toLowerCase() === "application/json";
}

type Guarded = { refusal: NextResponse } | { body: string; contentType: string | null };

/**
 * Check a request and read its body. A GET or HEAD is never refused and its
 * body is not read. Otherwise the result is either a refusal to return as is,
 * or the body text and the Content-Type to forward.
 */
export async function guardRequest(req: Request): Promise<Guarded> {
  if (SAFE_METHODS.has(req.method)) return { body: "", contentType: null };
  const noStore = { "Cache-Control": "no-store" };

  const site = req.headers.get("sec-fetch-site");
  if (site !== null && site !== "same-origin") {
    return {
      refusal: NextResponse.json(
        { error: "cross-site request refused" },
        { status: 403, headers: noStore },
      ),
    };
  }

  const contentType = req.headers.get("content-type");
  const body = await req.text();
  if ((contentType !== null || body !== "") && !isJsonContentType(contentType)) {
    return {
      refusal: NextResponse.json(
        { error: "request body must be application/json" },
        { status: 415, headers: noStore },
      ),
    };
  }
  return { body, contentType };
}
