// @vitest-environment node
/**
 * Tests for the stream/[...path] route handler, against a real directory tree.
 *
 * Only the session is mocked. The filesystem is real, because the defects this
 * route guards against are filesystem behaviour: a symlink resolved by open(),
 * a FIFO that blocks it, a directory read as a file (TMDEV-163, TMDEV-164).
 *
 * Critical regressions guarded here:
 *  1. No valid session → 401, before the filesystem is touched (TMDEV-152)
 *  2. `..` segments that escape OUTPUT_DIR → 404
 *  3. A symlink that leads out of OUTPUT_DIR → 404, as a leaf or as a
 *     directory on the way, even when the target is itself an .mp4. The
 *     volume is writable by the other containers, and the dashboard container
 *     also holds the session secret and API token
 *  4. A symlink that stays inside OUTPUT_DIR still serves
 *  5. Only .mp4 and .mp3 are served (with nosniff); a directory, a FIFO or any
 *     other extension → 404, and a FIFO does not hang the request
 *  6. Ranges: a-b, a- and suffix -n are byte-exact 206s with the end clamped;
 *     an inverted, out-of-range or malformed range → 416 with bytes * /size;
 *     a multi-range request gets the whole file
 *  7. The body is a stream, never the whole file in one buffer
 *  8. Cache-Control is private, no-cache with an ETag: these files are behind
 *     a login, and a re-render overwrites the file at the same URL, so the
 *     browser must revalidate (If-None-Match → 304) rather than replay an old
 *     copy; If-Range with a stale tag gets the whole new file
 *  9. A directory on the way swapped for a symlink between the realpath check
 *     and open() is refused: the opened descriptor's own path is checked, so
 *     O_NOFOLLOW (which covers the leaf only) is not the last line
 * 10. The file handle is closed on every path: a request already aborted
 *     before the stream existed, a cancelled body, a 304, a refused open
 */
import { execFileSync } from "child_process";
import {
  mkdirSync, mkdtempSync, promises as fsp, renameSync, rmSync, statSync, symlinkSync,
  utimesSync, writeFileSync,
} from "fs";
import type { FileHandle } from "fs/promises";
import { tmpdir } from "os";
import path from "path";
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

const session = vi.hoisted(() => ({ ok: true }));
vi.mock("@/lib/session", () => ({ isAuthenticated: vi.fn(async () => session.ok) }));

type Get = typeof import("@/app/stream/[...path]/route").GET;
let GET: Get;
let base: string;
let root: string;

// The real open(), kept before any spy replaces it.
const realOpen = fsp.open.bind(fsp);

const VIDEO = Buffer.from(Array.from({ length: 1000 }, (_, i) => i % 251));
const SECRET = Buffer.from("this-is-the-session-secret\n");

beforeAll(async () => {
  base = mkdtempSync(path.join(tmpdir(), "tm-stream-"));
  root = path.join(base, "output_videos");
  mkdirSync(path.join(root, "proj"), { recursive: true });
  mkdirSync(path.join(root, "voice-previews"));
  mkdirSync(path.join(root, "dir.mp4"));
  mkdirSync(path.join(root, "swap"));
  writeFileSync(path.join(root, "swap", "v.mp4"), VIDEO);
  // Far more than the read stream and its web wrapper buffer, so a handle
  // only closes if the route closes it, not because the file ran out.
  writeFileSync(path.join(root, "proj", "big.mp4"), Buffer.alloc(16 * 1024 * 1024));
  mkdirSync(path.join(base, "elsewhere"));
  writeFileSync(path.join(root, "proj", "vid.mp4"), VIDEO);
  writeFileSync(path.join(root, "voice-previews", "abc.mp3"), Buffer.from("ID3-mp3-bytes"));
  writeFileSync(path.join(root, "notes.txt"), "not media");
  writeFileSync(path.join(base, "session_secret"), SECRET);
  writeFileSync(path.join(base, "outside.mp4"), SECRET);
  writeFileSync(path.join(base, "elsewhere", "v.mp4"), SECRET);
  // Planted links, as another container with the volume mounted rw could.
  symlinkSync(path.join(base, "outside.mp4"), path.join(root, "leak.mp4"));
  symlinkSync(path.join(base, "session_secret"), path.join(root, "secret.mp4"));
  symlinkSync(path.join(base, "elsewhere"), path.join(root, "linkdir"));
  symlinkSync(path.join(root, "proj", "vid.mp4"), path.join(root, "alias.mp4"));
  execFileSync("mkfifo", [path.join(root, "pipe.mp4")]);

  process.env.OUTPUT_DIR = root;
  vi.resetModules();
  ({ GET } = await import("@/app/stream/[...path]/route"));
});

