// Adapted from mromidev/claude-animated-shorts (templates/bridge/lights.ts), MIT License, Copyright (c) 2026 Mr omi.
// Verbatim day/golden presets; lamp (the crawlspace) and hall (the hotel dining room) are ours.
// Light presets per time of day. The sun is CAMERA-RELATIVE and frozen per shot (world.ts update()):
// az = degrees from the shot camera's forward axis (0 = sun straight ahead = backlight, +90 = screen right,
// 180 = behind camera), el = elevation. lit/shade/lift are LINEAR RGB multipliers for shade.ts (may exceed 1).
// Field names follow lighting.md 9.1 exactly (the CHAR and POST agents read them); values are tuned on renders.
type C3 = [number, number, number];
export type LightPreset = {
  az: number; el: number;
  lit: C3; shade: C3; lift: C3; lambert: number; sideK: number; term: number;      // world two-tone (shade.ts)
  charTint: C3; charShade: number; charGrad: number; bodyGrad: number; sideTint: C3; // character cards (cast.ts)
  blob: C3; actorShadow: boolean;                                                    // contact blobs / card shadows
  top: string; hor: string; skyCurve: C3; fog: string; fogNear: number; fogFar: number; sunDisc: string; // depth.md 6.5
  sunCol: string; sunI: number; sky: string; ground: string; hemiI: number;         // three lights (unpatched mats only)
  bias: number; normalBias: number;
};
export type LightName = "day" | "golden" | "lamp" | "hall";
export const LIGHTS: Record<LightName, LightPreset> = {
  day: {
    az: 75, el: 48,
    lit: [1.58, 1.5, 1.33], shade: [0.62, 0.55, 0.66], lift: [0.06, 0.06, 0.1], // shade ours: ~0.45x lit in the same hue (round-1 verifier; the bridge's 0.3 turned brick mauve)
    lambert: 0.35, sideK: 0.84, term: 0.2,
    charTint: [1.0, 0.94, 0.92], charShade: 0.86, charGrad: 0.07, bodyGrad: 0.2, sideTint: [0.92, 0.90, 0.96],
    blob: [0.62, 0.58, 0.58], actorShadow: false,
    top: "#3e7fd2", hor: "#b8d0ec", skyCurve: [0.0, 0.5, 0.6], fog: "#b8d0ec", fogNear: 40, fogFar: 360, sunDisc: "#000000",
    sunCol: "#fff3e0", sunI: 2.8, sky: "#dcecff", ground: "#b49a78", hemiI: 0.55,
    bias: -0.00025, normalBias: 0.015,
  },
  golden: {
    az: 6, el: 7,
    lit: [1.5, 0.68, 0.24], shade: [0.15, 0.15, 0.3], lift: [0.04, 0.06, 0.17], lambert: 0.35, sideK: 0.82, term: 0.07,
    charTint: [1.0, 0.78, 0.56], charShade: 0.88, charGrad: 0.1, bodyGrad: 0.25, sideTint: [0.85, 0.80, 0.95],
    blob: [0.75, 0.74, 0.9], actorShadow: true,
    top: "#6a4f8c", hor: "#ffd08a", skyCurve: [0.05, 0.6, 1.0], fog: "#efb489", fogNear: 50, fogFar: 380, sunDisc: "#ffcf9e",
    sunCol: "#ffab5e", sunI: 5.5, sky: "#d8b0b8", ground: "#8a6a60", hemiI: 0.5,
    bias: -0.0006, normalBias: 0.03,
  },
  // crawlspace under a building: a low warm key from the open side and the lanterns, deep violet-brown shade, no sky
  lamp: {
    az: 70, el: 22,
    lit: [2.0, 1.45, 0.95], shade: [0.62, 0.52, 0.64], lift: [0.24, 0.2, 0.26], lambert: 0.4, sideK: 0.85, term: 0.15,
    charTint: [1.0, 0.94, 0.86], charShade: 0.88, charGrad: 0.07, bodyGrad: 0.24, sideTint: [0.86, 0.82, 0.95],
    blob: [0.7, 0.66, 0.8], actorShadow: true,
    top: "#2a1f24", hor: "#3b2c2a", skyCurve: [0.0, 0.5, 0.6], fog: "#6e544c", fogNear: 12, fogFar: 50, sunDisc: "#000000",
    sunCol: "#ffc890", sunI: 3.0, sky: "#6a5040", ground: "#3a2a20", hemiI: 0.4,
    bias: -0.0004, normalBias: 0.02,
  },
  // hotel dining room: warm afternoon light through tall windows on the left, soft warm-violet shade
  hall: {
    az: -60, el: 30,
    lit: [1.5, 1.32, 1.06], shade: [0.34, 0.29, 0.36], lift: [0.06, 0.05, 0.09], lambert: 0.35, sideK: 0.86, term: 0.2,
    charTint: [1.0, 0.92, 0.85], charShade: 0.87, charGrad: 0.08, bodyGrad: 0.22, sideTint: [0.9, 0.87, 0.96],
    blob: [0.66, 0.6, 0.62], actorShadow: false,
    top: "#d9c3a0", hor: "#e8d6b6", skyCurve: [0.0, 0.5, 0.6], fog: "#cdb592", fogNear: 30, fogFar: 120, sunDisc: "#000000",
    sunCol: "#fff0d6", sunI: 2.8, sky: "#f0dcc0", ground: "#8a6a50", hemiI: 0.5,
    bias: -0.0003, normalBias: 0.015,
  },
};

