// The gate's verdict file: what gateCli.ts writes and stage-config.ts reads.
// Pure (Node), no DOM.
import { createHash } from "node:crypto";
import * as fs from "node:fs";

/** the five fixed questions every judge answers, with the reason for each */
export const QUESTIONS = {
  recognisable: "would a viewer name it as the thing it claims to be without being told?",
  grounded: "nothing floats, intersects wrongly or sinks into the ground; it reads as one solid object",
  silhouette: "the shape still reads with the ink outline at this size: not a blob, not a tangle of sticks",
  scale: "a plausible size against the bystander and the crate for what it is",
  style: "colour and shape sit with the crate and the bystander as one kit: flat saturated colour, chunky simplified shapes, bold outline; not photoreal, not a different cartoon",
} as const;
export type Question = keyof typeof QUESTIONS;

export interface Answer { ok: boolean; why: string }
export interface Attempt {
  at: string;
  /** of the spec as judged, so an unchanged spec is never re-judged */
  hash: string;
  stage: "spec" | "render" | "stills" | "judge";
  pass: boolean;
  errors?: string[];
  seen?: string;
  answers?: Record<Question, Answer>;
  stills?: string[];
  prompt?: string;
  judge?: string;
}
export interface Verdicts { parts: Record<string, { pass: boolean; attempts: Attempt[] }> }

export const hashOf = (spec: unknown) => createHash("sha256").update(JSON.stringify(spec)).digest("hex").slice(0, 12);

export const readVerdicts = (file: string): Verdicts => (fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, "utf8")) : { parts: {} });

/** the parts of `parts` that have no PASS verdict for their current spec */
export const unpassed = (parts: Record<string, unknown>, v: Verdicts): string[] =>
  Object.entries(parts)
    .filter(([name, spec]) => !v.parts[name]?.attempts.some((a) => a.stage === "judge" && a.pass && a.hash === hashOf(spec)))
    .map(([name]) => name);
