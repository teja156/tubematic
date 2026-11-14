// The directory a stills render serves as /public/: the jobs volume (a video's files are /public/<video>/...) merged
// with the project's own public/ (fonts, watermark.png, the built-in mascots), as a render's staging gives them.
// Served from the jobs volume alone, every webfont 404s and the watermark image fails the frame, so a preview of
// a video would draw its text in a fallback font. Folders are symlinks and the few plain files are copies;
// nothing the server writes goes through it (out-path.mjs checks real paths under the jobs volume).
import fs from "node:fs";
import path from "node:path";

/** make `merged` hold one symlink per entry of `jobsDir`, then one per entry of `projectPublic` the jobs volume
 *  has no entry of; links whose entry is gone are removed. Cheap (two directory reads): run it before every request,
 *  since videos appear in the jobs volume while the bundle lives. */
export const syncMergedPublic = (merged, jobsDir, projectPublic) => {
  const want = new Map();
  const add = (dir) => {
    let names;
    try { names = fs.readdirSync(dir); } catch { return; }
    for (const name of names) if (!want.has(name)) want.set(name, path.join(dir, name));
  };
  add(jobsDir);
  add(projectPublic);
  fs.mkdirSync(merged, { recursive: true });
  for (const name of fs.readdirSync(merged)) {
    if (!want.has(name) || (!isLink(path.join(merged, name)) && isDir(want.get(name)))) {
      fs.rmSync(path.join(merged, name), { recursive: true, force: true });
    }
  }
  for (const [name, source] of want) {
    const dest = path.join(merged, name);
    if (isDir(source)) {
      if (isLink(dest) && fs.readlinkSync(dest) === source) continue;
      fs.rmSync(dest, { recursive: true, force: true });
      fs.symlinkSync(source, dest);
    } else if (!sameFile(source, dest)) {
      // a plain file is copied: Remotion's static server answers 404 for a symlinked file
      fs.rmSync(dest, { recursive: true, force: true });
      fs.copyFileSync(source, dest);
    }
  }
};

const isLink = (p) => { try { return fs.lstatSync(p).isSymbolicLink(); } catch { return false; } };
const isDir = (p) => { try { return fs.statSync(p).isDirectory(); } catch { return false; } };
const sameFile = (a, b) => {
  try {
    const x = fs.statSync(a), y = fs.lstatSync(b);
    return y.isFile() && x.size === y.size && x.mtimeMs <= y.mtimeMs;
  } catch { return false; }
};
