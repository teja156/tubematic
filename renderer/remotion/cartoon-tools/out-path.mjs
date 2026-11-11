// Where the stills server may write. Its port takes requests from anything on the Compose network with no
// credential, and in production its public directory is the read-write /jobs volume, so a request may only write
// a PNG under <public>/<video>/cartoon/, where the Cartoon 3D tools keep their stills (TMDEV-208).
import path from "node:path";

/** why `p` may not be written (null when it may); `dir` checks a directory that PNGs will be written into */
export const outPathError = (publicDir, p, { dir = false } = {}) => {
  if (typeof p !== "string" || !p) return "no output path was given";
  const rel = path.relative(path.resolve(publicDir), path.resolve(p));
  const parts = rel.split(path.sep);
  const inCartoon = !path.isAbsolute(rel) && parts[0] !== ".." && parts[0] !== "" && parts[1] === "cartoon";
  if (!inCartoon || parts.length < (dir ? 2 : 3)) return `${p} is not under ${path.join(publicDir, "<video>", "cartoon")}`;
  if (!dir && !p.endsWith(".png")) return `${p} is not a .png file`;
  return null;
};
