// Runs the engine's real cue-track driver (public/mascot/driver.js) on tracks read from stdin and prints where
// it puts the mascot's feet at each requested frame, so a Python test can check tubematic_core/mascots.py
// (the validator's port of the same walk model) against the code that actually renders.
//   stdin:  { "tracks": [ { "cues": [...], "frames": [0, 10, ...] } ] }
//   stdout: [ [ { "frame": 0, "feet": [x, y] | null } ... ] ... ]
// driver.js needs only a few globals (W, H, easing helpers, emotion/jump helpers it never calls here), so it
// runs in a bare vm context without p5 or the kit.
import fs from "node:fs";
import vm from "node:vm";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const source = fs.readFileSync(path.join(here, "../public/mascot/driver.js"), "utf8");
const W = 560, H = 640, FEET_Y = H - 50;   // frame.html KIT_W / KIT_H, and driver.js FEET_Y = H - 50
const input = JSON.parse(fs.readFileSync(0, "utf8"));

const out = input.tracks.map(({ cues, frames }) => {
  const ctx = vm.createContext({
    W, H,
    clamp: (v, a, b) => Math.min(b, Math.max(a, v)),
    lerp: (a, b, k) => a + (b - a) * k,
    seg: (t, a, b) => Math.min(1, Math.max(0, (t - a) / (b - a))),
    ease: k => k * k * (3 - 2 * k),
    emotions: () => ({}), jump: () => ({ dy: 0, sq: 0 }),
  });
  ctx.window = ctx;
  ctx.TRACK = { fps: 30, width: 1080, height: 1920, cues };
  vm.runInContext(source, ctx);
  return frames.map(frame => {
    const p = ctx.placeAt(frame / 30);
    return { frame, feet: p ? [p.left + W / 2, p.top + FEET_Y] : null };
  });
});
process.stdout.write(JSON.stringify(out));
