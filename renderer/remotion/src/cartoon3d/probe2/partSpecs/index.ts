// Parts written in the part grammar (partGrammar.ts). makePart compiles these
// kinds from their spec; PART_DIMS and PART_INFO derive their facts from them.
import type { PartSpec } from "../partGrammar";
import type { PartKind } from "../partsSpec";
import { bystander } from "./bystander";
import { crate } from "./crate";
import { locomotive } from "./locomotive";
import { pineTree } from "./pineTree";
import { tent } from "./tent";
import { waterTower } from "./waterTower";

export const PART_SPECS = { crate, waterTower, tent, pineTree, locomotive, bystander } satisfies Partial<Record<PartKind, PartSpec>>;
export type SpecKind = keyof typeof PART_SPECS;