afterAll(() => {
  rmSync(base, { recursive: true, force: true });
  delete process.env.OUTPUT_DIR;
});

beforeEach(() => {
  session.ok = true;
  vi.restoreAllMocks();
});

function get(segs: string[], range?: string, extra: Record<string, string> = {}, signal?: AbortSignal) {
  const req = new NextRequest(`http://localhost:3000/stream/${segs.join("/")}`, {
    headers: { ...(range === undefined ? {} : { Range: range }), ...extra },
    signal,
  });
  return GET(req, { params: Promise.resolve({ path: segs }) });
}

/** Spy on open() and keep every handle it returns, so a test can tell whether
 *  the route closed it (a closed FileHandle's fd is -1). */
function trackHandles(): FileHandle[] {
  const handles: FileHandle[] = [];
  vi.spyOn(fsp, "open").mockImplementation((async (...args: Parameters<typeof fsp.open>) => {
    const handle = await realOpen(...args);
    handles.push(handle);
    return handle;
  }) as typeof fsp.open);
  return handles;
}

async function bytes(res: Response): Promise<Buffer> {
  return Buffer.from(await res.arrayBuffer());
}

describe("stream/[...path]/route — access", () => {
  it("answers 401 without a session and never touches the filesystem", async () => {
    session.ok = false;
    const realpath = vi.spyOn(fsp, "realpath");
    const open = vi.spyOn(fsp, "open");
    const res = await get(["proj", "vid.mp4"]);
    expect(res.status).toBe(401);
    expect(realpath).not.toHaveBeenCalled();
    expect(open).not.toHaveBeenCalled();
  });

  it("404s a path that escapes OUTPUT_DIR with ..", async () => {
    const res = await get(["..", "outside.mp4"]);
    expect(res.status).toBe(404);
  });

  it("404s a missing file", async () => {
    expect((await get(["proj", "nope.mp4"])).status).toBe(404);
  });

  it("404s a symlinked leaf that points outside, even to an .mp4", async () => {
    for (const name of ["leak.mp4", "secret.mp4"]) {
      const res = await get([name]);
      expect(res.status).toBe(404);
      expect((await bytes(res)).includes(SECRET)).toBe(false);
    }
  });

  it("404s a file reached through a symlinked directory that points outside", async () => {
    const res = await get(["linkdir", "v.mp4"]);
    expect(res.status).toBe(404);
    expect((await bytes(res)).includes(SECRET)).toBe(false);
  });

  it("still serves a symlink that stays inside OUTPUT_DIR", async () => {
    const res = await get(["alias.mp4"]);
    expect(res.status).toBe(200);
    expect((await bytes(res)).equals(VIDEO)).toBe(true);
  });

  it("404s a directory, even one named like a video", async () => {
    expect((await get(["proj"])).status).toBe(404);
    expect((await get(["dir.mp4"])).status).toBe(404);
  });

  it("404s a FIFO named like a video instead of hanging on it", async () => {
    expect((await get(["pipe.mp4"])).status).toBe(404);
  });

  it("404s any extension but .mp4 and .mp3", async () => {
    expect((await get(["notes.txt"])).status).toBe(404);
  });

  it("404s a file whose directory is swapped for a symlink between realpath and open", async () => {
    // What another container with the volume mounted rw could race: realpath
    // has passed on swap/v.mp4, then swap/ becomes a link to a directory
    // outside, and O_NOFOLLOW guards only the leaf. Doing the swap inside
    // open() makes the race deterministic.
    const swap = path.join(root, "swap");
    vi.spyOn(fsp, "open").mockImplementation((async (...args: Parameters<typeof fsp.open>) => {
      renameSync(swap, swap + "-old");
      symlinkSync(path.join(base, "elsewhere"), swap);
      return realOpen(...args);
    }) as typeof fsp.open);
    try {
      const res = await get(["swap", "v.mp4"]);
      expect(res.status).toBe(404);
      expect((await bytes(res)).includes(SECRET)).toBe(false);
    } finally {
      rmSync(swap);
      renameSync(swap + "-old", swap);
    }
    vi.restoreAllMocks();
    expect((await get(["swap", "v.mp4"])).status).toBe(200);
  });

  it("404s the same swap where there is no /proc, by the file's identity", async () => {
    // macOS or another OS running `npm run dev`: descriptorPath has nothing to
    // read, so the dev/ino of the file that passed the checks is what refuses
    // the file open() actually reached.
    const platform = Object.getOwnPropertyDescriptor(process, "platform")!;
    Object.defineProperty(process, "platform", { ...platform, value: "darwin" });
    const readlink = vi.spyOn(fsp, "readlink");
    const swap = path.join(root, "swap");
    vi.spyOn(fsp, "open").mockImplementation((async (...args: Parameters<typeof fsp.open>) => {
      renameSync(swap, swap + "-old");
      symlinkSync(path.join(base, "elsewhere"), swap);
      return realOpen(...args);
    }) as typeof fsp.open);
    try {
      const res = await get(["swap", "v.mp4"]);
      expect(res.status).toBe(404);
      expect((await bytes(res)).includes(SECRET)).toBe(false);
      expect(readlink).not.toHaveBeenCalled();
      rmSync(swap);
      renameSync(swap + "-old", swap);
      vi.restoreAllMocks();
      // The fallback still serves the file when nothing was swapped.
      expect((await get(["swap", "v.mp4"])).status).toBe(200);
    } finally {
      Object.defineProperty(process, "platform", platform);
    }
  });

  it("404s and closes the file when the opened descriptor's real path is not the one checked", async () => {
    const handles = trackHandles();
    const readlink = vi.spyOn(fsp, "readlink").mockResolvedValue(path.join(base, "elsewhere", "v.mp4"));
    const res = await get(["proj", "vid.mp4"]);
    expect(res.status).toBe(404);
    expect(readlink).toHaveBeenCalledWith(expect.stringMatching(/^\/proc\/self\/fd\/\d+$/));
    expect(handles).toHaveLength(1);
    expect(handles[0].fd).toBe(-1);
  });

  it("fails closed when the descriptor's path cannot be read", async () => {
    vi.spyOn(fsp, "readlink").mockRejectedValue(Object.assign(new Error("no /proc"), { code: "ENOENT" }));
    expect((await get(["proj", "vid.mp4"])).status).toBe(404);
  });
});

