// The Chicago short as a VideoDef: what the authoring agent's per-video module exports. The sets are built once per
// World; staging (scenes.ts) and the camera (story.ts) are pure functions of the frame.
import type { VideoDef } from "../../video";
import { SHOTS, TOTAL, XFADE, FLASH_AT, camAt, clipAt, dofAt, type Place } from "./story";
import { stage } from "./scenes";
import { Street } from "./sets/street";
import { Crawl } from "./sets/crawl";
import { Dining } from "./sets/dining";
import { Section } from "./sets/section";
import { River } from "./sets/river";

const OUTDOOR: Record<Place, boolean> = { street: true, section: true, river: true, crawl: false, dining: false };

export const CHICAGO: VideoDef = {
  total: TOTAL,
  shots: SHOTS,
  xfade: XFADE,
  flashAt: FLASH_AT,
  camAt,
  clipAt,
  dofAt,
  stage,
  sets: () => ({ street: new Street(), crawl: new Crawl(), dining: new Dining(), section: new Section(), river: new River() }),
  outdoor: (set) => OUTDOOR[set as Place] ?? false,
  skyVisible: (set) => set === "dining",
  // round 4: the crawlspace's forest of screws and timbers gets thinner lines that fade out down the rows (it
  // measured 9-10 % ink against the 2.5 % interior target)
  inkFor: (sh) => (sh.set === "crawl" ? { widthNear: 3.8, widthFar: 2.4, fadeNear: 9, fadeFar: 26, concaveGain: 0.0, creaseScale: 0.35, depthLo: 0.02, depthHi: 0.05 } : undefined),
};
