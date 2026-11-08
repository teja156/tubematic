// The part gate (TMDEV-181): what an agent-made part must pass before a world
// may use it. Runs in Node inside the Remotion project; the gallery stills come
// through gate/stills.ts (the stills server, else the Remotion Node API).
//
//   node gate.mjs <scene-config.json | world.json> <outdir>            # check + stills + judge prompts
//   node gate.mjs <...> <outdir> --record <part> <answers.json> [--promote]   # store a judge's verdict
//   node gate.mjs <...> <outdir> --check                                      # which parts lack a PASS, as JSON; no stills
//
// For every part in the world's `parts`:
//   1. the deterministic check (partGrammar.ts validatePartSpec): shape, size,
//      materials, nothing floating. Fails here cost nothing.
//   2. two stills of gallery/PartGate.tsx: three-quarter and near end-on, with a
//      bystander and a crate beside the part for scale and style.
//   3. the judge: a SEPARATE model call that sees only the two stills and the
//      fixed prompt written to <outdir>/<part>-judge-prompt.md, and answers five
//      yes/no questions with reasons. In Claude Code that is a fresh subagent
//      (no key, no vendor, nothing of the author's context); its JSON answer
//      is stored with --record. Pass = all five yes.
//
// A part gets two judged attempts (two distinct specs under one name); the
// third is refused with "fall back to a kit part". A spec already judged
// returns its stored verdict. Verdicts and stills land in <outdir>/verdict.json;
// stage-config.ts refuses to write a scene-config whose parts lack a PASS for
// their current spec, so the judge cannot be skipped. --record ... --promote
// copies a passed part into partSpecs/promoted.json (+ its still), where every
// later world can name it.
//
// Env: REMOTION_ROOT (default: cwd); GATE_GL, CARTOON_BROWSER, STILLS_SERVER
// (see stills.ts).
import { installDomShim } from "../domShim";
import { ensureCodeBuilder } from "../parts";
installDomShim();
ensureCodeBuilder();
import * as fs from "node:fs";
import * as path from "node:path";
import { deriveDims, validatePartSpec, type PartSpec } from "../partGrammar";
import { PART_KINDS, RESERVED_PART_NAMES } from "../partsSpec";
import { measureCodePart, validateCodePart } from "../partSpecs/code/measure";
import { figureHeight } from "../../kit/Figure";
import { validateFigure } from "../../kit/figureCheck";
import { codeFileHash, gateSpecs, type GateSpec } from "./codeSpecs";
import { hashOf, QUESTIONS, readVerdicts, unpassed, type Answer, type Attempt, type Question, type Verdicts } from "./verdicts";
import { cartoonScene } from "../video/sceneConfig";
import { renderStills } from "./stills";
import { writeAtomic } from "./atomic";

const VIEWS = ["quarter", "end"] as const;
/** a cast figure gets a third still: the figure alone, close, so a moustache or a cap brim can be seen */
const FIGURE_VIEWS = ["quarter", "end", "close"] as const;
const MAX_ATTEMPTS = 2;
/** NAMES a world has had refused (failed the judge MAX_ATTEMPTS times) before no NEW name may be prepared: the
 *  per-name cap alone was sidestepped by passing a failed design under a new name. Counted by name, not attempt,
 *  so a round that tries six figures is not stopped after its third. */
const MAX_REFUSED_PER_WORLD = 8;

const args = process.argv.slice(2);
const flag = (f: string) => args.includes(f);
const recordAt = args.indexOf("--record");
const positional = args.filter((a, i) => !a.startsWith("--") && !(recordAt >= 0 && (i === recordAt + 1 || i === recordAt + 2)));
const [input, outdir] = positional;
if (!input || !outdir || (recordAt >= 0 && !(args[recordAt + 1] && args[recordAt + 2]))) {
  console.error("usage: gate <scene-config.json | world.json> <outdir> [--record <part> <answers.json>] [--promote]");
  process.exit(1);
}
const ROOT = path.resolve(process.env.REMOTION_ROOT ?? process.cwd());
const PROMOTE = flag("--promote");
const PROMOTED_FILE = path.join(ROOT, "src/cartoon3d/probe2/partSpecs/promoted.json");
const PROMOTED_DIR = path.join(ROOT, "src/cartoon3d/probe2/partSpecs/promoted");
const CODE_PROMOTED_FILE = path.join(ROOT, "src/cartoon3d/probe2/partSpecs/code/promoted.json");
const CAST_PROMOTED_FILE = path.join(ROOT, "src/cartoon3d/probe2/partSpecs/castPromoted.json");

