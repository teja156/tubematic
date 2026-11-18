// What the beat gate's verdict is keyed by (beatGateCli.ts): the video's source files, and, for a video in an
// installed external style (TMDEV-253), every file of each package its source imports. A package updated after
// the judges answered changes what the frames show, so it needs fresh judges like an edit to the source does.
import { createHash } from "node:crypto";
import * as fs from "node:fs";
import * as path from "node:path";

/** every file under root, by relative path, in a fixed order */
export const filesOf = (root: string): [string, string][] => {
  const out: [string, string][] = [];
  const walk = (d: string) => {
    for (const e of fs.readdirSync(d, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      const p = path.join(d, e.name);
      if (e.isDirectory()) walk(p);
      else if (e.isFile()) out.push([path.relative(root, p), fs.readFileSync(p, "utf8")]);
    }
  };
  walk(root);
  return out;
};

/** the external packages the source imports, by id (`…/external/ext_x/runner/…`) */
export const importedPackages = (source: [string, string][]): string[] => {
  const ids = new Set<string>();
  for (const [, text] of source) {
    for (const m of text.matchAll(/["'][^"'\n]*\bexternal\/(ext_[a-z0-9_]{1,40})\//g)) ids.add(m[1]);
  }
  return [...ids].sort();
};

/** every file under root by relative path and the sha256 of its bytes: a package holds binary assets too, and
 * reading those as text maps different bytes to the same replacement characters */
export const hashesOf = (root: string): [string, string][] => {
  const out: [string, string][] = [];
  const walk = (d: string) => {
    for (const e of fs.readdirSync(d, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      const p = path.join(d, e.name);
      if (e.isDirectory()) walk(p);
      else if (e.isFile()) out.push([path.relative(root, p), createHash("sha256").update(fs.readFileSync(p)).digest("hex")]);
    }
  };
  walk(root);
  return out;
};

/** the key's material: built-in videos keep the exact shape they had, so their recorded verdicts stay valid */
export const keyMaterial = (srcdir: string, externalRoot: string, extra: Record<string, unknown>): string => {
  const source = filesOf(srcdir);
  const packages = importedPackages(source).map((id) => {
    const dir = path.join(externalRoot, id);
    return [id, fs.existsSync(dir) ? hashesOf(dir) : []] as const;
  });
  return JSON.stringify(packages.length ? { source, ...extra, packages } : { source, ...extra });
};
