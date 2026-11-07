// PROBE 2 round 3 — the look: sky, light and grade as functions of time of day,
// nudged per world by a small `Look` the agent can set.
//
// Round 4 (the "slick" pass): the storybook palette had drifted into a hazy,
// low-contrast sepia. The target look is a clean cartoon: a vivid blue day
// sky, a strong warm sun with real shadows, clean near-black blacks, and
// saturated flat colours. Night is a stylised bright blue night, not darkness.
import * as THREE from "three";
import type { Grade } from "../kit/InkPipeline";
import { lerp } from "../kit/prng";

/** The agent's per-world grade knobs. All optional; absent = the house look. */
export interface Look {
  /** -1 cool .. +1 warm. Shifts key light, highlights and shadows. */
  warmth?: number;
  /** grade saturation; 1 = neutral (round 2 effectively ran 1.3) */
  saturation?: number;
  contrast?: number;
  /** strength of the characters' back-light rim, 0..1 */
  rim?: number;
  /** pull the sky's hue toward this (0..360) by skyAmount 0..1 */
  skyHue?: number;
  skyAmount?: number;
}

const C = (r: number, g: number, b: number) => new THREE.Color(r, g, b);
/** an ON-SCREEN sRGB colour as the scene value that lands there after the output encode (the scene is colour-
 *  unmanaged, so a hex would otherwise be taken as linear and come out far lighter and paler) */
export const S = (hex: number) => {
  const c = new THREE.Color(hex);
  return c.setRGB(Math.pow(c.r, 2.2), Math.pow(c.g, 2.2), Math.pow(c.b, 2.2));
};
/** time-of-day keys: day, sunset, dusk, night */
const KEYS = [0, 0.5, 0.8, 1];
/** Day holds: the day -> sunset segment eases in (t^2), so a video whose clock runs 0.05..0.48 spends its first
 *  half under a day sky and only the last third turns gold. Linear mixing had the sunset top showing 44 % through
 *  by mid-video, which read as a violet day sky. */
const warp = (tod: number) => (tod <= 0.5 ? 0.5 * Math.pow(tod / 0.5, 2.6) : tod);
export const pal = (vals: THREE.Color[], tod: number) => {
  tod = warp(tod);
  for (let i = 0; i < KEYS.length - 1; i++) {
    if (tod <= KEYS[i + 1]) return vals[i].clone().lerp(vals[i + 1], (tod - KEYS[i]) / (KEYS[i + 1] - KEYS[i]));
  }
  return vals[vals.length - 1].clone();
};
export const num = (vals: number[], tod: number) => {
  tod = warp(tod);
  for (let i = 0; i < KEYS.length - 1; i++) {
    if (tod <= KEYS[i + 1]) return lerp(vals[i], vals[i + 1], (tod - KEYS[i]) / (KEYS[i + 1] - KEYS[i]));
  }
  return vals[vals.length - 1];
};

const tintHue = (c: THREE.Color, look: Look) => {
  if (look.skyHue === undefined || !look.skyAmount) return c;
  const h = { h: 0, s: 0, l: 0 };
  c.getHSL(h);
  const target = (look.skyHue % 360) / 360;
  let d = target - h.h;
  if (d > 0.5) d -= 1;
  if (d < -0.5) d += 1;
  return c.setHSL((h.h + d * look.skyAmount + 1) % 1, h.s, h.l);
};

// Sky stops are the reference's measured ON-SCREEN colours (LOOK-TARGETS.md 6): day upper #3e7fd2 (C* ~50),
// horizon #9fb6e6; sunset violet-blue top #8c78c4 (the 32 deg stop) down to a peach horizon #ffc47c. The old palette and a 50 % cloud cover
// measured C* 20-26 at the frame top against >= 45, in every post variant.
/** how far the look is into GOLDEN HOUR, 0 (day) .. 1 (the full peach-and-violet sunset preset): one curve for the
 *  sky stops, the key, the two-tone shade and the grade, so a beat's `tod` of 0.5 is the whole golden look at once
 *  (the day -> golden sky blend passes through a grey lavender midway, so a video wants either end, chosen per beat) */
export const goldAmount = (tod: number) => Math.max(0, Math.min(1, (warp(tod) - 0.16) / 0.34));

/** the sky as SIX colour stops by elevation (degrees): the reference's golden sky is a 4-stop ramp with a peach band
 *  that holds to ~3 deg, a coral stop near 10 and violet-blue from 30 up, which a 2-stop power curve cannot draw.
 *  Day, dusk and night are sampled from their zenith/horizon pairs so those looks are unchanged. */
export const SKY_STOP_EL = [0, 4, 10, 20, 40, 90] as const;
/** golden stops decode with a softer curve: measured with the post chain OFF, S() stops landed ~20 L* darker and
 *  far more saturated than authored (the sky's mids are crushed on the way out), the same finding as the water's */
const SG = (hex: number) => { const c = new THREE.Color(hex); return c.setRGB(Math.pow(c.r, 1.45), Math.pow(c.g, 1.45), Math.pow(c.b, 1.45)); };
const GOLDEN_STOPS = [0xffd08a, 0xffad7e, 0xf3907f, 0xd27e9e, 0xa07cc6, 0x8c78c4].map(SG);
export const skyStops = (tod: number, look: Look): THREE.Color[] => {
  const two = (zen: THREE.Color, hor: THREE.Color) => SKY_STOP_EL.map((e) => hor.clone().lerp(zen, Math.pow(Math.sin((e * Math.PI) / 180), 0.36)));
  const day = two(S(0x7ab6ee), S(0xc2d6f3));
  const dusk = two(C(0.08, 0.1, 0.34), C(0.6, 0.38, 0.5));
  const night = two(C(0.03, 0.05, 0.15), C(0.12, 0.17, 0.36));
  return SKY_STOP_EL.map((_e, i) => tintHue(pal([day[i], GOLDEN_STOPS[i], dusk[i], night[i]], tod), look));
};