const loaded = JSON.parse(fs.readFileSync(input, "utf8"));
const world = Array.isArray(loaded.scenes) ? cartoonScene(loaded).world : loaded;
const parts = gateSpecs(world, ROOT) as Record<string, GateSpec>;
const isCode = (spec: GateSpec) => typeof spec.code === "string";
const isFigure = (spec: GateSpec) => !!spec.figure;
const dimsOf = (spec: GateSpec) => (isFigure(spec) ? { w: 0.5, h: Math.round(figureHeight(spec.figure!) * 100) / 100, d: 0.1 } : isCode(spec) ? measureCodePart(spec.name) : deriveDims(spec));
fs.mkdirSync(outdir, { recursive: true });
const verdictFile = path.join(outdir, "verdict.json");
const verdicts: Verdicts = readVerdicts(verdictFile);
const save = () => writeAtomic(verdictFile, JSON.stringify(verdicts, null, 2));

const stillProps = (spec: GateSpec, view: (typeof FIGURE_VIEWS)[number]) =>
  isFigure(spec) ? { figure: spec.figure, figureName: spec.name, view } : isCode(spec) ? { code: spec.name, view } : { spec, view };

/** the fixed prompt the judge gets, and nothing else but the two stills */
const judgePrompt = (spec: GateSpec, stills: string[]) => {
  const d = dimsOf(spec);
  return [
    "You are the quality gate for a cartoon 3D prop library: flat saturated colours, bold ink outlines, chunky simplified shapes, the look of a narrated cartoon Short. You have no other context and must not ask for any.",
    isFigure(spec)
      ? `Look at these three renders (standing beside a townsman and a crate; mid-wave; then alone and close) of ONE new CHARACTER named "${spec.name}", ${d.h} m tall, which its author describes as: "${spec.blurb}". The HOUSE STYLE for people is a bean head, a rounded torso, single-stroke arms and legs with ink-dot hands and feet, and flat painted clothes: that is correct, not a flaw, and the townsman beside the figure is drawn the same way, so judge style against HIM, not against the crate. Judge whether a viewer would recognise that person from the description (role, period, clothes, what they hold), whether the outfit reads cleanly, and whether they sit with the townsman as the same cast.`
      : `Look at these two renders (three-quarter view, then nearly end-on) of ONE new prop named "${spec.name}", ${d.w} x ${d.h} x ${d.d} m, which its author describes as: "${spec.blurb}".`,
    ...stills.map((s) => `- ${s}`),
    isFigure(spec)
      ? "It stands on a dirt terrace. In the first two renders there is also, for scale and style only: the townsman (1.75 m) at one side, a wooden crate 0.8 m wide at the other, and a 1 m stick with four 25 cm bands in front. Judge only the new character."
      : "It stands on a dirt terrace. In every render there is also, for scale and style only: a flat cartoon bystander (a person 1.5-1.8 m tall) at one side, a wooden crate 0.8 m wide at the other, and a 1 m stick with four 25 cm bands in front. Judge only the new prop.",
    "Answer every question with ok (true/false) and one sentence why:",
    ...(Object.keys(QUESTIONS) as Question[]).map((q) => `- ${q}: ${QUESTIONS[q]}`),
    'Also give "seen": one line saying what the prop looks like to you, without using its name.',
    "Be strict but fair: a clean, simplified cartoon of the thing passes; a vague mass of boxes, a thing that only its author could name, or a shape with pieces hanging in the air does not.",
    "",
    "Write your answer as JSON only, exactly this shape, to the file named in your instructions:",
    JSON.stringify({ seen: "...", ...Object.fromEntries((Object.keys(QUESTIONS) as Question[]).map((q) => [q, { ok: true, why: "..." }])) }, null, 2),
  ].join("\n");
};

const promote = (spec: GateSpec, still: string) => {
  if (isFigure(spec)) {
    const all = (fs.existsSync(CAST_PROMOTED_FILE) ? JSON.parse(fs.readFileSync(CAST_PROMOTED_FILE, "utf8")) : {}) as Record<string, unknown>;
    all[spec.name] = spec.figure;
    writeAtomic(CAST_PROMOTED_FILE, JSON.stringify(all, null, 2) + "\n");
    fs.mkdirSync(PROMOTED_DIR, { recursive: true });
    fs.copyFileSync(still, path.join(PROMOTED_DIR, `${spec.name}.png`));
    return;
  }
  if (isCode(spec)) {
    const raw = fs.existsSync(CODE_PROMOTED_FILE) ? JSON.parse(fs.readFileSync(CODE_PROMOTED_FILE, "utf8")) : {};
    const map = (Array.isArray(raw) ? Object.fromEntries((raw as string[]).map((n) => [n, codeFileHash(n, ROOT)])) : raw) as Record<string, string>;
    map[spec.name] = codeFileHash(spec.name, ROOT);
    writeAtomic(CODE_PROMOTED_FILE, JSON.stringify(map, null, 2) + "\n");
    fs.mkdirSync(PROMOTED_DIR, { recursive: true });
    fs.copyFileSync(still, path.join(PROMOTED_DIR, `${spec.name}.png`));
    return;
  }
  const all = (fs.existsSync(PROMOTED_FILE) ? JSON.parse(fs.readFileSync(PROMOTED_FILE, "utf8")) : {}) as Record<string, PartSpec>;
  all[spec.name] = spec;
  writeAtomic(PROMOTED_FILE, JSON.stringify(all, null, 2) + "\n");
  fs.mkdirSync(PROMOTED_DIR, { recursive: true });
  fs.copyFileSync(still, path.join(PROMOTED_DIR, `${spec.name}.png`));
};

