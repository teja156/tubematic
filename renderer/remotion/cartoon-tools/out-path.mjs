// Where the stills server may write. Its port takes requests from anything on the Compose network with no
// credential, and in production its public directory is the read-write /jobs volume, so a request may only write
// a PNG under <public>/<video>/cartoon/, where the Cartoon 3D tools keep their stills (TMDEV-208).
import fs from "node:fs";
import path from "node:path";

/** the first part of `rel` below `publicDir` that is a symlink (dangling or not), or null: a planted link could
 *  carry a write out of the public directory, so none is followed (the rule mcp/cartoon.py::_below keeps too) */
const linkIn = (publicDir, rel) => {
  let at = path.resolve(publicDir);
  for (const part of rel.split(path.sep)) {
    at = path.join(at, part);
    let st;
    try {
      st = fs.lstatSync(at);
    } catch {
      return null;           // not created yet, so nothing below it exists either
    }
    if (st.isSymbolicLink()) return at;
  }
  return null;
};

/** why `p` may not be written (null when it may); `dir` checks a directory that PNGs will be written into */
export const outPathError = (publicDir, p, { dir = false } = {}) => {
  if (typeof p !== "string" || !p) return "no output path was given";
  const rel = path.relative(path.resolve(publicDir), path.resolve(p));
  const parts = rel.split(path.sep);
  const inCartoon = !path.isAbsolute(rel) && parts[0] !== ".." && parts[0] !== "" && parts[1] === "cartoon";
  if (!inCartoon || parts.length < (dir ? 2 : 3)) return `${p} is not under ${path.join(publicDir, "<video>", "cartoon")}`;
  if (!dir && !p.endsWith(".png")) return `${p} is not a .png file`;
  const link = linkIn(publicDir, rel);
  return link ? `${p} goes through the symlink ${link}` : null;
};

const isFrame = (f) => Number.isInteger(f) && f >= 0;

/** the frames a /still or /stills request draws and the file each goes to, checked; {error} when any is refused.
 *  The server writes exactly these targets, so what is checked is what is written. */
export const planRequest = (publicDir, route, b) => {
  if (route === "/still") {
    const frame = b.frame ?? 0;
    if (!isFrame(frame)) return { error: "frame must be a non-negative integer" };
    const error = outPathError(publicDir, b.out);
    return error ? { error } : { targets: [{ frame, out: b.out }] };
  }
  if (!Array.isArray(b.frames) || !b.frames.length || !b.frames.every(isFrame)) {
    return { error: "frames must be a non-empty list of non-negative integers" };
  }
  const dirError = outPathError(publicDir, b.outDir, { dir: true });
  if (dirError) return { error: dirError };
  const prefix = b.prefix ?? "f";
  if (typeof prefix !== "string") return { error: "prefix must be a string" };
  const targets = b.frames.map((frame) => ({ frame, out: path.join(b.outDir, `${prefix}${String(frame).padStart(4, "0")}.png`) }));
  const error = targets.map((t) => outPathError(publicDir, t.out)).find((e) => e);
  return error ? { error } : { targets };
};
