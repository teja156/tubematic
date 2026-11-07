// Prints the kit CATALOG, every part a world may name, as markdown: kit kinds, promoted JSON parts, code parts
// (with their acts), promoted cast, and the gestures and holds the cast grammar knows. The authoring agent reads
// this instead of the source.
//   node catalog.mjs
import { installDomShim } from "../domShim";
import { ensureCodeBuilder } from "../parts";
installDomShim();
ensureCodeBuilder();
import { FIGURE_COATS, FIGURE_GESTURES, FIGURE_HATS, FIGURE_HOLDS } from "../../kit/Figure";
import { BOY_GESTURES } from "../../carrington/newsboy";
import { OP_GESTURES } from "../../carrington/operator";
import { deriveDims } from "../partGrammar";
import { CODE_PARTS } from "../partSpecs/code/index";
import { measureCodePart } from "../partSpecs/code/measure";
import { CODE_PROMOTED_NAMES, PART_DIMS, PART_INFO, PART_KINDS, PROMOTED } from "../partsSpec";
import * as fs from "node:fs";
import * as path from "node:path";
import type { FigureSpec } from "../../kit/Figure";

console.log("| part | w x h x d (m) | solid | walkable | what it is |\n|---|---|---|---|---|");
for (const k of PART_KINDS) {
  const d = PART_DIMS[k], i = PART_INFO[k];
  console.log(`| ${k} | ${d.w} x ${d.h} x ${d.d} | ${i.solid ? "yes" : "no"} | ${i.walkable ? "yes" : ""} | ${i.blurb}${i.smoke ? " (emits smoke)" : ""}${i.lightAtNight ? " (lit at night)" : ""} |`);
}
for (const [k, s] of Object.entries(PROMOTED)) {
  const d = deriveDims(s);
  console.log(`| ${k} (promoted) | ${d.w} x ${d.h} x ${d.d} | ${s.solid === false ? "no" : "yes"} | ${s.walkable ? "yes" : ""} | ${s.blurb} |`);
}
for (const [k, c] of Object.entries(CODE_PARTS)) {
  const d = measureCodePart(k);
  const acts = c.acts ? " acts: " + Object.entries(c.acts).map(([a, w]) => `${a} (${w})`).join("; ") : "";
  console.log(`| ${k} (code${CODE_PROMOTED_NAMES.includes(k) ? ", promoted" : ", needs the gate"}) | ${d.w} x ${d.h} x ${d.d} | ${c.solid === false ? "no" : "yes"} | ${c.walkable ? "yes" : ""} | ${c.blurb}${acts} |`);
}
// cast the gate promoted (gateCli --promote writes partSpecs/castPromoted.json): figures a world may copy by name
const castFile = path.join(path.resolve(process.env.REMOTION_ROOT ?? process.cwd()), "src/cartoon3d/probe2/partSpecs/castPromoted.json");
const cast = fs.existsSync(castFile) ? (JSON.parse(fs.readFileSync(castFile, "utf8")) as Record<string, FigureSpec>) : {};
if (Object.keys(cast).length) {
  console.log("\n| promoted cast | who |\n|---|---|");
  for (const [k, f] of Object.entries(cast)) console.log(`| ${k} | ${f.blurb} |`);
}
console.log(`\nGestures: newsboy ${BOY_GESTURES.join(", ")}; operator ${OP_GESTURES.join(", ")}; world.cast figures ${FIGURE_GESTURES.join(", ")}.`);
console.log(`Cast grammar: hats ${FIGURE_HATS.join(", ")}; holds ${FIGURE_HOLDS.join(", ")}; coats ${FIGURE_COATS.join(", ")}.`);