const show = (name: string, a: Attempt) => {
  console.log(`\n== ${name} == ${a.pass ? "PASS" : a.stage === "stills" ? "AWAITING JUDGE" : "FAIL"} (${a.stage})`);
  if (a.seen) console.log(`    seen: ${a.seen}`);
  if (a.answers) for (const q of Object.keys(QUESTIONS) as Question[]) console.log(`    ${a.answers[q].ok ? "yes" : "NO "} ${q}: ${a.answers[q].why}`);
  for (const e of a.errors ?? []) console.log(`    - ${e}`);
  if (a.stills) console.log(`    stills: ${a.stills.join(", ")}`);
  if (a.prompt) console.log(`    judge prompt: ${a.prompt}`);
};

/** steps 1 and 2 for one part; the judge comes back through --record */
const prepare = async (key: string, spec: GateSpec): Promise<Attempt> => {
  const hash = hashOf(spec);
  const at = new Date().toISOString();
  const errors = isFigure(spec) ? validateFigure(spec.name, spec.figure) : isCode(spec) ? validateCodePart(spec.name, [...PART_KINDS]) : validatePartSpec(spec, RESERVED_PART_NAMES);
  if (spec && typeof spec === "object" && spec.name !== key) errors.unshift(`parts["${key}"].name is "${spec.name}": the key and the name must match`);
  if (errors.length) return { at, hash, stage: "spec", pass: false, errors };
  const views = isFigure(spec) ? FIGURE_VIEWS : VIEWS;
  const stills = views.map((v) => path.join(outdir, `${spec.name}-${v}.png`));
  try {
    await renderStills(ROOT, views.map((v, i) => ({ composition: "Cartoon3DPartGate", props: stillProps(spec, v), frame: 0, out: stills[i] })), 0.5);
  } catch (e) {
    return { at, hash, stage: "render", pass: false, errors: [String((e as Error).message)], stills };
  }
  const prompt = path.join(outdir, `${spec.name}-judge-prompt.md`);
  fs.writeFileSync(prompt, judgePrompt(spec, stills));
  return { at, hash, stage: "stills", pass: false, stills, prompt, errors: [`look at the stills yourself first, then have a fresh judge answer ${path.basename(prompt)} and store it with --record ${spec.name} <answers.json>`] };
};

/** step 3: a judge's answers for the part's current spec */
const record = (name: string, answersFile: string) => {
  const spec = parts[name];
  if (!spec) throw new Error(`no part "${name}" in this world`);
  const rec = (verdicts.parts[name] ??= { pass: false, attempts: [] });
  const hash = hashOf(spec);
  const prepared = rec.attempts.find((a) => a.hash === hash && a.stage === "stills");
  if (!prepared) throw new Error(`"${name}" has no stills for its current spec: run the gate first`);
  const judged = rec.attempts.filter((a) => a.stage === "judge");
  if (judged.some((a) => a.hash === hash)) throw new Error(`"${name}" already has a verdict for this exact spec: change the spec, or use the verdict you have`);
  if (judged.filter((a) => !a.pass).length >= MAX_ATTEMPTS && !rec.pass) {
    throw new Error(`"${name}" has failed the judge ${MAX_ATTEMPTS} times: fall back to a kit part (or a promoted one) and drop this spec`);
  }
  const raw = JSON.parse(fs.readFileSync(answersFile, "utf8")) as { seen?: unknown } & Partial<Record<Question, Partial<Answer>>>;
  const answers = {} as Record<Question, Answer>;
  for (const q of Object.keys(QUESTIONS) as Question[]) {
    const a = raw[q];
    if (!a || typeof a.ok !== "boolean" || typeof a.why !== "string" || !a.why.trim()) throw new Error(`answers.${q} must be {ok: true|false, why: "..."}`);
    answers[q] = { ok: a.ok, why: a.why };
  }
  const a: Attempt = {
    at: new Date().toISOString(), hash, stage: "judge", judge: "harness", seen: String(raw.seen ?? ""), answers,
    pass: (Object.keys(QUESTIONS) as Question[]).every((q) => answers[q].ok), stills: prepared.stills,
  };
  rec.attempts.push(a);
  rec.pass = a.pass;
  save();
  show(name, a);
  if (a.pass && PROMOTE && a.stills) {
    promote(spec, a.stills[0]);
    console.log(`    promoted into ${path.relative(ROOT, isFigure(spec) ? CAST_PROMOTED_FILE : isCode(spec) ? CODE_PROMOTED_FILE : PROMOTED_FILE)}`);
  }
  return a.pass;
};

