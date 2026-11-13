/*
 * What is on screen at a frame: a pure function of the data, so the scene, the
 * sheets and the tests read the same answer.
 *
 * A beat shows from its start until the next beat's, and beats change on a hard
 * cut: nobody carries over from one beat to the next, so each beat's puppets
 * enter in it (an entrance `from: "cut"` puts a puppet there already at the
 * cut). A costume swap lasts: a puppet keeps its new costume in later beats
 * too. The camera never moves; the cut is the style's edit.
 */
import { clamp01, ease, hashSeed } from "../characterKit/geometry";
import { GEOMETRY, TIMING, W, type Costume, type Face, type PHBeat, type PHEvent, type Pose, type PuppetHistoryData } from "./contract";

export function beatAt(data: PuppetHistoryData, frame: number): number {
  let i = -1;
  data.beats.forEach((b, k) => { if (b.start <= frame) i = k; });
  return i;
}

export const beatEnd = (data: PuppetHistoryData, i: number, total: number) => (i + 1 < data.beats.length ? data.beats[i + 1].start : total);

/** Every costume swap in the video, so a swap lasts into later beats. */
export function costumeAt(data: PuppetHistoryData, who: string, frame: number): Costume {
  let c = data.cast.find((a) => a.id === who)?.costume ?? "plain";
  for (const b of data.beats) for (const e of b.events) if (e.type === "swap" && e.who === who && e.frame <= frame) c = e.costume;
  return c;
}

/** A puppet faces the middle of the frame: right from the left and middle slots, left from the right one. */
export const facesLeft = (slot: number) => slot === 2;

const edgeX = (slot: number) => (slot === 2 ? W + 260 : -260);

export type PuppetState = {
  id: string;
  costume: Costume;
  pose: Pose;
  face: Face;
  slot: number;
  /** Where its waist is on screen, its scale for a pop, and whether it is mirrored to face left. */
  x: number;
  pop: number;
  flip: boolean;
  sign: string;
  prop: string;
  propText: string;
  blink: boolean;
  /** The frame it last changed, for a short squash on a change of pose. */
  since: number;
};

export function blinkAt(frame: number, seed: number): boolean {
  const period = 96 + (seed % 31);
  return (frame + (seed % period)) % period < 4;
}

/** The puppets of a set or map beat at a frame. */
export function puppetsAt(data: PuppetHistoryData, beat: PHBeat, frame: number): PuppetState[] {
  const on = new Map<string, PuppetState & { from: number; to: number; moveAt: number; enterAt: number; how: string; exitAt: number }>();
  for (const e of beat.events) {
    if (e.frame > frame) break;
    const p = "who" in e ? on.get(e.who) : undefined;
    switch (e.type) {
      case "enter": {
        const x = GEOMETRY.slots[e.slot];
        // what the video opens on is already there at frame 0
        const how = e.frame <= 0 ? "cut" : e.from ?? "slide";
        on.set(e.who, {
          id: e.who, costume: "plain", pose: e.pose ?? "stand", face: e.face ?? "stern", slot: e.slot, x, pop: 1,
          flip: facesLeft(e.slot), sign: "", prop: "", propText: "", blink: false, since: e.frame,
          from: how === "slide" ? edgeX(e.slot) : x, to: x, moveAt: e.frame, enterAt: e.frame, how, exitAt: -1,
        });
        break;
      }
      case "move":
        if (p) Object.assign(p, { from: GEOMETRY.slots[p.slot], to: GEOMETRY.slots[e.slot], moveAt: e.frame, how: "move", slot: e.slot, flip: facesLeft(e.slot) });
        break;
      case "exit":
        if (p) Object.assign(p, { exitAt: e.frame, from: GEOMETRY.slots[p.slot], to: edgeX(p.slot), moveAt: e.frame, how: "exit" });
        break;
      case "act":
        if (p) Object.assign(p, { pose: e.pose ?? p.pose, face: e.face ?? p.face, since: e.frame });
        break;
      case "sign":
        if (p) Object.assign(p, { sign: e.text, since: e.frame });
        break;
      case "hold":
        if (p) Object.assign(p, { prop: e.prop, propText: e.text ?? "", since: e.frame });
        break;
      default:
        break;
    }
  }
  const out: PuppetState[] = [];
  for (const p of on.values()) {
    const d = frame - p.moveAt;
    if (p.how === "exit" && d >= TIMING.slide) continue;
    let x = p.to, pop = 1;
    if (p.how === "slide" || p.how === "move") {
      const t = clamp01(d / (p.how === "slide" ? TIMING.slide : TIMING.move));
      x = p.from + (p.to - p.from) * (p.how === "slide" ? ease.out(t) : ease.inOut(t));
    } else if (p.how === "exit") {
      x = p.from + (p.to - p.from) * ease.in(clamp01(d / TIMING.slide));
    } else if (p.how === "pop") {
      const t = (frame - p.enterAt) / TIMING.pop;
      pop = t >= 1 ? 1 : t <= 0 ? 0.01 : Math.max(0.01, ease.outBack(t));
    }
    const seed = hashSeed(p.id);
    out.push({
      id: p.id, costume: costumeAt(data, p.id, frame), pose: p.sign ? "sign" : p.pose, face: p.face, slot: p.slot, x, pop,
      flip: p.flip, sign: p.sign, prop: p.sign ? "" : p.prop, propText: p.propText, blink: blinkAt(frame, seed), since: p.since,
    });
  }
  return out;
}

