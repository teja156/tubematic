# The Low-Poly Skit kit: what a video is written against

The kit lives in the renderer at `renderer/remotion/src/cartoon3d/lowpoly/` and is frozen: `cartoon_kit_list()`
names every file, `cartoon_kit_read(path)` shows one (`lowpoly/figure.ts`, `lowpoly/examples/dig/story.ts`).
Your files sit under `src/scenes/generated/<video_id>/`, so the kit is imported as
`../../../cartoon3d/lowpoly/<file>` (and `../../../cartoon3d/camera`) from a file at the top of that directory and
as `../../../../cartoon3d/...` one directory deeper. Units are metres; `y` is up; a figure stands **1.0 tall** with
its feet at `y = 0` facing `+z`; 30 frames per second; the front of a room is `+z` (the camera looks toward `-z`).

## 1. The contract: `def.ts`

```ts
export type LPShot = { id: number; a: number; b: number; set: string; note: string };   // frames [a, b), b exclusive
export interface LowPolyDef {
  total: number;                                  // = timeline.totalFrames
  shots: LPShot[];                                // tile 0..total, one set per shot
  camAt(id: number, f: number): Cam;              // the camera, every frame (camera.ts below)
  sets(): Record<string, SetPiece>;               // built once; place every set far from the others (100 m apart in x)
  background(set: string): string;                // the colour behind a set: a grey for a diorama, near black for space
  light?(shot: LPShot): Partial<LowPolyLight>;    // ambient, key, keyFrom, keyColor, fill, fillColor (defaults are warm and soft)
  blurAt?(id: number, f: number): number;         // 0..1 to smear a frame (a whip, an impact); 4 renders on those frames
}
interface SetPiece { root: THREE.Group; pose(id: number, f: number, cam: THREE.PerspectiveCamera): void }
```

A set builds its figures, props and effects once in the constructor and moves them in `pose`, a pure function of
the frame (no `Math.random`). The runner shows only the set of the current shot, with no outlines, shadows, lens
blur, bloom or grade: flat colour and facets.

## 2. The figure: `figure.ts`, `faces.ts`

```ts
const hero = buildFigure({ ...HOUSE, shirt: "#2f9aa8" });   // a Figure: root, body, joints, headMount, handL, handR
this.root.add(hero.root);  hero.root.position.set(x, y, z);  hero.root.rotation.y = yaw;  hero.root.scale.setScalar(k);
setFace(hero.headMount, "grin");                             // a hard swap; mouths never move with speech
```

- `Outfit` = `{ skin, hair, hairStyle: "cap" | "tuft" | "bob" | "bald", shirt, trousers, boots, sole, stubble? }`.
  Palettes: `SKINS`, `HAIRS`, `SHIRTS`, `TROUSERS`; `randomOutfit(mulberry(seed))` is a seeded pick. Everyone shares
  one mesh; people differ by colour, hair and stubble.
- Faces: `neutral smile smug shock shout worry grin blank`. Swap on the frame the word lands.
- `root` is where the figure stands (position, yaw, scale belong to the set); `body` is inside it and posed by
  `applyPose` (a lie-down or a lift). A prop in a hand: `hero.handR.add(prop)`.

## 3. Poses and cycles: `poses.ts`, `cycles.ts`

```ts
applyPose(fig, POSES.bang);                                  // names: stand sit lie fall thrust bang point hold cheer shrug slump stomp flinch
applyPose(fig, poseTrack([{ f: 36, pose: POSES.stand }, { f: 40, pose: POSES.bang, dur: 3 }], f));   // a snap in `dur` frames (2 to 6)
applyPose(fig, walkPose(f - f0, speed));  applyPose(fig, dancePose(f));  applyPose(fig, idlePose(f, seed));
footfalls(f0, f1, startedAt)                                 // the frames a foot lands (every 11): jolt the camera and the audio there
```

A pose is plain numbers: `{ y, pitch, roll, lean, twist, side, nod, turn, tilt, shL, shR, elL, elR, hipL, hipR, knL, knR }`
(`shL: [fwd, out]` raises forward and away from the body; `elL: bend`; `knL: bend` folds the shin back). Anything a
pose leaves out is at rest. Write your own as an object, or blend: `lerpPose(a, b, k)`. A pose snaps; a fall is a
pose change, not a simulation.

## 4. Crowds: `crowd.ts`

```ts
const members = Crowd.block(cols, rows, { x0, z0, dx: 0.4, dz: 0.5, rise: 0.1, seed: 9, outfit: randomOutfit, smileRate: 0.4 });
const crowd = new Crowd(members, (f, bucket) => dancePose(f + bucket * 2));   // 12 phase buckets; a few hundred figures is fine
this.root.add(crowd.root);   // pose(): crowd.update(f)
```

Members share a cycle and differ by bucket (phase), outfit and place. Build a stand or a street from several
blocks. Draw calls stay about two dozen however many people there are.

## 5. Effects: `fx.ts`

`new Burst(size, hold)` (a yellow star: `.at(frame, [x,y,z])`, `.update(f, camera)`), `new Debris(n, seed, life)` (chips
thrown and falling), `new ComicWord("BANG!", width, hold)` (a red outlined word that scales up in 2 frames),
`lightCone(h, r)` (an additive spotlight), `ramp(f, f0, dur)`. Start all of them on the hit's frame, and call
`update` in `pose`.

## 6. Dioramas: `diorama.ts`

`room({ w, d, h, wall, floor })` (a room with its front off), `box(parent, w, h, d, colour, x, y, z)`,
`cyl(parent, r, h, colour, x, y, z)`, `sign(parent, text, w, h, { bg, fg, x, y, z })` (text on a plane: a clock,
a label), `globe(parent, r, { sea, land, seed })`, `strata(parent, w, d, layers)` (a cutaway of layers),
`discs(parent, rings)` (a cross-section of a ball). A set is a few dozen of these; flat colours, no textures.

## 7. Camera: `../camera.ts` (shared with Cartoon 3D) and the low-poly moves

`runKeys(keys, f)`, `dolly(pos, look, k)` with `pushK(f, f0, rate)` for a push-in (rate 0.003 to 0.005 per
frame), `glide`, `rolled`; and new here: `joltAt(hits, f)` with `jolted(cam, a)` (a vertical jolt for 6 frames
on each hit frame; multiply `a` for a bigger hit) and `whip(camA, camB, f, f0, dur = 12)` returning
`{ cam, blur }` (a hard-eased move between two framings; hand `blur` to `blurAt`). Hold a framing 7 frames, whip
12, settle 4. Hard cuts between shots: there is no crossfade.

```ts
export const camAt = (id: number, f: number): Cam =>
  jolted(runKeys(KEYS[id], f), joltAt(id === 1 ? footfalls(0, 30, 0) : HITS, f));
```

## Numbers that hold

Shots 15 to 75 frames, median about 30. Push-in 0.3 to 0.5 % a frame. A step every 11 frames, a jig lift every
5, a snap 2 to 6, a burst held about 4 frames, a comic word about 18. Camera at 0.8 to 1.6 m for people, fov 36 to 42.
Keep the subject in the upper 60 % of the frame: the captions sit at 65 % down.