describe("stream/[...path]/route — file handles", () => {
  it("closes the file when the request was aborted before the stream existed", async () => {
    const handles = trackHandles();
    const controller = new AbortController();
    controller.abort();
    await get(["proj", "big.mp4"], undefined, {}, controller.signal);
    expect(handles).toHaveLength(1);
    await vi.waitFor(() => expect(handles[0].fd).toBe(-1));
  });

  it("closes the file when the response body is cancelled", async () => {
    const handles = trackHandles();
    const res = await get(["proj", "big.mp4"]);
    expect(res.status).toBe(200);
    expect(handles[0].fd).not.toBe(-1);
    await res.body!.cancel();
    await vi.waitFor(() => expect(handles[0].fd).toBe(-1));
  });

  it("closes the file when the browser goes away mid-stream", async () => {
    const handles = trackHandles();
    const controller = new AbortController();
    const res = await get(["proj", "big.mp4"], undefined, {}, controller.signal);
    expect(res.status).toBe(200);
    controller.abort();
    await vi.waitFor(() => expect(handles[0].fd).toBe(-1));
  });
});

describe("stream/[...path]/route — caching", () => {
  it("revalidates rather than caches: private, no-cache with an ETag", async () => {
    const res = await get(["proj", "vid.mp4"]);
    expect(res.headers.get("Cache-Control")).toBe("private, no-cache");
    expect(res.headers.get("ETag")).toMatch(/^"[^"]+"$/);
  });

  it("answers a matching If-None-Match with a bodiless 304 and closes the file", async () => {
    const etag = (await get(["proj", "vid.mp4"])).headers.get("ETag")!;
    const handles = trackHandles();
    for (const inm of [etag, `W/${etag}`, `"nope", ${etag}`, "*"]) {
      const res = await get(["proj", "vid.mp4"], "bytes=0-9", { "If-None-Match": inm });
      expect(res.status).toBe(304);
      expect(res.headers.get("ETag")).toBe(etag);
      expect(res.headers.get("Cache-Control")).toBe("private, no-cache");
      expect((await bytes(res)).length).toBe(0);
    }
    expect(handles.every((h) => h.fd === -1)).toBe(true);
  });

  it("serves a re-rendered file at the same path with a new ETag, and its new bytes", async () => {
    const file = path.join(root, "proj", "rerender.mp4");
    writeFileSync(file, VIDEO);
    utimesSync(file, 1_000_000, 1_000_000);
    const before = (await get(["proj", "rerender.mp4"])).headers.get("ETag")!;

    const NEW = Buffer.from(VIDEO).reverse();
    writeFileSync(file, NEW);
    utimesSync(file, 2_000_000, 2_000_000);
    const res = await get(["proj", "rerender.mp4"], undefined, { "If-None-Match": before });
    expect(res.status).toBe(200);
    expect(res.headers.get("ETag")).not.toBe(before);
    expect((await bytes(res)).equals(NEW)).toBe(true);
  });

  // A render replaced by another of the same length whose mtime ends up where
  // the old one was: size and mtime alone keep the tag, so the old copy would
  // validate (304) and an old If-Range would splice old ranges onto new bytes.
  async function expectOldTagRefused(name: string, before: string, NEW: Buffer) {
    const res = await get(["proj", name], undefined, { "If-None-Match": before });
    expect(res.status).toBe(200);
    expect(res.headers.get("ETag")).not.toBe(before);
    expect((await bytes(res)).equals(NEW)).toBe(true);
    const ranged = await get(["proj", name], "bytes=0-9", { "If-Range": before });
    expect(ranged.status).toBe(200);
    expect((await bytes(ranged)).equals(NEW)).toBe(true);
  }

  it("gives a new tag to a same-size file renamed into place with its old mtime", async () => {
    const file = path.join(root, "proj", "same-size.mp4");
    writeFileSync(file, VIDEO);
    utimesSync(file, 1_000_000, 1_000_000);
    const before = (await get(["proj", "same-size.mp4"])).headers.get("ETag")!;

    const NEW = Buffer.from(VIDEO).reverse();
    writeFileSync(file + ".tmp", NEW);
    renameSync(file + ".tmp", file);
    utimesSync(file, 1_000_000, 1_000_000);
    await expectOldTagRefused("same-size.mp4", before, NEW);
  });

  it("gives a new tag to a same-size file rewritten in place with its old mtime", async () => {
    const file = path.join(root, "proj", "in-place.mp4");
    writeFileSync(file, VIDEO);
    utimesSync(file, 1_000_000, 1_000_000);
    const ino = statSync(file).ino;
    const before = (await get(["proj", "in-place.mp4"])).headers.get("ETag")!;

    // ctime is what changes here, and some filesystems tick it coarsely.
    await new Promise((r) => setTimeout(r, 20));
    const NEW = Buffer.from(VIDEO).reverse();
    writeFileSync(file, NEW);
    utimesSync(file, 1_000_000, 1_000_000);
    expect(statSync(file).ino).toBe(ino);
    await expectOldTagRefused("in-place.mp4", before, NEW);
  });

  it("honours a Range whose If-Range matches, and sends the whole file when it does not", async () => {
    const etag = (await get(["proj", "vid.mp4"])).headers.get("ETag")!;
    const same = await get(["proj", "vid.mp4"], "bytes=0-9", { "If-Range": etag });
    expect(same.status).toBe(206);
    expect((await bytes(same)).equals(VIDEO.subarray(0, 10))).toBe(true);

    for (const stale of ['"an-old-render"', `W/${etag}`, "Wed, 21 Oct 2015 07:28:00 GMT"]) {
      const res = await get(["proj", "vid.mp4"], "bytes=0-9", { "If-Range": stale });
      expect(res.status).toBe(200);
      expect((await bytes(res)).equals(VIDEO)).toBe(true);
    }
  });
});

