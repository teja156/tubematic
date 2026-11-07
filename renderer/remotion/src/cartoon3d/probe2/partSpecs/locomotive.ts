import type { KitMat, PartSpec, Prim, V3 } from "../partGrammar";

// railTrack facts every vehicle needs: the rail tops and where the rails run
const RAIL_TOP = 0.26;
const RAIL_Z = 1.435 / 2;
const R2D = 180 / Math.PI;
const K: KitMat = "engineBlack";
const R: KitMat = "engineRed";
const B: KitMat = "brass";
const rD = 0.78; // driving wheels
const rP = 0.4; // pilot and tender wheels
const yD = RAIL_TOP + rD;
const yP = RAIL_TOP + rP;
const CRANK = 0.35; // radians
const bx = 1.3; // boiler
const by = 1.98;
const rB = 0.72;
const sx = 2.55; // stack
const topB = by + rB;
const cx = -0.9; // cab
const cy0 = 1.23;
const tc = -3.15; // tender

/** a wheel in the xy plane: iron tread with an inside flange, red spoked
 *  centre, optional crank pin. `out` is the side it is on (+-1), so the flange
 *  goes inside and the pin outside. */
const wheel = (r: number, out: 1 | -1, spokes: number, crank?: number): Prim => ({
  kind: "group", at: [0, 0, out * RAIL_Z],
  items: [
    { kind: "cylinder", r, h: 0.12, seg: 24, open: true, rot: [90, 0, 0], mat: "iron" },
    { kind: "torus", r: r + 0.02, tube: 0.035, at: [0, 0, -out * 0.07], mat: "iron" },
    { kind: "torus", r: r - 0.08, tube: 0.05, mat: R },
    { kind: "cylinder", r: r * 0.22, h: 0.16, seg: 12, rot: [90, 0, 0], mat: R },
    { kind: "rod", from: [r * 0.18, 0, 0], to: [r - 0.1, 0, 0], r: Math.max(0.028, r * 0.05), seg: 5, mat: R, repeat: { n: spokes, turn: [0, 0, 360 / spokes] } },
    ...(crank === undefined ? [] : [{ kind: "cylinder", r: 0.06, h: 0.18, seg: 8, at: [Math.cos(crank) * r * 0.55, Math.sin(crank) * r * 0.55, out * 0.1], rot: [90, 0, 0], mat: "steel" } as Prim]),
  ],
});
/** both wheels of an axle and the axle, centred on the track */
const wheelset = (r: number, spokes: number, axle: number, crank?: number): Prim[] => [
  wheel(r, 1, spokes, crank),
  wheel(r, -1, spokes, crank),
  { kind: "rod", from: [0, 0, -RAIL_Z], to: [0, 0, RAIL_Z], r: axle, seg: 8, mat: "iron" },
];
const SMALL = wheelset(rP, 8, 0.05);

/** steam cylinder and the rods from it to the driving wheels' crank pins on side s */
const steam = (s: 1 | -1): Prim[] => {
  const z = s * 1.0;
  const zp = s * (RAIL_Z + 0.12);
  const pin = (x: number): V3 => [x + Math.cos(CRANK) * rD * 0.55, yD + Math.sin(CRANK) * rD * 0.55, zp];
  return [
    { kind: "cylinder", r: 0.22, h: 0.9, seg: 14, at: [2.3, 1.2, z], rot: [0, 0, 90], mat: K },
    { kind: "cylinder", r: 0.25, h: 0.08, seg: 14, at: [1.9, 1.2, z], rot: [0, 0, 90], mat: B },
    { kind: "rod", from: pin(0.9), to: pin(-0.6), r: 0.045, mat: "steel" },
    { kind: "rod", from: pin(0.9), to: [1.85, 1.2, zp], r: 0.04, mat: "steel" },
    { kind: "rod", from: [1.85, 1.2, zp], to: [1.85, 1.2, z], r: 0.04, mat: "steel" },
  ];
};
/** one side of the cab: window frame, dark pane, brass band, number plate.
 *  Pane and plate face out of their side (the hand-built cab turned them
 *  edge-on, toward +-x, so the window read as a slit and the plate vanished). */
