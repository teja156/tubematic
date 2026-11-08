# The Cartoon 3D kit: what a video is written against

The kit lives in the renderer at `renderer/remotion/src/cartoon3d/` and is frozen: `cartoon_kit_list()` names
every file, `cartoon_kit_read(path)` shows one. Your files sit under `src/scenes/generated/<video_id>/`, so
the kit is imported as `../../../cartoon3d/<path>` from a file at the top of that directory (`"../../../cartoon3d/kit/cast"`,
`"../../../cartoon3d/camera"`, `"../../../cartoon3d/video"`) and as `../../../../cartoon3d/<path>` from a module one
directory deeper (`sets/*.ts`, `stage/*.ts`); `three` is `import * as THREE from "three"`. The worked example
is `examples/chicago/` (41 shots, five sets, 120 s): read it as the spelling of everything below. Units are
metres; `y` is up; a character is 2.16 m tall at scale 1; 30 frames per second.

## 1. The contract: `video.ts`

```ts
export const FPS = 30;
export type V3 = [number, number, number];
export type Light = "day" | "golden" | "lamp" | "hall";

export type ShotDef = {
  id: number;             // 1-based, in order; shot n ends where shot n+1 starts
  a: number; b: number;   // frames, b exclusive; the last shot's b is the video's total
  light: Light;
  set: string;            // a key of sets()
  note: string;           // what the frame shows (for you; the judges read the SENTENCE)
  aerial?: boolean;       // a view from far above: shadow map, fog and clip planes cover the whole set
  sunAz?: number; sunEl?: number;   // camera-relative sun in degrees (default: outdoor day az 128 / el 56, else the light preset)
};

export interface VideoDef {
  total: number;                            // = timeline.totalFrames
  shots: ShotDef[];
  xfade: Record<number, number>;            // crossfade frames keyed by the id of the shot being faded IN; a cut otherwise
  flashAt?: number;                         // a 4-frame white flash starting here (the hook's end), if any
  camAt(id: number, f: number): Cam;        // the camera, every frame: build it with camera.ts (below)
  clipAt(id: number): { near: number; far: number };   // {near: 0.2, far: 1200} for everything but an aerial ({5, 2600})
  dofAt(f: number): { cInf: number; focus?: (f: number) => V3 };   // the lens, from a Dof table
  sets(): Record<string, SetPiece>;         // built once; place every set far from the others (1000 m apart)
  outdoor(set: string): boolean;            // under the sky: clouds, sky dome, sun disc
  skyVisible?(set: string): boolean;        // an interior whose windows show the sky
  stage(id: number, f: number, cam: CamInfo): Stage;   // who stands where, doing what
  inkFor?(shot: ShotDef): Partial<InkOptions> | undefined;   // per-shot ink overrides (rarely needed)
}
```

Everything is a pure function of the frame: a still, the beat gate and the render must agree. Keep every
`Math.random` out; use `hh(i, salt)` (a hash in [0, 1)) for variety.

The scene file is always:

```tsx
import { useCurrentFrame } from "remotion";
import { CartoonShort } from "../../../cartoon3d/CartoonShort";
import { VIDEO } from "./index";
export default function Scene() { return <CartoonShort video={VIDEO} frame={useCurrentFrame()} />; }
```

## 2. The camera grammar: `camera.ts`

Every move is a symmetric smootherstep glide of 18–40 frames; a reframe bigger than about half a frame width
is a cut on its key frame; every hold pushes in; impacts kick. The exports:

