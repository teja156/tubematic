// The "dig" example as a LowPolyDef: what the authoring agent's per-video module exports.
import type { LowPolyDef } from "../../def";
import { SHOTS, TOTAL, blurAt, camAt } from "./story";
import { Cutaway, Garden, Planet, Street } from "./sets";

export const DIG: LowPolyDef = {
  total: TOTAL,
  shots: SHOTS,
  camAt,
  sets: () => ({ garden: new Garden(), cutaway: new Cutaway(), crowd: new Street(), planet: new Planet() }),
  background: (set) => (set === "planet" ? "#0e0c1f" : set === "cutaway" ? "#2b1d12" : "#9fc3d9"),
  blurAt,
};
