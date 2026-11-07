import type { PartSpec } from "../partGrammar";

// 0.8 m crate: body, corner posts, edge battens top and bottom, two cross braces
const S = 0.8;
const T = 0.07;
const E = (S - T) / 2; // batten / post centre line
const BRACE = (S - 2 * T) * 1.38;

export const crate: PartSpec = {
  name: "crate",
  blurb: "wooden shipping crate with corner battens and a cross brace",
  prims: [
    { kind: "box", size: [S - 0.02, S - 0.02, S - 0.02], at: [0, S / 2, 0], mat: "crate" },
    {
      kind: "group", at: [E, S / 2, E], repeat: { n: 2, step: [-2 * E, 0, 0] },
      items: [{ kind: "box", size: [T, S, T], mat: "midWood", repeat: { n: 2, step: [0, 0, -2 * E] } }],
    },
    {
      kind: "group", at: [0, T / 2, 0], repeat: { n: 2, step: [0, S - T, 0] },
      items: [
        { kind: "box", size: [S, T, T], at: [0, 0, E], mat: "midWood", repeat: { n: 2, step: [0, 0, -2 * E] } },
        { kind: "box", size: [T, T, S], at: [E, 0, 0], mat: "midWood", repeat: { n: 2, step: [-2 * E, 0, 0] } },
      ],
    },
    { kind: "box", size: [T * 0.9, BRACE, 0.025], at: [0, S / 2, S / 2 - 0.005], rot: [0, 0, 45], mat: "midWood" },
    { kind: "box", size: [0.025, BRACE, T * 0.9], at: [S / 2 - 0.005, S / 2, 0], rot: [-45, 0, 0], mat: "midWood" },
  ],
};