| export | meaning |
|---|---|
| `type Cam = { pos: V3; look: V3; fov: number; roll: number }` | the camera at a frame |
| `type Shot = Partial<Cam> & { pos; look }` | what a key produces (fov defaults 40, roll 0) |
| `type Key = { f: number; dur?: number; cut?: boolean; s: (f: number) => Shot }` | from frame `f`, glide over `dur` (default 24) into `s(f)`, or cut |
| `runKeys(keys, f)` | the camera from a shot's keys: the first holds, each later one glides (or cuts) in from its frame |
| `makeCamAt(cams: Record<number, Key[]>, kicks)` | the usual `camAt`: keys per shot id, plus the kicks |
| `dolly(pos, look, k, rest?)` | a push toward the look point by factor k (`k < 1` closer) |
| `zoom(pos, look, fov, k, rest?)` | a push by lens (next to walls): tan(fov/2) shrinks by k |
| `pushK(f, f0, rate, punch?, n?)` | the push factor since frame f0: `exp(-rate·x)`; `punch` raises the rate for the first `n` frames (a word) |
| `rolled(s, roll)` | a roll (radians) on top of a framing |
| `kicksAt(kicks: [seconds, gain][], t)` / `kicked(cam, a)` | 7-frame impact kicks that flip sign every frame |
| `glide(u)`, `smooth(u)`, `easeOut(u)`, `clamp01`, `lin(table, x)`, `add(a, b)` | the easings and a piecewise-linear table lookup |
| `shotAt(shots, f)`, `layersAt(shots, xfade, f)` | the shot of a frame; the layers a crossfade draws |
| `type Dof = { f; dur?; cInf; focus? }`, `dofAtOf(table, f)` | the lens table: from frame `f`, `cInf` (blur-disc radius at infinity, px at 1080x1920; 0 = sharp), eased over `dur` |

A shot's framings are small functions of the frame that push in from the frame their key starts, as in the
example's `story.ts`:

```ts
const S1a = (f: number) => dolly([1.4, 1.35, 1.6], [-1.6, 0.95, -5.6], pushK(f, 0, 0.0025), { fov: 42 });
const S1b = (f: number) => dolly([0.4, 0.75, 0.6], [-1.6, 0.55, -3.0], pushK(f, 84, 0.003, 0.006, 30), { fov: 40, roll: 0.03 });
export const CAMS: Record<number, Key[]> = {
  1: [{ f: 0, s: S1a }, { f: 84, dur: 28, s: S1b }],        // a glide into the close-up on the word at frame 98 (centred: starts dur/2 early)
  2: [{ f: 127, s: S2a }],
};
const KICKS: [number, number][] = [[100 / FPS, 0.7]];      // the boot in the mud
export const DOF: Dof[] = [{ f: 0, cInf: 12 }, { f: 127, cInf: 0 }, ...];
export const camAt = makeCamAt(CAMS, KICKS);
export const dofAt = (f: number) => dofAtOf(DOF, f);
export const clipAt = (id: number) => (SHOTS[id - 1].aerial ? { near: 5, far: 2600 } : { near: 0.2, far: 1200 });
```

Numbers that hold: push rates 0.0015–0.0035 per frame (0.15–0.35 %), punch 0.005–0.006 for 25–35 frames on the
word; glide `dur` 18–40; roll 0.03–0.05 rad on one or two shots; kicks 0.4–0.7 on impacts; fov 38–48 (30 for an
insert). The lens height is 0.67–1.0 of a character (1.4–2.0 m) in most shots; the look point is the subject's
chest or the thing named. For an aerial: `aerial: true` on the shot, the camera 60–150 m up and away, `sunAz`
~140 and `sunEl` ~40.

## 3. Light: `kit/lights.ts`

Four presets, chosen per shot: `day` (sun from the lens's right shoulder, blue sky, clouds), `golden` (sunset:
backlight, the sun disc low and right of the axis, violet shade, long real card shadows), `lamp` (a dark
interior lit by a low warm key: a crawlspace, a cellar, a night room), `hall` (a bright interior: warm light
through windows on the left). The sun is camera-relative and frozen per shot, so the lit side is the side
the shot looks at. Fog is the horizon colour (day 40→360 m, golden 50→380 m, lamp 12→50 m, hall 30→120 m); an
aerial pushes it out. Nothing per video touches the presets: pick one per shot, and compose for it (a golden
shot shows sky; a lamp shot needs its own emissive lamps, see sets).

## 4. Sets: `kit/set.ts`, `kit/build.ts`, `kit/blocks.ts`, `kit/paint.ts`, `kit/chpaint.ts`, `kit/water.ts`