export const skyAt = (tod: number, look: Look) => ({
  // (the day zenith is authored a step lighter and more cyan than the measured #3e7fd2 top: the grade's blue tint and
  // the tone map land it on #5e93d9, the measured upper sky, at the top of an eye-level frame)
  // Authored values are calibrated by measurement, not equal to the targets: the v2 chain (neutral tone map, grade,
  // encode) takes a blue down about 20 L* and 15 deg toward violet, so the day stops are written lighter and more
  // cyan than the screen targets #5e93d9 (upper) / #9fb6e6 (horizon), and the sunset peach a step hotter.
  zenith: tintHue(pal([S(0x7ab6ee), S(0x9a8ada), C(0.08, 0.1, 0.34), C(0.03, 0.05, 0.15)], tod), look),
  horizon: tintHue(pal([S(0xc2d6f3), S(0xffb66a), C(0.6, 0.38, 0.5), C(0.12, 0.17, 0.36)], tod), look),
  ground: pal([C(0.6, 0.62, 0.62), C(0.56, 0.4, 0.36), C(0.18, 0.14, 0.26), C(0.04, 0.05, 0.1)], tod),
  cloud: tintHue(pal([S(0xfbf8f1), SG(0xffc9b0), C(0.56, 0.42, 0.56), C(0.14, 0.16, 0.28)], tod), look),
  /** the shaded underside of a cumulus: lavender by day, lilac-pink at sunset (the reference's #c18dde -> #feb0c6;
   *  a grey mauve read as a lavender mass over the top of every golden frame) */
  cloudShade: tintHue(pal([S(0xc3cbe9), SG(0xc9a0d6), C(0.26, 0.2, 0.36), C(0.06, 0.07, 0.16)], tod), look),
  cloudAmount: num([0.28, 0.3, 0.3, 0.16], tod),
  sun: pal([C(1, 0.9, 0.72), S(0xffd18a), C(0.5, 0.24, 0.24), C(0, 0, 0)], tod),
  /** the wide glow round the disc: a thin halo by day, the reference's ~280 px glow at sunset */
  sunGlow: num([0.5, 1.6, 0.8, 0], tod),
  sunElevation: num([0.32, 0.05, -0.08, -0.2], tod),
  stars: Math.min(1, Math.max(0, (tod - 0.7) / 0.3)),
});

const warm = (c: THREE.Color, w: number) => c.setRGB(c.r * (1 + 0.1 * w), c.g * (1 + 0.02 * w), c.b * (1 - 0.12 * w));

export const lightsAt = (tod: number, look: Look) => {
  const w = look.warmth ?? 0;
  return {
    // a warm sun by day, a low amber sunset, then cool moonlight
    keyColor: warm(pal([C(1.0, 0.93, 0.8), C(1.0, 0.7, 0.44), C(0.66, 0.62, 0.95), C(0.6, 0.7, 1.0)], tod), w),
    keyIntensity: num([3.9, 3.1, 1.5, 1.25], tod),
    keyDir: pal([C(-30, 19, 14), C(-30, 7, 16), C(-16, 9, 15), C(-12, 16, 12)], tod),
    // the fill is the sky: cool blue from above, a warm bounce from the ground
    hemiSky: warm(pal([C(0.5, 0.68, 1.0), C(0.62, 0.52, 0.8), C(0.34, 0.38, 0.78), C(0.26, 0.34, 0.72)], tod), w * 0.5),
    hemiGround: warm(pal([C(0.56, 0.44, 0.34), C(0.5, 0.34, 0.3), C(0.2, 0.15, 0.28), C(0.12, 0.1, 0.24)], tod), w * 0.5),
    hemiIntensity: num([0.78, 0.72, 0.62, 0.6], tod),
  };
};

export const gradeAt = (tod: number, look: Look): Grade => {
  const w = look.warmth ?? 0;
  const sat = look.saturation ?? 1.2;
  return {
    exposure: num([1.08, 1.1, 1.2, 1.3], tod),
    saturation: sat * num([1.0, 1.02, 1.0, 0.98], tod),
    contrast: look.contrast ?? 1.14,
    // near-black blacks: the old 0.06 floor was the grey haze over everything
    lift: pal([C(0.012, 0.01, 0.02), C(0.014, 0.01, 0.022), C(0.01, 0.012, 0.03), C(0.01, 0.012, 0.035)], tod),
    gain: warm(pal([C(1, 1, 1), C(1, 0.98, 0.95), C(0.98, 0.98, 1), C(0.96, 0.98, 1)], tod), w * 0.4),
    // shadows cool a touch, highlights warm a touch: enough to read, never a wash
    shadowTint: pal([C(0.94, 0.95, 1.06), C(0.92, 0.9, 1.08), C(0.84, 0.84, 1.16), C(0.82, 0.84, 1.18)], tod),
    hiTint: warm(pal([C(1.03, 1.0, 0.96), C(1.05, 0.99, 0.93), C(1.0, 0.99, 1.0), C(0.98, 1.0, 1.02)], tod), w * 0.4),
  };
};
