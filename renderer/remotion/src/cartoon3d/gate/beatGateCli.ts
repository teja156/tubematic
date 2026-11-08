// The BEAT GATE: does each beat's frame show what its sentence says? One still at the middle of every beat, the
// sentence the voice speaks during it (from timeline.json), and a fixed prompt for FRESH judge subagents that
// answer per beat. The verdict is keyed by a hash of the video's SOURCE FILES (the agent's TypeScript under
// scenes/generated/<video_id>/), its beats and the narration per beat, so a changed shot is judged again and an
// unchanged one is not. submit_render refuses without a PASS.
//
// TWO judges answer the same prompt; a beat they split on goes to a third and the majority decides
// (beatVerdict.ts). Every judge's answers are recorded; the verdict is derived from all of them.
//
//   node beatgate.mjs <dir> <outdir> --source <srcdir>                      # stills + prompt
//   node beatgate.mjs <dir> <outdir> --source <srcdir> --record <answers.json>
//   node beatgate.mjs <dir> <outdir> --source <srcdir> --status             # the verdict as JSON, no render
//
// <dir> is the video's job directory (scene-config.json, timeline.json, audio.mp3); <srcdir> the directory of the
// video's generated source files, every file of which is hashed into the verdict's key.
//
// Env: REMOTION_ROOT, GATE_GL, CARTOON_BROWSER, STILLS_SERVER (see stills.ts); BEAT_PROPS (the Composition's --props
// JSON, so the still is the real frame with captions; default: built from <dir>'s name under public/).
import { createHash } from "node:crypto";
import * as fs from "node:fs";
import * as path from "node:path";
import { beatGateStatus, describeStatus, type BeatAnswer, type JudgeRecord } from "./beatVerdict";
import { renderStills } from "./stills";
import { cartoonScene } from "./sceneConfig";
import { writeAtomic } from "./atomic";

const args = process.argv.slice(2);
const recordAt = args.indexOf("--record");
const sourceAt = args.indexOf("--source");
const positional = args.filter((a, i) => !a.startsWith("--") && !(recordAt >= 0 && i === recordAt + 1) && !(sourceAt >= 0 && i === sourceAt + 1));
const [dir, outdir] = positional;
const srcdir = sourceAt >= 0 ? args[sourceAt + 1] : "";
if (!dir || !outdir || !srcdir) {
  console.error("usage: beatgate <dir> <outdir> --source <srcdir> [--record <answers.json> | --status]");
  process.exit(1);
}
const ROOT = path.resolve(process.env.REMOTION_ROOT ?? process.cwd());
const read = (n: string) => JSON.parse(fs.readFileSync(path.join(dir, n), "utf8"));
const { beats } = cartoonScene(read("scene-config.json"));
const timeline = read("timeline.json") as { fps: number; words: { word: string; startFrame: number; endFrame: number }[] };
const sentenceOf = (b: { start: number; end: number }) =>
  timeline.words.filter((w) => w.startFrame <= b.end && w.endFrame >= b.start).map((w) => w.word).join(" ");