A set is a class implementing `SetPiece`: `root: THREE.Group` built once in the constructor, placed at the
set's origin (`root.position.set(...ORIGIN)`), everything static merged into batches; `pose(id, f, cam)` moves
what moves (a boat, a rising building, lamps lighting up), as a pure function of f.

```ts
// sets/harbour.ts: one directory deep, so four `..` reach src/
import * as THREE from "three";
import { Batch, boxGeo, lam, house, prop } from "../../../../cartoon3d/kit/build";
import { block, placeM, groupOf, plankWalk, wagon, stairs, signBoard, M, ub } from "../../../../cartoon3d/kit/blocks";
import { grassHD, stoneHD, cobbleHD, planksHD } from "../../../../cartoon3d/kit/paint";
import { frontHD, sideHD, boardTex, type Front } from "../../../../cartoon3d/kit/chpaint";
import { waterMat } from "../../../../cartoon3d/kit/water";
import { SetPiece, quadUp, V } from "../../../../cartoon3d/kit/set";
import { NOINK } from "../../../../cartoon3d/post/ink";
import { HARBOUR, INN } from "../story";

export class Harbour implements SetPiece {
  root = new THREE.Group();
  constructor() {
    const R = this.root, b = new Batch(), m = new THREE.Matrix4();
    R.position.set(...HARBOUR);
    b.add(quadUp(-400, 400, -400, 400, 0, 8), lam("grass", () => ({ map: grassHD() })));        // ground
    const water = new THREE.Mesh(quadUp(-600, 600, -600, 20, -0.6, 1), waterMat()); water.receiveShadow = true; R.add(water);
    ub(b, M.timber(), m, -6, 6, 0, 0.3, 0, 12);                                                 // a quay deck
    house(b, -14, -20, 0, 8, 7, 4.5, 2);                                                         // a gabled house, style 2
    b.build(R, true);                                                                            // one mesh per material
    const bb = new Batch(); block(bb, { key: "inn", w: 10, d: 12, front: INN }); const g = new THREE.Group(); bb.build(g);
    g.applyMatrix4(placeM(4, 10, -24, false)); R.add(g);                                        // a brick block on the north side
  }
  pose(_id: number, f: number) { /* move what moves */ }
}
```

