// Code parts as the gate and the stager see them: a pseudo-spec whose hash is the hash of the part's SOURCE FILE,
// so a verdict is tied to exactly the code that was judged. Node only (reads the file).
import { createHash } from "node:crypto";
import * as fs from "node:fs";
import * as path from "node:path";
import type { PartSpec } from "../partGrammar";
import { CODE_PARTS, codePartFile } from "../partSpecs/code/index";
import { CODE_PROMOTED } from "../partsSpec";
import { codePartsUsed } from "../qa";
import type { WorldSpec } from "../worldKit";

import type { FigureSpec } from "../../kit/Figure";
export type GateSpec = PartSpec & { code?: string; figure?: FigureSpec };

/** the part's source and, transitively, every sibling it imports with a relative path (a shared steamboatKit.ts
 *  edited under one promoted boat changes both boats' hashes, so both are judged again) */
const codeSources = (file: string, seen = new Set<string>()): string[] => {
  if (seen.has(file) || !fs.existsSync(file)) return [];
  seen.add(file);
  const src = fs.readFileSync(file, "utf8");
  const out = [src];
  for (const m of src.matchAll(/from\s+["'](\.{1,2}\/[^"']+)["']/g)) {
    const rel = m[1];
    const base = path.resolve(path.dirname(file), rel);
    const cand = [base, `${base}.ts`, `${base}.tsx`, path.join(base, "index.ts")].find((c) => fs.existsSync(c) && fs.statSync(c).isFile());
    if (cand && !/\/(types|index|measure)\.ts$/.test(cand)) out.push(...codeSources(cand, seen));
  }
  return out;
};
export const codeFileHash = (name: string, root: string) => {
  const file = path.join(root, codePartFile(name));
  return createHash("sha256").update(codeSources(file).join("\n---\n")).digest("hex").slice(0, 12);
};
export const codeGateSpec = (name: string, root: string): GateSpec => ({ name, blurb: CODE_PARTS[name]?.blurb ?? "", prims: [], code: codeFileHash(name, root) });

/** a code part counts as promoted only while its source still hashes to what the judge saw */
export const isCodePromoted = (name: string, root: string) => CODE_PROMOTED[name] !== undefined && CODE_PROMOTED[name] === codeFileHash(name, root);

/** every part this world must have a verdict for: its JSON parts plus the code parts it uses that are not promoted
 *  (or were promoted as a different version of their file) */
export const gateSpecs = (world: WorldSpec, root: string): Record<string, GateSpec> => ({
  ...(world.parts ?? {}),
  ...Object.fromEntries(codePartsUsed(world).filter((n) => !isCodePromoted(n, root)).map((n) => [n, codeGateSpec(n, root)])),
  ...Object.fromEntries(Object.entries(world.cast ?? {}).map(([n, f]) => [n, { name: n, blurb: f.blurb, prims: [], figure: f } as GateSpec])),
});
