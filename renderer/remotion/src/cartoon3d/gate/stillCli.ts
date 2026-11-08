// Full-composition STILLS of a staged video (world + captions + watermark), the frames the author asks to see.
//   node still.mjs <dir> <outdir> frame...
// <dir> is the staged public directory (scene-config.json, timeline.json, audio.mp3); BEAT_PROPS overrides the
// Composition props (default: built from <dir>'s name under public/). Writes <outdir>/fNNNN.png at half size.
import * as fs from "node:fs";
import * as path from "node:path";
import { renderStills } from "../gate/stills";

const [dir, outdir, ...rest] = process.argv.slice(2);
const frames = rest.map((f) => Number(f)).filter((f) => Number.isInteger(f) && f >= 0);
if (!dir || !outdir || !frames.length) {
  console.error("usage: still <dir> <outdir> frame...");
  process.exit(1);
}
const ROOT = path.resolve(process.env.REMOTION_ROOT ?? process.cwd());
const pubName = path.basename(dir);
const props = JSON.parse(process.env.BEAT_PROPS ?? JSON.stringify({
  sceneConfigPath: `/public/${pubName}/scene-config.json`, timelinePath: `/public/${pubName}/timeline.json`, audioPath: `/public/${pubName}/audio.mp3`, watermark: false,
}));
fs.mkdirSync(outdir, { recursive: true });
const outs = frames.map((f) => path.join(outdir, `f${String(f).padStart(4, "0")}.png`));
renderStills(ROOT, frames.map((f, i) => ({ composition: "Composition", props, frame: f, out: outs[i] })), 0.5)
  .then(() => { console.log(JSON.stringify({ stills: outs })); })
  .catch((e) => { console.error(String((e as Error).message ?? e)); process.exit(1); });