/** every source file of the video, by relative path, in a fixed order */
const sourceFiles = (root: string): [string, string][] => {
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
// the verdict is about THIS code showing THESE sentences at THESE frames: an edit to the video's source, to its beats
// or a re-voiced narration changes the question, so all three are the key
const hash = createHash("sha256").update(JSON.stringify({ source: sourceFiles(srcdir), beats, sentences: beats.map(sentenceOf) })).digest("hex").slice(0, 12);
fs.mkdirSync(outdir, { recursive: true });
const verdictFile = path.join(outdir, "beat-verdict.json");
type Verdict = { hash: string; at: string; pass: boolean; stage: "stills" | "judge"; answers?: BeatAnswer[]; stills: string[]; prompt?: string };
const verdicts: Verdict[] = fs.existsSync(verdictFile) ? JSON.parse(fs.readFileSync(verdictFile, "utf8")) : [];
const judgesFor = (h: string): JudgeRecord[] => verdicts.filter((v): v is Verdict & { answers: BeatAnswer[] } => v.hash === h && v.stage === "judge" && !!v.answers).map((v) => ({ at: v.at, answers: v.answers }));
const status = () => beatGateStatus(judgesFor(hash), beats.length);

const mids = beats.map((b) => Math.round((b.start + b.end) / 2));
const stills = mids.map((m, i) => path.join(outdir, `beat${String(i).padStart(2, "0")}-f${String(m).padStart(4, "0")}.png`));

const pubName = path.basename(dir);
const props = process.env.BEAT_PROPS ?? JSON.stringify({
  sceneConfigPath: `/public/${pubName}/scene-config.json`, timelinePath: `/public/${pubName}/timeline.json`, audioPath: `/public/${pubName}/audio.mp3`, watermark: false,
});

const prompt = () => [
  "You are the continuity judge for a narrated cartoon Short. You have no other context and must not ask for any.",
  "For each beat below you get the sentence the narrator speaks and ONE frame from the middle of that beat (a vertical 1080x1920 frame at half size, captions burned in). Judge whether the PICTURE shows what the SENTENCE says: the thing or action named in the sentence must be visible and be the subject of the frame. A character merely reacting (pointing, shrugging, cheering) while the sentence names an object, place or event that is not on screen is a FAIL. An establishing or mood shot passes only if the sentence is about mood or place.",
  "",
  ...beats.map((b, i) => `Beat ${i} (frames ${b.start}-${b.end}, shot "${b.shot}"): sentence: "${sentenceOf(b)}"\n  frame: ${stills[i]}`),
  "",
  "Write your answer as JSON only, exactly this shape (one entry per beat, in order), to the file named in your instructions:",
  JSON.stringify({ beats: beats.map((_b, i) => ({ beat: i, seen: "one line: what the frame shows, without the sentence", shows: true, why: "one sentence", fix: "if shows is false: what should be on screen instead" })) }, null, 2),
].join("\n");

const main = async () => {
  if (args.includes("--status")) {
    const s = status();
    const prepared = verdicts.find((v) => v.hash === hash && v.stage === "stills");
    console.log(JSON.stringify({ hash, ...s, summary: describeStatus(s, beats.length), beats: beats.length, prompt: prepared?.prompt ?? null, stills: prepared?.stills ?? [] }));
    process.exit(s.pass ? 0 : 2);
  }
  if (recordAt >= 0) {
    const raw = JSON.parse(fs.readFileSync(args[recordAt + 1], "utf8")) as { beats: (BeatAnswer & { beat: number })[] };
    const prepared = verdicts.find((v) => v.hash === hash && v.stage === "stills");
    if (!prepared) throw new Error("no stills for the current source/beats: run the beat gate first");
    if (!Array.isArray(raw.beats) || raw.beats.length !== beats.length) throw new Error(`answers.beats must have ${beats.length} entries`);
    const answers = raw.beats.map((a, i) => {
      if (typeof a.shows !== "boolean" || !a.why) throw new Error(`beats[${i}] must have shows (boolean) and why`);
      return { shows: a.shows, why: a.why, seen: String(a.seen ?? ""), fix: a.fix };
    });
    const before = status();
    if (!before.need) throw new Error(`the judges have already decided for this source/beats (${describeStatus(before, beats.length)}); a verdict is recorded once`);
    const dup = verdicts.find((v) => v.hash === hash && v.stage === "judge" && JSON.stringify(v.answers) === JSON.stringify(answers));
    if (dup) throw new Error(`these exact answers are already recorded for this source/beats (${dup.at}); a second judge is a different, fresh judge`);
    const v: Verdict = { hash, at: new Date().toISOString(), pass: answers.every((a) => a.shows), stage: "judge", answers, stills: prepared.stills };
    verdicts.push(v);
    writeAtomic(verdictFile, JSON.stringify(verdicts, null, 2));
    answers.forEach((a, i) => console.log(`${a.shows ? "yes" : "NO "} beat ${i}: ${a.why}${a.fix ? `  -> ${a.fix}` : ""}`));
    const s = status();
    console.log(`\n${describeStatus(s, beats.length)} (hash ${hash})`);
    if (s.need) console.log(`judge prompt: ${prepared.prompt}`);
    process.exit(s.pass ? 0 : 2);
  }
  const s = status();
  if (!s.need) {
    console.log(`beats and source unchanged since their verdict: ${describeStatus(s, beats.length)} (hash ${hash}); not re-rendered`);
    process.exit(s.pass ? 0 : 2);
  }
  const prepared = verdicts.find((v) => v.hash === hash && v.stage === "stills");
  if (prepared && prepared.stills.every((st) => fs.existsSync(st))) {
    console.log(`stills already rendered for this source/beats (hash ${hash}); ${describeStatus(s, beats.length)}: ${prepared.prompt}`);
    process.exit(2);
  }
  await renderStills(ROOT, mids.map((m, i) => ({ composition: "Composition", props: JSON.parse(props), frame: m, out: stills[i] })), 0.5);
  const p = path.join(outdir, "beat-judge-prompt.md");
  fs.writeFileSync(p, prompt());
  verdicts.push({ hash, at: new Date().toISOString(), pass: false, stage: "stills", stills, prompt: p });
  writeAtomic(verdictFile, JSON.stringify(verdicts, null, 2));
  console.log(`${beats.length} beat stills in ${outdir}; look at them yourself first, then have TWO fresh judges answer ${p}, each stored with --record`);
  process.exit(2);
};

main().catch((e) => {
  console.error(String((e as Error).message ?? e));
  process.exit(1);
});
