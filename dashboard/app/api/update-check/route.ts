import { type NextRequest, NextResponse } from "next/server";
import { apiToken, isAuthenticated } from "@/lib/session";
import { isRepo, parseVersion, releasesFor, updateFor, type UpdateInfo } from "@/lib/updateCheck";

const RENDERER_URL = process.env.RENDERER_URL ?? "http://localhost:4000";

export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store" };
const NO_UPDATE: UpdateInfo = { available: false };

/**
 * Is a newer stable release out? (TMDEV-114). The banner under the top bar
 * polls this.
 *
 * The installed version and the repo are read from the API on every request,
 * so the answer changes the moment an upgrade lands; only GitHub's release
 * list is cached (lib/updateCheck.ts, 2 hours). Anything that prevents a
 * confident answer -- the development branch, an API older than this route,
 * an unreachable API or GitHub -- is "no update", never an error: the banner
 * is a courtesy, and a false one is worse than none.
 */
export async function GET(req: NextRequest): Promise<NextResponse> {
  if (!(await isAuthenticated(req))) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401, headers: NO_STORE });
  }

  let status: Record<string, unknown>;
  try {
    const res = await fetch(`${RENDERER_URL}/pipeline/status`, {
      cache: "no-store",
      headers: { Authorization: `Bearer ${apiToken()}` },
    });
    if (!res.ok) return NextResponse.json(NO_UPDATE, { headers: NO_STORE });
    status = await res.json();
  } catch {
    return NextResponse.json(NO_UPDATE, { headers: NO_STORE });
  }

  const current = status?.version;
  const repo = status?.github_repo;
  if (typeof current !== "string" || !parseVersion(current) || typeof repo !== "string" || !isRepo(repo)) {
    return NextResponse.json(NO_UPDATE, { headers: NO_STORE });
  }

  const releases = await releasesFor(repo);
  return NextResponse.json(updateFor(current, repo, releases), { headers: NO_STORE });
}
