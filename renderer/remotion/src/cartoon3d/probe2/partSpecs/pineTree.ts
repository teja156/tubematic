import type { PartSpec, Prim } from "../partGrammar";

const R2D = 180 / Math.PI;
// stacked cones [radius, height, base y]; each tier spun by a seeded angle
const TIERS: [number, number, number][] = [[1.18, 1.9, 1.05], [0.98, 1.7, 2.0], [0.76, 1.5, 2.9], [0.52, 1.3, 3.75], [0.3, 1.0, 4.55]];

export const pineTree: PartSpec = {
  name: "pineTree",
  blurb: "conifer of stacked cones (5.6 m)",
  prims: [
    { kind: "cylinder", r: 0.2, rTop: 0.12, h: 1.4, seg: 8, at: [0, 0.7, 0], mat: "bark" },
    ...TIERS.map(([r, h, y], i): Prim => ({
      kind: "cylinder", r, rTop: 0, h, seg: 7, at: [0, y + h / 2 - 0.3, 0], rot: [0, (i * 0.7 + 0.5) * R2D, 0], mat: "leafDark",
      jitter: { at: [0.04, 0, 0.04], rot: [0, 0.5 * R2D, 0] },
    })),
  ],
};