describe("stream/[...path]/route — content", () => {
  it("serves the whole file as a 200 stream with its headers", async () => {
    const res = await get(["proj", "vid.mp4"]);
    expect(res.status).toBe(200);
    expect(res.body).toBeInstanceOf(ReadableStream);
    expect(res.headers.get("Content-Type")).toBe("video/mp4");
    expect(res.headers.get("Content-Length")).toBe("1000");
    expect(res.headers.get("Accept-Ranges")).toBe("bytes");
    expect(res.headers.get("X-Content-Type-Options")).toBe("nosniff");
    expect(res.headers.get("Cache-Control")).toBe("private, no-cache");
    expect((await bytes(res)).equals(VIDEO)).toBe(true);
  });

  it("serves a voice preview as audio/mpeg", async () => {
    const res = await get(["voice-previews", "abc.mp3"]);
    expect(res.status).toBe(200);
    expect(res.headers.get("Content-Type")).toBe("audio/mpeg");
    expect((await bytes(res)).toString()).toBe("ID3-mp3-bytes");
  });

  const ranges: [string, number, number][] = [
    ["bytes=0-9", 0, 9],
    ["bytes=100-", 100, 999],
    ["bytes=-10", 990, 999],
    ["bytes=995-5000", 995, 999],
    ["bytes=-5000", 0, 999],
  ];
  for (const [header, start, end] of ranges) {
    it(`answers ${header} with a byte-exact 206`, async () => {
      const res = await get(["proj", "vid.mp4"], header);
      expect(res.status).toBe(206);
      expect(res.body).toBeInstanceOf(ReadableStream);
      expect(res.headers.get("Content-Range")).toBe(`bytes ${start}-${end}/1000`);
      expect(res.headers.get("Content-Length")).toBe(String(end - start + 1));
      expect(res.headers.get("Cache-Control")).toBe("private, no-cache");
      expect((await bytes(res)).equals(VIDEO.subarray(start, end + 1))).toBe(true);
    });
  }

  for (const header of ["bytes=10-5", "bytes=1000-", "bytes=5000-6000", "bytes=-0", "bytes=-", "bytes=abc"]) {
    it(`answers ${header} with 416 and the size`, async () => {
      const res = await get(["proj", "vid.mp4"], header);
      expect(res.status).toBe(416);
      expect(res.headers.get("Content-Range")).toBe("bytes */1000");
    });
  }

  it("answers a multi-range request with the whole file", async () => {
    const res = await get(["proj", "vid.mp4"], "bytes=0-1, 5-6");
    expect(res.status).toBe(200);
    expect((await bytes(res)).equals(VIDEO)).toBe(true);
  });
});