const main = async () => {
  if (flag("--check")) {
    // the enforcement's question, answered without rendering: which parts of this world have no PASS for the spec
    // the world carries now (gate/verdicts.ts unpassed, the same function the stager uses)
    const missing = unpassed(parts, verdicts);
    const state = Object.fromEntries(Object.keys(parts).map((n) => {
      const rec = verdicts.parts[n], h = hashOf(parts[n]);
      const judged = rec?.attempts.filter((a) => a.hash === h && a.stage === "judge") ?? [];
      const prepared = rec?.attempts.find((a) => a.hash === h && a.stage === "stills");
      return [n, judged.some((a) => a.pass) ? "pass" : judged.length ? "fail" : prepared ? "awaiting judge" : "unjudged"];
    }));
    console.log(JSON.stringify({ unpassed: missing, parts: state }));
    process.exit(missing.length ? 2 : 0);
  }
  if (recordAt >= 0) {
    const ok = record(args[recordAt + 1], args[recordAt + 2]);
    console.log(`\nverdicts: ${verdictFile}`);
    process.exit(ok ? 0 : 2);
  }
  let allPass = true;
  const names = Object.keys(parts);
  if (!names.length) console.log("no agent-made parts in this world (JSON or code): nothing to gate");
  if (PROMOTE && recordAt < 0) {
    // `gate ... --promote` alone: promote every part that already holds a PASS for its current spec
    for (const name of names) {
      const rec = verdicts.parts[name];
      const a = rec?.attempts.find((x) => x.stage === "judge" && x.pass && x.hash === hashOf(parts[name]));
      if (a?.stills) { promote(parts[name], a.stills[0]); console.log(`${name}: promoted (judged PASS ${a.at})`); }
      else console.log(`${name}: not promoted (no PASS for its current spec)`);
    }
    process.exit(0);
  }
  const refused = () => Object.values(verdicts.parts).filter((r) => !r.pass && r.attempts.filter((a) => a.stage === "judge" && !a.pass).length >= MAX_ATTEMPTS).length;
  for (const name of names) {
    const spec = parts[name];
    const rec = (verdicts.parts[name] ??= { pass: false, attempts: [] });
    const hash = hashOf(spec);
    if (!rec.attempts.length && refused() >= MAX_REFUSED_PER_WORLD) {
      const a: Attempt = { at: new Date().toISOString(), hash, stage: "spec", pass: false, errors: [`this world has already had ${refused()} names refused by the judge: no new part may be gated; fall back to kit or promoted parts (a failed design under a new name is still a failed design)`] };
      rec.attempts.push(a); save(); allPass = false; show(name, a); continue;
    }
    const judged = rec.attempts.find((a) => a.hash === hash && a.stage === "judge");
    const prepared = rec.attempts.find((a) => a.hash === hash && a.stage === "stills");
    let a: Attempt;
    if (judged) {
      a = judged;
      console.log(`${name}: unchanged since its verdict, not re-rendered`);
    } else if (prepared && prepared.stills?.every((s) => fs.existsSync(s))) {
      a = prepared;
      console.log(`${name}: stills already rendered for this spec`);
    } else if (rec.attempts.filter((x) => x.stage === "judge" && !x.pass).length >= MAX_ATTEMPTS && !rec.pass) {
      a = { at: new Date().toISOString(), hash, stage: "spec", pass: false, errors: [`"${name}" has failed the judge ${MAX_ATTEMPTS} times: fall back to a kit part (or a promoted one) and drop this spec`] };
      rec.attempts.push(a);
    } else {
      a = await prepare(name, spec);
      rec.attempts.push(a);
    }
    rec.pass = a.pass;
    save();
    allPass &&= a.pass;
    show(name, a);
  }
  console.log(`\nverdicts: ${verdictFile}`);
  process.exit(allPass ? 0 : 2);
};

main().catch((e) => {
  console.error(String((e as Error).message ?? e));
  process.exit(1);
});
