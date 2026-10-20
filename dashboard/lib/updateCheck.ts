/**
 * Is a newer Tubematic release out? (TMDEV-114). Server-only: the dashboard's
 * /api/update-check route is the one caller, so every open tab shares one
 * cache and the browser never talks to GitHub itself.
 *
 * The repo is not spelled here. It comes from the API's /pipeline/status
 * (`github_repo`, from tubematic_core.version.GITHUB_REPO), because this image's
 * build context is dashboard/ only and cannot import that module.
 */

// Keep in sync with kasm_workspace/image/tubematic_bootstrap.py::UPGRADE_GUIDE.
export const UPGRADE_GUIDE_URL = "https://docs.tubematic.ai/user-guide/upgrading";

/** How often GitHub is asked, at most. Unauthenticated calls are limited to 60
 * an hour per IP, and a release is not urgent news. */
export const CHECK_INTERVAL_MS = 2 * 60 * 60 * 1000;

/** A failed check (offline, rate-limited) is retried sooner than a good one is
 * repeated, but not on every request, which would hammer a limit already hit. */
export const RETRY_AFTER_FAILURE_MS = 15 * 60 * 1000;

const GITHUB_TIMEOUT_MS = 10_000;

// The same grammar as tubematic_core.version.VERSION_RE: MAJOR.MINOR.PATCH with
// an optional SemVer prerelease, never "+build". Keep in sync.
const VERSION_RE = /^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$/;

// Only a stable release tag counts: no prerelease suffix at all. This is what
// keeps a "v2.1.0-rc.1" out even when it was published without GitHub's
// prerelease flag.
const STABLE_TAG_RE = /^v(\d+\.\d+\.\d+)$/;

// What tubematic_core's test pins GITHUB_REPO to. It is pasted into URLs, so
// anything else is refused rather than requested.
const REPO_RE = /^[a-z0-9-]+\/[a-z0-9._-]+$/;

interface Version {
  core: [number, number, number];
  pre: string[];
}

export interface UpdateInfo {
  available: boolean;
  current?: string;
  latest?: string;
  release_url?: string;
  upgrade_url?: string;
}

export function parseVersion(v: string): Version | null {
  const m = VERSION_RE.exec(v);
  if (!m) return null;
  return { core: [Number(m[1]), Number(m[2]), Number(m[3])], pre: m[4] ? m[4].split(".") : [] };
}

export function isRepo(repo: string): boolean {
  return REPO_RE.test(repo);
}

function comparePre(a: string[], b: string[]): number {
  // A release outranks any of its prereleases.
  if (!a.length || !b.length) return b.length - a.length;
  for (let i = 0; i < Math.min(a.length, b.length); i++) {
    const an = /^\d+$/.test(a[i]);
    const bn = /^\d+$/.test(b[i]);
    if (an && bn) {
      const d = Number(a[i]) - Number(b[i]);
      if (d) return d;
    } else if (an !== bn) {
      return an ? -1 : 1; // numeric identifiers rank below alphanumeric ones
    } else if (a[i] !== b[i]) {
      return a[i] < b[i] ? -1 : 1;
    }
  }
  return a.length - b.length;
}

/** SemVer precedence. Both arguments must parse; an unparseable one sorts lowest. */
export function compareVersions(a: string, b: string): number {
  const va = parseVersion(a);
  const vb = parseVersion(b);
  if (!va || !vb) return (va ? 1 : 0) - (vb ? 1 : 0);
  for (let i = 0; i < 3; i++) {
    const d = va.core[i] - vb.core[i];
    if (d) return d;
  }
  return comparePre(va.pre, vb.pre);
}

/** The highest stable version in a GitHub release list, without the "v", or null.
 * Highest by version, not first listed: GitHub orders by creation date, so a
 * patch to an older line published later would otherwise win. */
export function newestStable(releases: unknown): string | null {
  if (!Array.isArray(releases)) return null;
  let best: string | null = null;
  for (const r of releases) {
    if (!r || typeof r !== "object") continue;
    const { tag_name, draft, prerelease } = r as Record<string, unknown>;
    if (draft || prerelease || typeof tag_name !== "string") continue;
    const m = STABLE_TAG_RE.exec(tag_name);
    if (m && (best === null || compareVersions(m[1], best) > 0)) best = m[1];
  }
  return best;
}

export function updateFor(current: string, repo: string, releases: unknown): UpdateInfo {
  const latest = newestStable(releases);
  if (!latest || !parseVersion(current) || compareVersions(latest, current) <= 0) {
    return { available: false };
  }
  return {
    available: true,
    current,
    latest,
    // Built from the repo rather than taken from GitHub's html_url, so the
    // banner can only ever link to this project's own release page.
    release_url: `https://github.com/${repo}/releases/tag/v${latest}`,
    upgrade_url: UPGRADE_GUIDE_URL,
  };
}

async function fetchReleases(repo: string): Promise<unknown[]> {
  const res = await fetch(`https://api.github.com/repos/${repo}/releases?per_page=100`, {
    cache: "no-store",
    headers: {
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      // GitHub refuses requests with no User-Agent.
      "User-Agent": "tubematic-dashboard",
    },
    signal: AbortSignal.timeout(GITHUB_TIMEOUT_MS),
  });
  if (!res.ok) throw new Error(`GitHub answered HTTP ${res.status}`);
  const data: unknown = await res.json();
  if (!Array.isArray(data)) throw new Error("GitHub's release list was not a list");
  return data;
}

interface CacheEntry {
  releases: unknown[] | null;
  nextCheckAt: number;
  inflight: Promise<unknown[] | null> | null;
}

const cache = new Map<string, CacheEntry>();

/** GitHub's release list for `repo`, asked at most once per CHECK_INTERVAL_MS.
 * Concurrent callers share one request. On a failure the last good list (or
 * null) is kept, and the next attempt waits RETRY_AFTER_FAILURE_MS. */
export async function releasesFor(repo: string): Promise<unknown[] | null> {
  const entry = cache.get(repo);
  if (entry?.inflight) return entry.inflight;
  if (entry && Date.now() < entry.nextCheckAt) return entry.releases;

  const previous = entry?.releases ?? null;
  const inflight = fetchReleases(repo).then(
    (releases) => {
      cache.set(repo, { releases, nextCheckAt: Date.now() + CHECK_INTERVAL_MS, inflight: null });
      return releases;
    },
    (e: unknown) => {
      console.warn(`Update check failed: ${e instanceof Error ? e.message : e}`);
      cache.set(repo, { releases: previous, nextCheckAt: Date.now() + RETRY_AFTER_FAILURE_MS, inflight: null });
      return previous;
    },
  );
  cache.set(repo, { releases: previous, nextCheckAt: 0, inflight });
  return inflight;
}

/** Tests only: forget every cached list. */
export function _resetReleaseCache(): void {
  cache.clear();
}