const cabSide = (s: 1 | -1): Prim[] => [
  { kind: "box", size: [0.6, 0.66, 0.03], at: [cx + 0.15, 2.35, s * 0.855], mat: "creamPaint" },
  { kind: "plane", size: [0.46, 0.52], at: [cx + 0.15, 2.35, s * 0.88], rot: [0, s === 1 ? 0 : 180, 0], mat: "dark", noInk: true },
  { kind: "box", size: [1.52, 0.06, 0.03], at: [cx, 1.6, s * 0.855], mat: B },
  { kind: "card", draw: "plate", text: ["60", "119"], size: [0.5, 0.25], at: [cx - 0.3, 1.95 - 0.125, s * 0.86], rot: [0, s === 1 ? 0 : 180, 0], noInk: true },
];
/** cordwood on the tender: a spinning log, seeded per log */
const log = (at: V3): Prim => ({
  kind: "cylinder", r: 0.1, h: 1.4, seg: 7, at, rot: [90, 3 * R2D, 0], mat: ["bark", "rings", "rings"],
  jitter: { rot: [0, 3 * R2D, 0] }, repeat: { n: 2, step: [0, 0.19, 0] },
});

export const locomotive: PartSpec = {
  name: "locomotive",
  blurb: "1860s 4-4-0 steam locomotive and its wood tender, 9 m along x with the cowcatcher toward +x; place it on railTrack (its wheels sit on the rail tops); headlamp lit at night, stack smokes",
  lightAtNight: true,
  smoke: [{ at: [sx, topB + 1.45, 0], kind: "stack" }],
  lamp: [{ at: [3.65, topB + 0.28, 0], colour: [34.595, 1.0, 0.7824] }],
  prims: [
    // frame, wheels, axles (front is +x)
    { kind: "box", size: [4.7, 0.18, 1.2], at: [0.7, 1.14, 0], mat: K },
    { kind: "group", at: [0.9, yD, 0], repeat: { n: 2, step: [-1.5, 0, 0] }, items: wheelset(rD, 12, 0.06, CRANK) },
    { kind: "group", at: [2.15, yP, 0], repeat: { n: 2, step: [0.8, 0, 0] }, items: SMALL },
    { kind: "box", size: [1.3, 0.14, 1.2], at: [2.55, yP + 0.14, 0], mat: K },
    // steam cylinders and rods
    ...steam(-1),
    ...steam(1),
    // boiler, smokebox, bands, running boards
    { kind: "cylinder", r: rB, h: 3.3, seg: 22, at: [bx, by, 0], rot: [0, 0, 90], mat: K },
    { kind: "cylinder", r: rB + 0.04, h: 0.5, seg: 22, at: [2.75, by, 0], rot: [0, 0, 90], mat: K },
    { kind: "cylinder", r: 0.3, h: 0.06, seg: 16, at: [3.02, by, 0], rot: [0, 0, 90], mat: "iron" },
    { kind: "cylinder", r: rB + 0.03, h: 0.1, seg: 22, at: [0.7, by, 0], rot: [0, 0, 90], mat: B, repeat: { n: 2, step: [1.5, 0, 0] } },
    { kind: "box", size: [3.4, 0.07, 0.36], at: [1.15, 1.86, 0.95], mat: K, repeat: { n: 2, step: [0, 0, -1.9] } },
    { kind: "rod", from: [-0.15, 2.7, 0.8], to: [2.9, 2.7, 0.8], r: 0.025, mat: B, repeat: { n: 2, step: [0, 0, -1.6] } },
    // balloon stack
    { kind: "lathe", points: [[0.2, 0], [0.2, 0.55], [0.5, 1.1], [0.46, 1.38], [0.36, 1.42], [0.0, 1.42]], seg: 18, at: [sx, topB - 0.05, 0], mat: K },
    { kind: "cylinder", r: 0.52, h: 0.06, seg: 18, at: [sx, topB + 1.31, 0], mat: B },
    // domes, bell and whistle
    { kind: "lathe", points: [[0.36, 0], [0.36, 0.26], [0.3, 0.4], [0.0, 0.46]], at: [0.2, topB - 0.08, 0], mat: B },
    { kind: "rod", from: [0.2, topB + 0.36, 0], to: [0.2, topB + 0.72, 0], r: 0.045, seg: 8, mat: B },
    { kind: "lathe", points: [[0.32, 0], [0.32, 0.3], [0.26, 0.42], [0.0, 0.5]], at: [1.65, topB - 0.08, 0], mat: B },
    { kind: "rod", from: [1.0 - 0.18, topB - 0.04, 0], to: [1.0, topB + 0.42, 0], r: 0.025, seg: 5, mat: B },
    { kind: "rod", from: [1.0 + 0.18, topB - 0.04, 0], to: [1.0, topB + 0.42, 0], r: 0.025, seg: 5, mat: B },
    { kind: "cylinder", r: 0.16, rTop: 0, h: 0.26, seg: 12, at: [1.0, topB + 0.2, 0], mat: B },
    // headlamp on its platform in front of the stack
    { kind: "box", size: [0.6, 0.06, 0.6], at: [3.05, topB + 0.02, 0], mat: K },
    { kind: "rod", from: [3.0, by + 0.5, 0.25], to: [3.3, topB, 0.25], r: 0.025, seg: 5, mat: K, repeat: { n: 2, step: [0, 0, -0.5] } },
    { kind: "box", size: [0.46, 0.46, 0.46], at: [3.1, topB + 0.28, 0], mat: K },
    { kind: "box", size: [0.52, 0.06, 0.52], at: [3.1, topB + 0.53, 0], mat: K },
    { kind: "cylinder", r: 0.17, h: 0.04, seg: 16, at: [3.34, topB + 0.28, 0], rot: [0, 0, 90], mat: { hsl: [42.353, 0.7556, 0.8235], glow: { rgb: [1.0, 0.78, 0.4], peak: 1.6 } } },
    // cab
    { kind: "box", size: [1.5, 1.55, 1.7], at: [cx, cy0 + 0.775, 0], mat: R },
    { kind: "box", size: [1.75, 0.1, 2.05], at: [cx, 2.86, 0], mat: K },
    ...cabSide(-1),
    ...cabSide(1),
    { kind: "card", draw: "plate", text: ["60", "119"], size: [0.3, 0.15], at: [3.1, topB + 0.28 - 0.075, 0.24], noInk: true },
    { kind: "box", size: [0.4, 0.05, 0.3], at: [cx - 0.55, 0.45, 0.95], mat: K, repeat: { n: 2, step: [0, 0.4, 0] } },
    { kind: "box", size: [0.4, 0.05, 0.3], at: [cx - 0.55, 0.45, -0.95], mat: K, repeat: { n: 2, step: [0, 0.4, 0] } },
    // cowcatcher
    { kind: "box", size: [0.2, 0.3, 2.0], at: [3.15, 1.05, 0], mat: R },
    ...Array.from({ length: 9 }, (_, i): Prim => {
      const z = -0.8 + i * 0.2;
      return { kind: "rod", from: [3.25, 1.15, z], to: [4.4 - (Math.abs(z) / 0.95) * 1.05, 0.32, z], r: 0.035, seg: 5, mat: R };
    }),
    { kind: "rod", from: [4.4, 0.32, 0], to: [3.3, 0.32, -0.9], r: 0.04, seg: 5, mat: R },
    { kind: "rod", from: [4.4, 0.32, 0], to: [3.3, 0.32, 0.9], r: 0.04, seg: 5, mat: R },
    // tender: wood-sided box on two trucks, cordwood and coal heaped on top
    { kind: "box", size: [2.6, 0.16, 1.2], at: [tc, 1.14, 0], mat: K },
    {
      kind: "group", at: [-2.45, yP, 0], repeat: { n: 2, step: [-1.4, 0, 0] },
      items: [
        { kind: "group", at: [-0.375, 0, 0], repeat: { n: 2, step: [0.75, 0, 0] }, items: SMALL },
        { kind: "box", size: [1.35, 0.16, 1.2], at: [0, 0.2, 0], mat: K },
        { kind: "box", size: [1.45, 0.16, 0.08], at: [0, 0, 0.87], mat: "darkWood", repeat: { n: 2, step: [0, 0, -1.74] } },
      ],
    },
    { kind: "box", size: [2.5, 1.0, 1.6], at: [tc, 1.72, 0], mat: "redPaintV" },
    { kind: "box", size: [2.56, 0.08, 1.66], at: [tc, 2.25, 0], mat: K },
    // logs in the hand-built order (column by column, bottom then top)
    { kind: "group", repeat: { n: 2, step: [-0.44, 0, 0] }, items: [log([-2.25, 2.3, 0]), log([-2.47, 2.33, 0])] },
    { kind: "sphere", r: [0.55, 0.35, 0.7], at: [-3.75, 2.2, 0], mat: "coal" },
    { kind: "box", size: [0.4, 0.3, 1.2], at: [-4.25, 2.44, 0], mat: "darkWood" },
    { kind: "box", size: [0.6, 0.1, 0.16], at: [-1.75, 1.1, 0], mat: K },
  ],
};