| export | what it is |
|---|---|
| `Batch` | collects geometry by material and `build(parent, castShadow)`s one mesh per material; `add(geo, mat, matrix?)`, `addObject(object3d, matrix)` |
| `lam(key, () => MeshLambertMaterialParameters)` | a cached two-tone Lambert material (the look's shading); `key` must be unique per look |
| `boxGeo(min: V3, max: V3, tile?)`, `quad(a, b, c, d)`, `tri(a, b, c)`, `quadUp(x0, x1, z0, z1, y, tile?)` | geometry pieces (`quadUp` is a ground quad facing up) |
| `house(b, x, z, yaw, w, d, h, styleIndex, y?)` | a gabled house with a painted facade (left out if it would stand in front of a lens) |
| `prop(b, kit, name, x, y, z, h, yaw?)` | cartoon vegetation by name (`tree` tall, `tree_oak` round, `tree_fat`, `tree_cone`, `plant_bush`, `plant_bushLarge`, `hedge`) scaled to height h, left out when it would stand in a sight line; pass `{}` for `kit` |
| `inTheWay(x0, x1, y0, y1, z0, z1)` | does any camera sight line of the video pass through this box? use it before placing clutter |
| `block(b, { key, w, d, front: Front, cornice?, awning?, chimneys?, flag? })` | a commercial block: painted brick or stucco front with a shopfront and sign (`Front`: wall, brick?, frame, board, ink, name, goods, floors, groundH, floorH, hotel?), real relief; local frame: front on z = 0 facing +z, x 0..w |
| `placeM(x0, w, zFront, faceSouth, y?)` | the matrix that puts a block on a street line |
| `blockH(front)`, `groupOf(batch)` | a block's height; a batch as its own group (for things that move) |
| `plankWalk`, `plankAcross`, `wagon`, `wheel`, `pipe`, `stairs`, `signBoard(root, tex, x, y, z, w, h, yaw, posts, postH?, tilt?)`, `Lifter`, `JackGeo` | street things of the example, reusable as they are |
| `M.trim() / stone() / roof() / iron() / timber() / plank() / wood(c) / col(c)`, `ub(b, mat, m, x0, x1, y0, y1, z0, z1)` | ready materials and a unit box between two corners |
| `paint.ts`: `grassHD`, `cobbleHD`, `stoneHD(key?, cols?, mortar?)`, `planksHD`, `beamHD`, `roofHD(col)`, `brick`, `facadeHD(key, wm, hm, {wall, shutter, door?, timber?, brick?})`, `cloudHD`, `ctex(key, w, h, draw)` | painted canvas textures; `ctex` paints your own with a 2D canvas callback `(g, rnd) => …` (seeded, cached by key) |
| `chpaint.ts`: `frontHD(key, wm, hm, Front)`, `sideHD(key, wm, hm, wall, windows?)`, `mudHD`, `fillHD`, `pavingHD`, `strataHD`, `wallpaperHD`, `boardsHD`, `boardTex(key, w, h, bg, lines: [text, size, colour][], opts?)`, `planTex`, `gaugeTex`, `glowTex`, `letter(g, text, cx, cy, maxW, h, face)`, `texRepeat(t, x, y)` | the example's painters: facades, grounds, a sign board with lines of text, a lamp glow sprite |
| `water.ts`: `waterMat(tint?, k?, flow?)` | the water shader on any `quadUp` (a lake, a river, a puddle); `tint`/`k` pull it toward a colour (muddy), `flow` drifts along +x |
| `post/ink.ts`: `NOINK` | the layer for things the ink pass must skip: emissive windows, glow sprites, your own sprites (`mesh.layers.set(NOINK)`) |

Rules the look depends on: every static thing goes through a `Batch` with `lam` materials (plain three.js
materials shade wrong); dark materials are plum or navy, never black; an emissive (a lit window, a lamp glow)
is a `MeshBasicMaterial` with a colour above 1.0 on the `NOINK` layer, which is what blooms; nothing is
closer than ~2 m to a lens unless it is a deliberate foreground object; keep sets 1000 m apart so one set's
fog and shadows never reach another.

## 5. The cast: `kit/cast.ts`, `kit/toon.ts`

Characters are flat drawings (the bean-head figure drawer, `toon.ts`) on lit cards the world places and
lights (`cast.ts`). `stage(id, f, cam)` returns `{ places: Place[], fx: FxPlace[] }`; you build it from the
helpers the example's `scenes.ts` defines over the kit (copy their shape into your `scenes.ts`; they are a
dozen lines each): `stand(out, cam, t, i, outfit, x, y, z, opts?, scale?)`, `walk(out, cam, t, i, outfit,
from, to, t0, t1, opts?)`, `pusher(...)` (side view, pushing a bar), `horse(...)`, `fx(out, key, cw, ch, draw,
x, y, z, w, h, extra?)`. Every helper calls the kit's primitives:

| export | what it is |
|---|---|
| `prepare(light, cam)` | first line of `stage()`: the contact-shadow colours and the sun the cards are drawn toward |
| `person(cam, who: {i, o, okey}, x, y, z, view: {side, mirror}, frontOpts, sideOpts, scale?)` | one character drawing: front view (`bodyFront`) or side view (`bodySide`), sized by distance, lit from the scene's sun; push the result into `out.places` |
| `blob(out, x, y, z, scale?, k?)` | the contact shadow under a standing figure (always, or they float) |
| `viewOf(cam, x, z, dx, dz)` | front or side view, mirrored or not, for someone walking along (dx, dz) |
| `lidAt(t, i, swaps?)` | eyelid position: blinks every 0.5–2.3 s and across every expression swap |
| `hh(i, salt?)`, `q(v, n?)` | a hash in [0, 1); quantise (drawings are cached by their rounded options) |
| `LEAD` | 2/30 s: a reaction lands this early before its word |
| `type CamInfo = { pos, right, sun? }`, `type Stage`, `type Place`, `type FxPlace`, `type Who` | the types |

