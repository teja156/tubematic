// THE CAST GRAMMAR: a character the authoring agent describes as data (an outfit, a build, a skin, a hat), drawn
// every frame by the ported bean-head drawer (kit/toon.ts) on the same lit card as the hand-drawn newsboy and
// operator (kit/Cutout.ts). A world lists its people in `cast`; beats name them like the fixed two, with the same
// actions and a shared gesture list. Each figure passes the gate (gateCli: stills with a bystander and a crate,
// a fresh judge), exactly like a part.
import { Cutout } from "./Cutout";
import { bodyFront, INK, Pen, SKINS, type Build, type Expr, type Held, type Outfit } from "./toon";

/** what the agent writes in WorldSpec.cast[name] */
export interface FigureSpec {
  /** one line: who this is (for the judge and the catalog): "a riverboat captain in a navy coat and peaked cap" */
  blurb: string;
  /** hex colours; `hat` one of toon.ts's hats: cap, hair, bonnet, tophat, shako, shako_tall, or null */
  jacket: string;
  pants: string;
  boots: string;
  hat?: "cap" | "hair" | "bonnet" | "tophat" | "shako" | "shako_tall" | null;
  /** colours the hats and hair use */
  cap?: string;
  hair?: string;
  /** a dress instead of trousers (the jacket becomes the bodice) */
  dress?: string;
  belt?: string | null;
  buttons?: string;
  sash?: string;
  moustache?: string;
  /** skin: a hex, or one of the four kit skins by index 0-3 */
  skin?: string | number;
  build?: Build;
  /** ROLE PROP: what the right hand holds (paper, flag, lantern, cane) or what hangs on the body (satchel, bundle of
   *  papers under the arm). A role the costume cannot carry (newsboy, lamplighter) reads from this. */
  holds?: Held;
  /** the held thing's own colour (the flag's cloth, the bag's leather, the paper) */
  heldColor?: string;
  /** a frock coat's tails over the legs, or a long coat */
  coat?: "tails" | "long";
  /** height in metres (default by build: adult 1.75, stout 1.7, kid 1.3) */
  height?: number;
  seed?: number;
}

export const FIGURE_HATS = ["cap", "hair", "bonnet", "tophat", "shako", "shako_tall"] as const;
export const FIGURE_HOLDS: readonly Held[] = ["paper", "bundle", "satchel", "cane", "flag", "lantern"];
export const FIGURE_COATS = ["tails", "long"] as const;
export const BUILD_HEIGHT: Record<Build, number> = { adult: 1.75, stout: 1.7, kid: 1.3 };
export const figureHeight = (s: FigureSpec) => s.height ?? BUILD_HEIGHT[s.build ?? "adult"];

/** the gestures every grammar figure understands (a subset of the fixed cast's, mapped onto the drawer's poses) */
export type FigureGesture = "none" | "wave" | "cheer" | "shout" | "point" | "shrug" | "lookUp" | "think" | "talk" | "armsCrossed" | "handsOnHips" | "holdPaper";
export const FIGURE_GESTURES: readonly FigureGesture[] = ["none", "wave", "cheer", "shout", "point", "shrug", "lookUp", "think", "talk", "armsCrossed", "handsOnHips", "holdPaper"];
export const FIGURE_EXPRS: readonly Expr[] = ["neutral", "stern", "grin", "laugh", "whistle", "nervous", "shock", "relief", "relief_open", "dazed", "pained", "smile", "smile_closed", "lick"];

export interface FigurePose {
  /** walk cycle 0..1 and 0 standing .. 1 walking */
  phase: number;
  walk: number;
  expr?: Expr;
  /** eyelid 0 open .. 1 shut */
  lid: number;
  /** -1 look left .. 1 look right */
  look?: number;
  gesture?: FigureGesture;
  gestureFrom?: FigureGesture;
  gestureBlend?: number;
  /** seconds, for the gestures' own motion */
  beat?: number;
  talk?: number;
  headTilt?: number;
  /** canvas angle the key light comes from (radians); the painted crescent and the thick side of the ink follow it */
  light?: number;
}

/** no fill darker than the look's dark-material floor (navy #262c51, L* 16-22): a near-black coat or hat becomes a
 *  hole in the frame under the golden grade */
