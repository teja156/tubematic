import type { PartSpec } from "../partGrammar";

// Four splayed legs from (+-1.3, 0, +-1.3) to 0.8 of that at y = 4. Each leg,
// and each face's X brace and girt, is drawn once for the +z face and turned
// round the other three. Brace ends are points t of the way up a leg.
const TURN4 = { n: 4, turn: [0, -90, 0] as [number, number, number] };
const up = (t: number, side: 1 | -1): [number, number, number] => [side * (1.3 - 0.26 * t), 4 * t, 1.3 - 0.26 * t];

export const waterTower: PartSpec = {
  name: "waterTower",
  blurb: "railway water tank on four splayed legs with a swing spout (7.4 m tall)",
  prims: [
    { kind: "rod", from: [1.3, 0, 1.3], to: [1.04, 4.0, 1.04], r: 0.1, mat: "darkWood", repeat: TURN4 },
    { kind: "rod", from: up(0.15, 1), to: up(0.55, -1), r: 0.045, seg: 5, mat: "darkWood", repeat: TURN4 },
    { kind: "rod", from: up(0.15, -1), to: up(0.55, 1), r: 0.045, seg: 5, mat: "darkWood", repeat: TURN4 },
    { kind: "rod", from: up(0.6, 1), to: up(0.6, -1), r: 0.05, seg: 5, mat: "darkWood", repeat: TURN4 },
    // deck, staved tank with three hoops, conical roof and finial
    { kind: "cylinder", r: 1.7, h: 0.14, seg: 16, at: [0, 4.07, 0], mat: "darkWood" },
    { kind: "cylinder", r: 1.5, h: 2.2, seg: 18, open: true, uv: [3, 1.1], at: [0, 5.24, 0], mat: "barrel" },
    { kind: "cylinder", r: 1.52, h: 0.06, seg: 18, at: [0, 4.45, 0], mat: "iron" },
    { kind: "cylinder", r: 1.52, h: 0.06, seg: 18, at: [0, 5.24, 0], mat: "iron" },
    { kind: "cylinder", r: 1.52, h: 0.06, seg: 18, at: [0, 6.05, 0], mat: "iron" },
    { kind: "cylinder", r: 1.72, rTop: 0, h: 0.95, seg: 18, at: [0, 6.8, 0], mat: "greyWood" },
    { kind: "sphere", r: 0.09, seg: [6, 4], at: [0, 7.3, 0], mat: "iron" },
    // swing spout toward +z with its pull rope
    { kind: "rod", from: [0, 4.7, 1.5], to: [0, 5.9, 2.05], r: 0.11, seg: 8, mat: "iron" },
    { kind: "cylinder", r: 0.15, h: 0.12, seg: 8, at: [0, 4.7, 1.45], rot: [90, 0, 0], mat: "iron" },
    { kind: "rod", from: [0, 5.9, 2.05], to: [0, 3.6, 2.05], r: 0.01, seg: 4, mat: "rope" },
    // ladder up the +z face
    { kind: "rod", from: [-0.22, 0, 1.35], to: [-0.22, 4.05, 1.12], r: 0.025, seg: 4, mat: "lightWood", repeat: { n: 2, step: [0.44, 0, 0] } },
    { kind: "rod", from: [-0.22, 0.35, 1.35 - 0.35 * 0.057], to: [0.22, 0.35, 1.35 - 0.35 * 0.057], r: 0.015, seg: 4, mat: "lightWood", repeat: { n: 10, step: [0, 0.38, -0.38 * 0.057] } },
  ],
};
