import { constants, promises as fsp } from "fs";
import type { FileHandle } from "fs/promises";
import path from "path";
import { Readable } from "stream";
import { type NextRequest, NextResponse } from "next/server";
import { isAuthenticated } from "@/lib/session";

export const runtime = "nodejs";

const OUTPUT_DIR = process.env.OUTPUT_DIR ?? "/output_videos";

// Rendered videos and cached voice previews are the only things this route is
// for. Anything else on the volume is not served, whatever it is called.
const CONTENT_TYPES = new Map([
  [".mp4", "video/mp4"],
  [".mp3", "audio/mpeg"],
]);

function contentTypeFor(filePath: string): string | undefined {
  return CONTENT_TYPES.get(path.extname(filePath).toLowerCase());
}

function notFound(): NextResponse {
  return NextResponse.json({ error: "Not found" }, { status: 404 });
}

/**
 * A Range header, resolved against the file's size: the bytes to send, `null`
 * for the whole file, or "unsatisfiable" for a 416. One range only: a
 * multi-range request gets the whole file, which RFC 9110 allows and which no
 * <video> or <audio> element asks for anyway.
 */
function parseRange(
  header: string | null, size: number,
): { start: number; end: number } | null | "unsatisfiable" {
  if (header === null) return null;
  const value = header.trim();
  if (/^bytes=.*,/.test(value)) return null;
  const m = /^bytes=(\d*)-(\d*)$/.exec(value);
  if (!m || (m[1] === "" && m[2] === "")) return "unsatisfiable";
  if (m[1] === "") {
    // Suffix: the last n bytes.
    const n = Number(m[2]);
    if (n === 0 || size === 0) return "unsatisfiable";
    return { start: Math.max(0, size - n), end: size - 1 };
  }
  const start = Number(m[1]);
  const last = m[2] === "" ? size - 1 : Number(m[2]);
  if (start >= size || last < start) return "unsatisfiable";
  return { start, end: Math.min(last, size - 1) };
}

/**
 * Where an open descriptor really is, by the kernel's own account. On Linux,
 * /proc/self/fd/<n> names the file the descriptor was opened on, through
 * whatever directories open() actually walked. Elsewhere there is no /proc,
 * so `npm run dev` on another OS skips this (null) and relies on the device
 * and inode comparison alone, while a Linux process that cannot read /proc
 * fails closed (the readlink rejects, and the caller answers 404).
 */
async function descriptorPath(handle: FileHandle): Promise<string | null> {
  if (process.platform !== "linux") return null;
  return fsp.readlink(`/proc/self/fd/${handle.fd}`);
}

