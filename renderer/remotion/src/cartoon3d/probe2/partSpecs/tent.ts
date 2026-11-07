import type { PartSpec } from "../partGrammar";

export const tent: PartSpec = {
  name: "tent",
  blurb: "canvas A-frame tent, open flap faces +z, with guy ropes",
  prims: [
    { kind: "shape", points: [[-1, 0], [1, 0], [0, 1.6]], depth: 2.6, mat: "canvas" },
    // the dark doorway and the two flaps pinned back beside it
    { kind: "shape", points: [[-0.42, 0], [0.42, 0], [0, 1.25]], at: [0, 0, 1.305], mat: "dark", noInk: true },
    { kind: "rod", from: [-0.47, 0.06, 1.34], to: [-0.06, 1.3, 1.34], r: 0.05, rTop: 0.035, mat: "canvas" },
    { kind: "rod", from: [0.47, 0.06, 1.34], to: [0.06, 1.3, 1.34], r: 0.05, rTop: 0.035, mat: "canvas" },
    // poles front and back, a guy rope and peg off each
    { kind: "rod", from: [0, 0, 1.33], to: [0, 1.66, 1.33], r: 0.03, seg: 5, mat: "darkWood", repeat: { n: 2, step: [0, 0, -2.66] } },
    { kind: "rod", from: [0, 1.62, 1.33], to: [0, 0.02, 1.4], r: 0.008, seg: 3, mat: "rope", repeat: { n: 2, turn: [0, 180, 0] } },
    { kind: "cylinder", r: 0.01, rTop: 0.02, h: 0.12, seg: 4, at: [0, 0.03, 1.4], mat: "darkWood", repeat: { n: 2, turn: [0, 180, 0] } },
  ],
};