/** The stamps of a beat that have landed by a frame, with their kick. */
export function stampsAt(beat: PHBeat, frame: number): { text: string; color: string; kick: number; seed: number }[] {
  return beat.events
    .filter((e): e is Extract<PHEvent, { type: "stamp" }> => e.type === "stamp" && e.frame <= frame)
    .map((e) => {
      const d = frame - e.frame;
      return { text: e.text, color: e.color ?? "red", kick: d < TIMING.stamp ? Math.exp(-d / 2.2) * Math.cos(d * 2.4) : 0, seed: e.frame };
    });
}

/** The beat's date tag at a frame, or "". */
export function dateAt(beat: PHBeat, frame: number): string {
  let t = "";
  for (const e of beat.events) if (e.type === "date" && e.frame <= frame) t = e.text;
  return t;
}

/** A card line's strike-out at a frame: how far the line is struck (0-1) and the new value scrawled (0-1). */
export function strikesAt(beat: PHBeat, frame: number): Map<number, { text: string; strike: number; scrawl: number }> {
  const out = new Map<number, { text: string; strike: number; scrawl: number }>();
  for (const e of beat.events) {
    if (e.type !== "strike" || e.frame > frame) continue;
    const d = frame - e.frame;
    out.set(e.line, { text: e.text, strike: ease.out(clamp01(d / TIMING.strike)), scrawl: ease.out(clamp01((d - TIMING.strike / 2) / TIMING.strike)) });
  }
  return out;
}

/** A map beat's fills, arrows and labels at a frame, each with its progress (0-1). */
export function mapAt(beat: PHBeat, frame: number) {
  const fills: { region: string; color: string; t: number }[] = [];
  const arrows: { from: string; to: string; t: number }[] = [];
  const labels: { region: string; text: string; t: number }[] = [];
  for (const e of beat.events) {
    if (e.frame > frame) continue;
    const d = frame - e.frame;
    if (e.type === "fill") fills.push({ region: e.region, color: e.color, t: clamp01(d / TIMING.fill) });
    if (e.type === "arrow") arrows.push({ from: e.from, to: e.to, t: ease.out(clamp01(d / TIMING.arrow)) });
    if (e.type === "label") labels.push({ region: e.region, text: e.text, t: clamp01(d / TIMING.fill) });
  }
  return { fills, arrows, labels };
}