/** world-only look per light (sky stops by elevation in degrees, river colours, cloud palette). All colours are
 *  ON-SCREEN targets under the current PBR-Neutral tone map; world.ts pre-inverts the tone map (shade.ts untone). */
export type WorldLook = {
  sky: { c: string[]; e: number[] };                         // 5 stops: c[i] at elevation e[i] (deg), smoothstep between
  water: { near: string; mid: string; far: string; crest: string; trough: string; glint: string; shade: C3 };
  bounce: C3;                                                 // shade.ts uBounce: albedo x bounce on shaded faces turned to the lens
  sat: number;                                                // shade.ts uSat: world albedo saturation (1 = as painted)
  cloud: { lit: string; mid: string; shade: string };
};
export const LOOK: Record<LightName, WorldLook> = {
  day: {
    // depth.md 2.2: horizon #9fb6e6 just above the skyline, upper sky #5e93d9 at ~20 deg (grade: frame top #5997e2)
    sky: { c: ["#a9c6ec", "#86b0e8", "#5c95df", "#4483d8", "#3373cc"], e: [0, 3, 8, 16, 40] }, // round 2: C* >= 45 by ~10 deg
    water: { near: "#22a7b6", mid: "#167fb2", far: "#1a5596", crest: "#7ddfe8", trough: "#0e4a80", glint: "#ffffff", shade: [0.5, 0.56, 0.72] },
    cloud: { lit: "#fbf8f1", mid: "#e1e5f3", shade: "#c3cbe9" },
    bounce: [0, 0, 0],
    sat: 1.08,
  },
  golden: {
    // sunset, not dusk: #ffd08a horizon, peach/orange through ~10 deg, warm rose at 20, muted warm mauve only near the top
    // (the golden grade adds ~+11/255 blue to shadows/mids, so these lean warm)
    sky: { c: ["#ffc66a", "#ff965e", "#ec6c8a", "#a866b6", "#7a62c8"], e: [0, 4, 12, 22, 32] }, // round 3: C* >= 40 on every stop after the golden grade
    water: { near: "#1e3a6e", mid: "#355f96", far: "#d4a48e", crest: "#d9a088", trough: "#16294f", glint: "#ffe2b0", shade: [0.42, 0.46, 0.72] },
    cloud: { lit: "#ffd2a8", mid: "#f2a08f", shade: "#a98fc4" },
    bounce: [0.04, 0.02, 0.0],
    sat: 1.1,
  },
  lamp: {
    sky: { c: ["#3b2c2a", "#35282a", "#2f2428", "#2a2026", "#241c24"], e: [0, 3, 8, 16, 40] },
    water: { near: "#3a3a30", mid: "#3a3a30", far: "#3a3a30", crest: "#7a6a50", trough: "#2a2420", glint: "#ffd8a0", shade: [0.5, 0.48, 0.6] },
    cloud: { lit: "#000000", mid: "#000000", shade: "#000000" },
    bounce: [0.05, 0.03, 0.0],
    sat: 1.05,
  },
  hall: {
    sky: { c: ["#e8d6b6", "#e2ceb0", "#dcc6a8", "#d6bea0", "#d0b698"], e: [0, 3, 8, 16, 40] },
    water: { near: "#22a7b6", mid: "#167fb2", far: "#1a5596", crest: "#7ddfe8", trough: "#0e4a80", glint: "#ffffff", shade: [0.5, 0.56, 0.72] },
    cloud: { lit: "#fbf8f1", mid: "#e1e5f3", shade: "#c3cbe9" },
    bounce: [0.03, 0.02, 0.0],
    sat: 1.05,
  },
};