/**
 * The update check's decision layer (TMDEV-114): which GitHub releases count,
 * how versions order, and when the 2-hour cache asks GitHub again.
 *
 * The rule that matters most: only a newer *stable* release is ever offered. A
 * prerelease is recognised by its tag (`v2.1.0-rc.1`) as well as by GitHub's
 * `prerelease` flag, because a release can be published without the flag.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  CHECK_INTERVAL_MS,
  RETRY_AFTER_FAILURE_MS,
  UPGRADE_GUIDE_URL,
  _resetReleaseCache,
  compareVersions,
  isRepo,
  newestStable,
  parseVersion,
  releasesFor,
  updateFor,
} from "@/lib/updateCheck";

const rel = (tag: string, extra: Record<string, unknown> = {}) => ({
  tag_name: tag, draft: false, prerelease: false, ...extra,
});

describe("parseVersion", () => {
  it("accepts a release and a prerelease", () => {
    expect(parseVersion("2.0.1")).not.toBeNull();
    expect(parseVersion("2.1.0-rc.1")).not.toBeNull();
  });

  it("refuses develop, a v prefix, build metadata and garbage", () => {
    for (const v of ["develop", "v2.0.0", "2.0.0+build", "2.0", "", "2.0.0-", "1.2.3.4"]) {
      expect(parseVersion(v), v).toBeNull();
    }
  });
});

describe("compareVersions", () => {
  it("orders numerically, not as strings", () => {
    expect(compareVersions("2.0.10", "2.0.9")).toBeGreaterThan(0);
    expect(compareVersions("10.0.0", "9.9.9")).toBeGreaterThan(0);
    expect(compareVersions("2.0.0", "2.0.0")).toBe(0);
  });

  it("puts a prerelease before its release, so an rc install is offered the final", () => {
    expect(compareVersions("2.1.0", "2.1.0-rc.1")).toBeGreaterThan(0);
    expect(compareVersions("2.1.0-rc.1", "2.0.9")).toBeGreaterThan(0);
  });

  it("follows SemVer precedence between prerelease identifiers", () => {
    expect(compareVersions("1.0.0-rc.2", "1.0.0-rc.10")).toBeLessThan(0);
    expect(compareVersions("1.0.0-alpha", "1.0.0-alpha.1")).toBeLessThan(0);
    expect(compareVersions("1.0.0-1", "1.0.0-alpha")).toBeLessThan(0);
    expect(compareVersions("1.0.0-beta", "1.0.0-alpha")).toBeGreaterThan(0);
  });
});

describe("isRepo", () => {
  it("accepts a bare owner/name only", () => {
    expect(isRepo("teja156/tubematic")).toBe(true);
    for (const r of ["", "tubematic", "a/b/c", "../x", "owner/name?x=1", "Owner/Name", "a/b.git/"]) {
      expect(isRepo(r), r).toBe(false);
    }
  });
});

describe("newestStable", () => {
  it("picks the highest stable version, not the first listed", () => {
    // GitHub lists by creation date: a 1.2.x patch published after 2.0.1 comes first.
    expect(newestStable([rel("v1.2.9"), rel("v2.0.1"), rel("v2.0.0")])).toBe("2.0.1");
  });

  it("ignores a prerelease by its tag even when GitHub does not flag it", () => {
    expect(newestStable([rel("v2.1.0-rc.1"), rel("v2.0.0")])).toBe("2.0.0");
    expect(newestStable([rel("v2.1.0-beta"), rel("v2.0.0")])).toBe("2.0.0");
  });

  it("ignores a release GitHub flags as a prerelease, and drafts", () => {
    expect(newestStable([rel("v2.1.0", { prerelease: true }), rel("v2.0.0")])).toBe("2.0.0");
    expect(newestStable([rel("v2.1.0", { draft: true }), rel("v2.0.0")])).toBe("2.0.0");
  });

  it("ignores tags that are not vX.Y.Z and malformed entries", () => {
    const list = [rel("2.9.0"), rel("ls"), rel("vdevelop"), { tag_name: 7 }, null, "x", rel("v2.0.0")];
    expect(newestStable(list)).toBe("2.0.0");
  });

  it("returns null when nothing qualifies", () => {
    expect(newestStable([])).toBeNull();
    expect(newestStable([rel("v3.0.0-rc.1")])).toBeNull();
    expect(newestStable("not a list" as unknown as unknown[])).toBeNull();
  });
});

describe("updateFor", () => {
  const repo = "teja156/tubematic";

  it("offers a newer stable release with links to it and to the upgrade guide", () => {
    expect(updateFor("2.0.0", repo, [rel("v2.0.1"), rel("v2.0.0")])).toEqual({
      available: true,
      current: "2.0.0",
      latest: "2.0.1",
      release_url: "https://github.com/teja156/tubematic/releases/tag/v2.0.1",
      upgrade_url: UPGRADE_GUIDE_URL,
    });
  });

  it("offers nothing for the same or an older release", () => {
    expect(updateFor("2.0.1", repo, [rel("v2.0.1")]).available).toBe(false);
    expect(updateFor("2.0.2", repo, [rel("v2.0.1")]).available).toBe(false);
  });

  it("offers nothing for a newer prerelease (the ticket's v1.0.1 / v1.0.1-beta example)", () => {
    expect(updateFor("1.0.1", repo, [rel("v1.0.2-beta"), rel("v1.0.1")]).available).toBe(false);
  });

  it("offers the final release to a prerelease install", () => {
    expect(updateFor("2.1.0-rc.1", repo, [rel("v2.1.0")]).latest).toBe("2.1.0");
  });

  it("offers nothing on the development branch, which is not a release", () => {
    expect(updateFor("develop", repo, [rel("v9.0.0")]).available).toBe(false);
  });
});

describe("releasesFor (the 2-hour cache)", () => {
  const repo = "teja156/tubematic";
  const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body }) as Response;

  beforeEach(() => {
    _resetReleaseCache();
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-20T00:00:00Z"));
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("asks GitHub's release list for the repo, unauthenticated, with a User-Agent", async () => {
    const fetchMock = vi.fn().mockResolvedValue(ok([rel("v2.0.0")]));
    vi.stubGlobal("fetch", fetchMock);
    expect(await releasesFor(repo)).toEqual([rel("v2.0.0")]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("https://api.github.com/repos/teja156/tubematic/releases?per_page=100");
    expect(init.headers["User-Agent"]).toBeTruthy();
    expect(init.headers.Authorization).toBeUndefined();
  });

  it("asks GitHub at most once per 2 hours", async () => {
    const fetchMock = vi.fn().mockResolvedValue(ok([rel("v2.0.0")]));
    vi.stubGlobal("fetch", fetchMock);
    await releasesFor(repo);
    vi.advanceTimersByTime(CHECK_INTERVAL_MS - 1000);
    await releasesFor(repo);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(2000);
    await releasesFor(repo);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("shares one request between concurrent callers", async () => {
    const fetchMock = vi.fn().mockResolvedValue(ok([rel("v2.0.0")]));
    vi.stubGlobal("fetch", fetchMock);
    await Promise.all([releasesFor(repo), releasesFor(repo), releasesFor(repo)]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("retries a failure after 15 minutes, not 2 hours, and keeps the last good list", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(ok([rel("v2.0.0")]))
      .mockResolvedValueOnce({ ok: false, status: 403, json: async () => ({}) } as Response)
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValue(ok([rel("v2.0.1")]));
    vi.stubGlobal("fetch", fetchMock);

    await releasesFor(repo);
    vi.advanceTimersByTime(CHECK_INTERVAL_MS + 1);
    expect(await releasesFor(repo)).toEqual([rel("v2.0.0")]); // 403 (rate limit)
    vi.advanceTimersByTime(RETRY_AFTER_FAILURE_MS - 1000);
    await releasesFor(repo);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    vi.advanceTimersByTime(2000);
    expect(await releasesFor(repo)).toEqual([rel("v2.0.0")]); // network error
    vi.advanceTimersByTime(RETRY_AFTER_FAILURE_MS + 1);
    expect(await releasesFor(repo)).toEqual([rel("v2.0.1")]);
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it("returns null when the first request fails and there is no earlier list", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(ok({ message: "not a list" })));
    expect(await releasesFor(repo)).toBeNull();
  });
});
