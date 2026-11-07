import type { PartSpec } from "../partGrammar";

export const bystander: PartSpec = {
  name: "bystander",
  blurb: "one flat cartoon background figure facing +z: hat, coat, skirt or trousers and height picked by seed",
  prims: [
    // 1.5-1.8 m by seed; the card is half as wide as it is tall, and stands for a 0.3 m deep body
    { kind: "card", draw: "figure", size: [0.75, 1.5], heights: [1.5, 1.55, 1.6, 1.65, 1.7, 1.75, 1.8], thick: 0.3 },
  ],
};
