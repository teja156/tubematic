// The registry of code parts (partSpecs/code/types.ts). The authoring agent adds one file per part beside this one
// and one line here; the gate (gate/gateCli.ts) hashes that file, renders it with a bystander and a crate, and a
// fresh judge decides. A world names a code part in `pieces` like any kit kind. Promoted names are in promoted.json:
// those need no new verdict.
import type { CodePart } from "./types";
import { TELEGRAPH_KEY } from "./telegraphKey";
import { LEE_BOAT } from "./leeBoat";
import { NATCHEZ_BOAT } from "./natchezBoat";
import { RIVER_SURFACE } from "./riverSurface";
import { FUEL_BARGE } from "./fuelBarge";
import { FOG_BANK } from "./fogBank";
import { MIST_BANK } from "./mistBank";
import { SPIN_CLOCK } from "./spinClock";
import { BET_BOARD } from "./betBoard";
import { RECORD_BOARD } from "./recordBoard";

export const CODE_PARTS: Record<string, CodePart> = {
  telegraphKey: TELEGRAPH_KEY,
  leeBoat: LEE_BOAT,
  natchezBoat: NATCHEZ_BOAT,
  riverSurface: RIVER_SURFACE,
  fuelBarge: FUEL_BARGE,
  fogBank: FOG_BANK,
  mistBank: MIST_BANK,
  spinClock: SPIN_CLOCK,
  betBoard: BET_BOARD,
  recordBoard: RECORD_BOARD,
};

/** the source file of a code part, relative to the Remotion project, for the gate's hash */
export const codePartFile = (name: string) => `src/cartoon3d/probe2/partSpecs/code/${name}.ts`;