`toon.ts` is the drawer: `Outfit` (`jacket`, `pants`, `boots`, `hat?`: "tophat" | "bonnet" | "cap" | "hair" |
"shako" | "shako_tall" | null, `cap?`, `hair?`, `dress?`, `coat?`: "tails" | "long", `belt?`, `buttons?`, `moustache?`,
`beard?`, `skin?` (from `SKINS`), `build?`: "adult" | "stout" | "kid", `holds?`: "paper" | "bundle" | "satchel"
| "cane" | "flag" | "lantern", `heldColor?`, `rifle?`, `sash?`, `sword?`), `Expr` (neutral, stern, grin, laugh,
whistle, nervous, shock, relief, relief_open, dazed, pained, smile, smile_closed, lick), `Prop` held in the
hand (icecream, shako, ["hammer", 0..1], ["shovel", 0..1], ["trowel", 0..1], whistle, basket, valise, cloth,
teacup, point), `FrontOpts` (`mode`: march | stroll | stand | sit | fall, `phase`, `expr`, `look` (−1..1),
`blink`, `prop`, `tilt`, `headTilt`, `wave`), `SideOpts` (`mode`: march | stand | swing | push, `phase`,
`pose`, `stride`, `stomp`, `hand`), ready outfits (`townsfolk(v)`, `soldier(v)`, `KID`, `PARENT`, `OFFICER`,
`RIFLEMAN`), the horse (`horseSide`) and the effect drawings (`fxBurst`, `fxSplash`, `fxPuff`, `fxStars`,
`fxCreak`, `fxRing`, `fxSign`, `fxCloud`, `fxMud`, `fxFlies`, `fxDirt`, `fxBlast`, `fxSteam`, `fxTremble`, `fxNote`),
each `(pen, t|seed) => void`, placed with `fx(...)`. A role reads from costume and the held thing: a captain is
a frock coat, a top hat and a cane; a clerk is shirtsleeves and a paper. Write each named character as one
`Outfit` constant with a distinct silhouette and colour, and keep its `i` (the identity hash) fixed across shots.

Staging rules: a figure's feet are at its `y` (the ground or deck height there); scale 1 is an adult, 0.9 a
seated one sunk to the chair; a sitting figure is `mode: "sit"`; a walking one has `t0`/`t1` in seconds and
walks at 1.4 m/s; a reaction is `expr`/`look`/`wave` switched at `t >= word/FPS - LEAD`; crowds are
deterministic (`hh(i, k)`) and stand still while the camera supplies the motion; nobody stands in the lower
~22 % of the frame (the caption band), and nobody is cut by the frame edge.

## 6. The runner: `CartoonShort.tsx`

`<CartoonShort video={VIDEO} frame={f} />` builds one `World` from the `VideoDef`, poses it per frame and
runs the post chain (ink, lens blur, bloom, neutral tone map, grade). `INK_DEFAULTS` per kind of shot
(exterior, aerial, interior) are chosen from `outdoor(set)` and `aerial`; `inkFor(shot)` overrides them when
a set's geometry draws too much ink (the example thins the crawlspace's).

## 7. The numbers the look is judged by (the verifier's targets, condensed)

Day frame luma median ~0.57, golden ~0.52; lit chroma C* median ≥ 32; sky frame-top C* ≥ 45 by day, every
stop ≥ 40 at golden; ink 2–2.6 % of pixels, 3–5 px near, fading past 150 m, never on wall/floor joins; day
shade ~0.5 × lit in the same hue, golden shade violet; characters 3.5 heads tall, lit by the scene, on the
ground, not under the captions; DOF on about a third of shots, focus on the eyes; horizon 0.40–0.50; lens at
eye level; a foreground object in about a third of shots; every hold creeps. The full list with its
measurements is in the verifier's prompt (`reference/verifier.md`).