const FLOOR_L = 0.16;
const aboveFloor = (hex: string | undefined) => {
  if (!hex || !/^#[0-9a-fA-F]{6}$/.test(hex)) return hex;
  const n = parseInt(hex.slice(1), 16), r = (n >> 16) / 255, g = ((n >> 8) & 255) / 255, b = (n & 255) / 255;
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2;
  if (l >= FLOOR_L) return hex;
  const k = l > 0.001 ? (FLOOR_L / l) : 0;
  const lift = (c: number) => Math.round(Math.min(1, l > 0.001 ? c * k : FLOOR_L) * 255);
  return `#${[lift(r), lift(g), lift(b)].map((v) => v.toString(16).padStart(2, "0")).join("")}`;
};

const outfitOf = (s: FigureSpec): Outfit => ({
  jacket: aboveFloor(s.jacket)!, pants: aboveFloor(s.pants)!, boots: aboveFloor(s.boots)!, hat: s.hat === undefined ? "hair" : s.hat, cap: aboveFloor(s.cap), hair: aboveFloor(s.hair ?? "#4a3020"), dress: aboveFloor(s.dress),
  belt: s.belt, buttons: s.buttons, sash: s.sash, moustache: s.moustache, build: s.build ?? "adult",
  holds: s.holds, heldColor: aboveFloor(s.heldColor), coat: s.coat,
  skin: typeof s.skin === "number" ? SKINS[Math.max(0, Math.min(3, Math.floor(s.skin)))] : s.skin,
});

/** a gesture as the drawer's knobs: an arm wave amount, an expression override, a head tilt */
const GESTURE: Record<FigureGesture, { wave?: number; expr?: Expr; tilt?: number; look?: number; lift?: number }> = {
  none: {},
  wave: { wave: 1 },
  cheer: { wave: 1.6, expr: "laugh", tilt: -4 },
  shout: { wave: 0.8, expr: "laugh" },
  point: { wave: 1.3, expr: "neutral" },
  shrug: { wave: 0.3, expr: "nervous", tilt: 5 },
  lookUp: { tilt: -7, expr: "relief_open" },
  think: { wave: 0.4, expr: "stern", tilt: 4 },
  talk: { wave: 0.5 },
  armsCrossed: { expr: "stern" },
  handsOnHips: { expr: "smile_closed" },
  holdPaper: { wave: 0.6, expr: "grin" },
};

export const smoother = (x: number) => { const t = Math.max(0, Math.min(1, x)); return t * t * t * (t * (t * 6 - 15) + 10); };

export class Figure {
  readonly cut: Cutout;
  readonly height: number;
  private outfit: Outfit;
  private seed: number;
  constructor(readonly spec: FigureSpec) {
    this.height = figureHeight(spec);
    // the drawer's adult is 3.5 head-heights of ~222 units on a 1000-unit canvas (soles at 975): the card is sized so
    // that figure stands `height` metres tall; a kid's card is shorter in the same ratio
    const Bd = spec.build ?? "adult";
    const units = (Bd === "kid" ? 2.85 : Bd === "stout" ? 3.47 : 3.5) * 222;
    this.cut = new Cutout((this.height * 1000) / units, 1024);
    this.outfit = outfitOf(spec);
    this.seed = spec.seed ?? 1;
  }
  get mesh() { return this.cut.mesh; }

  redraw(q: FigurePose) {
    const from = GESTURE[q.gestureFrom ?? "none"], to = GESTURE[q.gesture ?? "none"];
    const k = smoother(q.gestureBlend ?? 1);
    const mixN = (a?: number, b?: number) => (a === undefined && b === undefined ? undefined : (a ?? 0) + ((b ?? 0) - (a ?? 0)) * k);
    const wave = mixN(from.wave, to.wave);
    const beat = q.beat ?? 0;
    const waveNow = wave === undefined ? undefined : wave * (0.85 + 0.15 * Math.sin(beat * 7));
    const tilt = (q.headTilt ?? 0) + (mixN(from.tilt, to.tilt) ?? 0);
    const expr = (k > 0.5 ? to.expr : from.expr) ?? q.expr ?? "neutral";
    const walk = Math.max(0, Math.min(1, q.walk));
    const o = this.outfit, seed = this.seed, light = q.light ?? (-120 * Math.PI) / 180;
    this.cut.redraw((ctx) => {
      // the card's design space is 512 x 1024; the drawer's is 600 x 1000
      ctx.scale(512 / 600, 1024 / 1000);
      const p = new Pen(ctx);
      bodyFront(p, o, {
        phase: q.phase, expr, mode: walk > 0.5 ? "stroll" : "stand", look: q.look ?? 0, blink: q.lid,
        wave: waveNow, headTilt: tilt, light, facing: 0, seed, lift: 60,
      });
      if (q.talk && q.talk > 0.2) {
        // a simple open mouth over the drawn one while speaking
        ctx.fillStyle = "#5a1e28";
        ctx.beginPath();
        ctx.ellipse(300, 975 - (o.build === "kid" ? 2.85 : 3.5) * 222 + 0.7 * 222, 12 + 10 * q.talk, 7 + 9 * q.talk, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.lineWidth = 4; ctx.strokeStyle = INK; ctx.stroke();
      }
    });
  }
}