/** Whether an If-None-Match value names this file (or is "*"). */
function noneMatch(header: string, etag: string): boolean {
  if (header.trim() === "*") return true;
  // Weak comparison, as If-None-Match uses: W/"x" matches "x".
  return header.split(",").some((tag) => tag.trim().replace(/^W\//, "") === etag);
}

/**
 * Serve a rendered video or a voice preview off the output volume (TMDEV-163,
 * TMDEV-164).
 *
 * The volume is writable by the API, MCP and renderer containers, so a file or
 * symlink on it is not trusted to stay inside it: both paths are resolved with
 * realpath and the real one must still be under the real OUTPUT_DIR. That
 * check and the open() are two steps, so the open is checked too: O_NOFOLLOW
 * refuses a leaf swapped for a symlink in between, and the opened descriptor
 * must be the same file (device and inode) as the real path that passed, which
 * refuses a directory on the way swapped for one (O_NOFOLLOW covers only the
 * leaf). On Linux its own path must also be exactly that real path.
 * O_NONBLOCK keeps a FIFO from blocking the open; the fstat that follows
 * refuses it, and a directory, as not a regular file.
 *
 * The file is streamed from that one handle, never read into memory: a Range
 * of `bytes=0-` is the whole file, and the browser asks for that first.
 *
 * A re-render overwrites the file at the same URL, so the browser may keep a
 * copy but must revalidate it: `no-cache` plus an ETag of the file's device,
 * inode, size, mtime and ctime, answered with a 304 while it still matches.
 */
export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  // A <video>/<audio> src sends the session cookie like any same-site
  // request; without a valid session there is nothing to stream (TMDEV-152).
  if (!(await isAuthenticated(req))) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  const { path: segments } = await params;
  const outputRoot = path.resolve(OUTPUT_DIR);
  const filePath = path.resolve(outputRoot, ...segments);

  // voice_id is free text a human types into the roster editor, and its hash
  // ends up in a path segment here, so a lexical escape is refused first.
  if (!filePath.startsWith(outputRoot + path.sep)) return notFound();

  const type = contentTypeFor(filePath);
  if (!type) return notFound();

  let realRoot: string;
  let realPath: string;
  try {
    realRoot = await fsp.realpath(outputRoot);
    realPath = await fsp.realpath(filePath);
  } catch {
    return notFound();
  }
  if (!realPath.startsWith(realRoot + path.sep)) return notFound();
  if (contentTypeFor(realPath) !== type) return notFound();

  // The file that passed, by identity, for the comparison after the open.
  let checked: { dev: bigint; ino: bigint };
  try {
    checked = await fsp.lstat(realPath, { bigint: true });
  } catch {
    return notFound();
  }

  let handle: FileHandle;
  try {
    handle = await fsp.open(realPath, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  } catch {
    return notFound();
  }

  // Until a read stream owns the handle, every way out of here closes it.
  let owned = false;
  try {
    // Equal to the real path that passed the checks above is enough: that
    // one is inside the real root and has an allowed extension.
    const opened = await descriptorPath(handle);
    if (opened !== null && opened !== realPath) return notFound();

    const stat = await handle.stat({ bigint: true });
    // On every platform: the descriptor must be the very file that passed.
    // A directory on the way swapped between the lstat and the open lands on
    // another file, so this holds where /proc does not exist.
    if (stat.dev !== checked.dev || stat.ino !== checked.ino) return notFound();
    if (!stat.isFile()) return notFound();
    const size = Number(stat.size);

    // Strong, so If-Range can use it, which needs it to change with the bytes.
    // Size and mtime alone do not: a same-size file can be renamed into place,
    // or rewritten, with its old mtime put back. A rename changes the inode;
    // a rewrite changes ctime, which utimes cannot set. Not Last-Modified as
    // well: it has one-second resolution, and a render replaced within the
    // same second would validate the old copy.
    const etag = `"${[stat.dev, stat.ino, stat.size, stat.mtimeNs, stat.ctimeNs].map((n) => n.toString(16)).join("-")}"`;
    const headers: Record<string, string> = {
      "Content-Type": type,
      "Accept-Ranges": "bytes",
      "X-Content-Type-Options": "nosniff",
      "Cache-Control": "private, no-cache",
      ETag: etag,
    };

    const inm = req.headers.get("if-none-match");
    if (inm !== null && noneMatch(inm, etag)) return new Response(null, { status: 304, headers });

    // A Range is only for the copy the browser already holds: a stale or
    // weak If-Range (or a date, which this never sends) gets the whole file.
    const ifRange = req.headers.get("if-range");
    const rangeHeader = ifRange === null || ifRange.trim() === etag ? req.headers.get("range") : null;
    const range = parseRange(rangeHeader, size);
    if (range === "unsatisfiable") {
      return new Response(null, { status: 416, headers: { ...headers, "Content-Range": `bytes */${size}` } });
    }

    // The stream owns the handle from here: it closes it at the end, on an
    // error, when the body is cancelled (Readable.toWeb destroys it) and when
    // the browser goes away (seeking cancels the old request). A browser that
    // went away during the awaits above fired its abort before this listener
    // existed, so that case is checked here, with nothing awaited in between.
    const stream = handle.createReadStream(range ? { start: range.start, end: range.end } : {});
    owned = true;
    req.signal?.addEventListener("abort", () => stream.destroy(), { once: true });
    if (req.signal?.aborted) {
      stream.destroy();
      return new Response(null, { status: 499 });
    }
    const body = Readable.toWeb(stream) as unknown as ReadableStream<Uint8Array>;

    if (range) {
      return new Response(body, {
        status: 206,
        headers: {
          ...headers,
          "Content-Length": String(range.end - range.start + 1),
          "Content-Range": `bytes ${range.start}-${range.end}/${size}`,
        },
      });
    }
    return new Response(body, { status: 200, headers: { ...headers, "Content-Length": String(size) } });
  } catch {
    return notFound();
  } finally {
    if (!owned) await handle.close().catch(() => {});
  }
}
