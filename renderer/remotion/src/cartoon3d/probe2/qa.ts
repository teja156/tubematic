// PROBE 2 — the deterministic frame QA check (TMDEV-179 layer 1).
//
// Runs HEADLESS in Node on EVERY frame, no GPU, no render. It imports only the
// pure worldKit, and builds its collision proxies from the SAME `layout()` the
// renderer uses — round 1 re-derived scatter positions with its own RNG and
// tested trees that were never where they were drawn.
//
// BLOCK = a fact (a ray hits a wall; a body stands inside a crate; feet must
// slide at this speed). ADVISE = a threshold somebody chose (size, density).
import * as THREE from "three";
import { applyCameraState, cameraStateAt } from "./cameraMotion";
import { motionOf, type SceneOpts } from "./sceneOpts";
import { validatePartSpec } from "./partGrammar";
import { isCodePart, PART_KINDS, RESERVED_PART_NAMES } from "./partsSpec";
import { validateCodePart } from "./partSpecs/code/measure";
import { BeatSpec, Box, buildBeats, castHeight, castPosition, followShift, inBox, isSolid, layout, MAX_WALK_MPS, Placed, propPoseAt, WorldSpec } from "./worldKit";
import { validateFigure } from "../kit/figureCheck";
import { FIGURE_GESTURES } from "../kit/Figure";
import { BOY_GESTURES } from "../carrington/newsboy";
import { OP_GESTURES } from "../carrington/operator";
/** a named prop may be a vehicle under way; faster than this is a cue typo */
const MAX_PROP_MPS = 25;

/** a subject smaller than this in a 1920px-tall frame reads as a speck */
const MIN_SUBJECT_PX = 300;
/** CompositionBuilder's captions sit centred at 78% of the frame height (Subtitles
 *  `position` default); two lines of 62px span roughly 70%..86%. A face there is
 *  covered by words — and in a Short, by the platform's own UI too. */
const CAPTION_BAND: [number, number] = [0.7, 0.86];
/** a non-building prop in front of the subject wider than this share of the frame */
const MAX_FOREGROUND_FRAC = 0.28;
/** a shot with fewer solid things than this near the camera reads as bare */
const MIN_IN_FRAME = 8;
const DENSITY_RANGE_M = 20;

const proxy = (b: Box, tag: string) => {
  const m = new THREE.Mesh(new THREE.BoxGeometry(b.w, Math.max(b.h, 0.01), b.d));
  m.position.set(b.cx, b.y0 + b.h / 2, b.cz);
  m.rotation.y = b.yaw;
  m.userData.tag = tag;
  m.updateMatrixWorld(true);
  return m;
};

export interface Finding {
  frame: number;
  beat: number;
  who: string;
  kind: "offscreen" | "occluded" | "too-fast" | "inside" | "prop-in-building" | "tiny" | "bare" | "lens-clutter" | "sign-cropped" | "under-captions" | "bad-part";
  gate: "block" | "advise";
  detail: string;
}

/** The deterministic half of the part gate: a world's own parts must be sound
 *  before anything is laid out on them (a bad spec has no honest footprint). */
/** the code parts a world names anywhere (props, clusters, scatter, foreground framing) */
export const codePartsUsed = (spec: WorldSpec): string[] => {
  const names = new Set<string>();
  for (const p of spec.pieces) {
    if (p.kind === "prop" && isCodePart(p.what)) names.add(p.what);
    if (p.kind === "cluster") for (const w of p.what) if (isCodePart(w)) names.add(w);
    if (p.kind === "scatter" && isCodePart(p.what)) names.add(p.what);
  }
  for (const s of spec.shots) if (s.fg && isCodePart(s.fg.what)) names.add(s.fg.what);
  return [...names];
};

export const checkCast = (spec: WorldSpec): Finding[] => [
  ...Object.entries(spec.cast ?? {}).flatMap(([name, fig]) =>
    validateFigure(name, fig).map((e) => ({ frame: 0, beat: -1, who: name, kind: "bad-part" as const, gate: "block" as const, detail: e }))),
];

export const checkParts = (spec: WorldSpec): Finding[] => [
  ...Object.entries(spec.parts ?? {}).flatMap(([name, part]) => {
    const errs = validatePartSpec(part, RESERVED_PART_NAMES);
    if (part && typeof part === "object" && part.name !== name) errs.unshift(`parts["${name}"].name is "${part.name}": the key and the name must match`);
    return errs.map((e) => ({ frame: 0, beat: -1, who: name, kind: "bad-part" as const, gate: "block" as const, detail: e }));
  }),
  ...codePartsUsed(spec).flatMap((name) =>
    validateCodePart(name, [...PART_KINDS]).map((e) => ({ frame: 0, beat: -1, who: name, kind: "bad-part" as const, gate: "block" as const, detail: e })),
  ),
];

export const checkWorld = (spec: WorldSpec, sheet: BeatSpec[], opts: SceneOpts = {}) => {
  const bad = checkParts(spec);
  if (bad.length) return { findings: bad, counts: {} as Record<string, number> };
  // the SAME camera function the renderer uses, so every verdict is about a
  // frame that will actually be rendered
  const motion = motionOf(opts);
  const beatOf = (f: number) => {
    let found = sheet[0];
    for (const b of sheet) {
      if (f >= b.start) found = b;
      if (f >= b.start && f <= b.end) return b;
    }
    return found;
  };
  const camAt = (f: number) => {
    const cs = cameraStateAt(beats, f, motion);
    const sh = followShift(L, sheet, beatOf(f), f);
    if (sh.lengthSq() > 0) cs.pose = { ...cs.pose, pos: [cs.pose.pos[0] + sh.x, cs.pose.pos[1], cs.pose.pos[2] + sh.z], target: [cs.pose.target[0] + sh.x, cs.pose.target[1], cs.pose.target[2] + sh.z] };
    return cs;
  };
  const findings: Finding[] = [];
  const badCast = checkCast(spec);
  for (const beat of sheet) for (const r of beat.cast) {
    const bi = sheet.indexOf(beat);
    const bad = (detail: string) => badCast.push({ frame: beat.start, beat: bi, who: r.who, kind: "bad-part", gate: "block", detail });
    if (!(r.who === "newsboy" || r.who === "operator" || spec.cast?.[r.who])) { bad(`beat names cast member "${r.who}", who is neither newsboy, operator, nor in world.cast`); continue; }
    // gestures and cues are data from the author: an unknown gesture would crash the drawer mid-render
    const known: readonly string[] = r.who === "newsboy" ? BOY_GESTURES : r.who === "operator" ? OP_GESTURES : FIGURE_GESTURES;
    if (r.gesture !== undefined && !known.includes(r.gesture)) bad(`gesture "${r.gesture}" is not one ${r.who} can make (${known.join(", ")})`);
    (r.cues ?? []).forEach((c, i) => {
      const prev = r.cues![i - 1];
      if (!Number.isInteger(c.frame) || c.frame < beat.start || c.frame > beat.end) bad(`cue ${i} at frame ${c.frame} is outside the beat (frames ${beat.start}-${beat.end})`);
      else if (prev && c.frame <= prev.frame) bad(`cue ${i} at frame ${c.frame} is not after cue ${i - 1} (frame ${prev.frame}): cues are in frame order`);
      if (c.gesture !== undefined && !known.includes(c.gesture)) bad(`cue ${i}: gesture "${c.gesture}" is not one ${r.who} can make (${known.join(", ")})`);
      if (c.gesture === undefined && c.headTurn === undefined) bad(`cue ${i} changes nothing: give it a gesture or a headTurn`);
    });
  }
  if (badCast.length) return { findings: badCast, counts: {} as Record<string, number> };
  const L = layout(spec);
  const solidsAll = L.placed.filter(isSolid);
  const occAll = solidsAll.flatMap((p) => p.boxes.map((b) => proxy(b, p.tag)));
  const beats = buildBeats(L, sheet);
  // named props may move or hide per frame: their boxes and proxies follow propPoseAt, the renderer's function
  const named = solidsAll.filter((p): p is Extract<Placed, { kind: "prop" }> => p.kind === "prop" && !!p.name);
  const namedSet = new Set<Placed>(named);
  const occOf = new Map<Placed, typeof occAll>();
  {
    let k = 0;
    for (const p of solidsAll) occOf.set(p, p.boxes.map(() => occAll[k++]));
  }
  let solids = solidsAll;
  let occ = occAll;
  const poseProps = (f: number) => {
    if (!named.length) return;
    const shown = new Set<Placed>();
    for (const p of named) {
      const pose = propPoseAt(L, sheet, p, f);
      if (!pose.visible) continue;
      shown.add(p);
      p.boxes.forEach((b, j) => {
        b.cx = pose.pos.x; b.cz = pose.pos.z; b.y0 = pose.pos.y; b.yaw = pose.yaw;
        const o = occOf.get(p)![j];
        o.position.set(b.cx, b.y0 + b.h / 2, b.cz);
        o.rotation.y = b.yaw;
        o.updateMatrixWorld(true);
      });
    }
    solids = solidsAll.filter((p) => !namedSet.has(p) || shown.has(p));
    occ = solids.flatMap((p) => occOf.get(p)!);
  };
  // a prop cue that would have the prop cover more ground than a vehicle plausibly can
  sheet.forEach((beat, bi) => {
    for (const c of beat.props ?? []) {
      // any named prop, solid or not (a fog bank or a decal can be cued too; only solids get occlusion proxies)
      const p = L.placed.find((n): n is Extract<Placed, { kind: "prop" }> => n.kind === "prop" && n.name === c.name);
      if (!p) { findings.push({ frame: beat.start, beat: bi, who: c.name, kind: "bad-part", gate: "block", detail: `beat cue names "${c.name}" but no prop piece has that name` }); continue; }
      const { speed } = propPoseAt(L, sheet, p, beat.end);
      if (speed > MAX_PROP_MPS) findings.push({ frame: beat.start, beat: bi, who: c.name, kind: "too-fast", gate: "block", detail: `${c.name} would move at ${speed.toFixed(1)} m/s in this beat (max ${MAX_PROP_MPS})` });
    }
  });
  const cam = new THREE.PerspectiveCamera(50, 1080 / 1920, 0.1, 600);
  const ray = new THREE.Raycaster();
  const frustum = new THREE.Frustum();
  const last = sheet[sheet.length - 1].end;
  const seen = new Set<string>();
  const push = (f: Finding) => {
    const key = `${f.beat}:${f.who}:${f.kind}`;
    if (seen.has(key)) return;
    seen.add(key);
    findings.push(f);
  };

  // --- static: an explicitly placed prop sitting inside a building
  const buildings = L.placed.filter((p) => p.kind === "building");
  for (const p of L.placed) {
    if (p.kind !== "prop" || !p.explicit) continue;
    const hit = buildings.find((b) => b.boxes.some((bx) => inBox(bx, p.pos.x, p.pos.z, 0.1)));
    if (hit) push({ frame: 0, beat: -1, who: "-", kind: "prop-in-building", gate: "block", detail: `${p.tag} sits inside ${hit.tag}` });
  }

  // --- per beat: walk speed, and how much world the shot actually contains
  sheet.forEach((beat, bi) => {
    for (const role of beat.cast) {
      const { speed } = castPosition(L, beat, role, beat.start);
      if (speed > MAX_WALK_MPS) {
        push({
          frame: beat.start, beat: bi, who: role.who, kind: "too-fast", gate: "block",
          detail: `walk ${role.mark}->${role.to} needs ${speed.toFixed(2)} m/s; the rig draws at most ${MAX_WALK_MPS.toFixed(2)} m/s before the feet slide`,
        });
      }
    }
    const mid = Math.round((beat.start + beat.end) / 2);
    poseProps(mid);
    applyCameraState(cam, camAt(mid));
    frustum.setFromProjectionMatrix(new THREE.Matrix4().multiplyMatrices(cam.projectionMatrix, cam.matrixWorldInverse));
    const inFrame = solids.filter((p) =>
      p.boxes.some((b) => {
        const c = new THREE.Vector3(b.cx, b.y0 + b.h / 2, b.cz);
        return c.distanceTo(cam.position) < DENSITY_RANGE_M && frustum.containsPoint(c);
      }),
    ).length;
    // A prop in FRONT of the subject that spans a big share of the frame width
    // reads as a smear across the shot. Buildings are exempt: filling the frame
    // is a wall's job. Measured on screen, because size-in-frame is the defect,
    // not distance — round 2's sacks were 5 m away and still covered 40%.
    const subjectDist = camAt(mid).pose.focus;
    for (const p of solids) {
      if (p.kind === "building") continue;
      for (const b of p.boxes) {
        const c = new THREE.Vector3(b.cx, b.y0 + b.h / 2, b.cz);
        if (c.distanceTo(cam.position) >= subjectDist - 0.5) continue;
        const corners = new THREE.Box3().setFromObject(proxy(b, p.tag));
        const pts = [0, 1].flatMap((i) => [0, 1].flatMap((j) => [0, 1].map((k) => new THREE.Vector3(
          i ? corners.max.x : corners.min.x, j ? corners.max.y : corners.min.y, k ? corners.max.z : corners.min.z))));
        const ndc = pts.map((v) => v.clone().applyMatrix4(cam.matrixWorldInverse)).filter((v) => v.z < -0.05)
          .map((v) => v.applyMatrix4(cam.projectionMatrix));
        if (ndc.length < 2) continue;
        const xs = ndc.map((v) => Math.max(-1, Math.min(1, v.x)));
        const ys = ndc.map((v) => Math.max(-1, Math.min(1, v.y)));
        const wFrac = (Math.max(...xs) - Math.min(...xs)) / 2;
        const onScreen = Math.max(...ys) > -1 && Math.min(...ys) < 1 && Math.max(...xs) > -1 && Math.min(...xs) < 1;
        if (onScreen && wFrac > MAX_FOREGROUND_FRAC) {
          push({ frame: mid, beat: bi, who: p.tag, kind: "lens-clutter", gate: "advise", detail: `${p.tag} spans ${(wFrac * 100).toFixed(0)}% of the frame width in front of the subject in shot "${beat.shot}"` });
        }
      }
    }
    if (inFrame < MIN_IN_FRAME) {
      push({ frame: mid, beat: bi, who: "-", kind: "bare", gate: "advise", detail: `only ${inFrame} solid things within ${DENSITY_RANGE_M}m in shot "${beat.shot}" (want >= ${MIN_IN_FRAME})` });
    }
  });

  // --- per frame: can the camera see each cast member, and are they standing in something
  const beatAt = (f: number) => {
    let found = 0;
    for (let i = 0; i < sheet.length; i++) {
      if (f >= sheet[i].start) found = i;
      if (f >= sheet[i].start && f <= sheet[i].end) return i;
    }
    return found;
  };
  const signs = L.placed.flatMap((p) => (p.kind === "building" && p.sign ? [{ tag: p.tag, text: p.piece.sign!.text, corners: p.sign }] : []));
  for (let f = 0; f <= last; f++) {
    poseProps(f);
    applyCameraState(cam, camAt(f));
    frustum.setFromProjectionMatrix(new THREE.Matrix4().multiplyMatrices(cam.projectionMatrix, cam.matrixWorldInverse));
    const bi = beatAt(f);
    const beat = sheet[bi];
    // Words cut by the frame edge (the 3D twin of the DOM path's text_offscreen).
    // Fully in or fully out is fine; half a word is not — on a HELD shot. During
    // the glide between beats a sign sliding out of frame is just camera motion.
    const held = f >= beat.start && f <= beat.end;
    for (const sg of held ? signs : []) {
      const pts = sg.corners.map((c) => c.clone().applyMatrix4(cam.matrixWorldInverse));
      if (pts.every((v) => v.z > -0.05)) continue; // entirely behind the camera
      const ndc = pts.map((v) => (v.z < -0.05 ? v.clone().applyMatrix4(cam.projectionMatrix) : null));
      const front = ndc.filter((v): v is THREE.Vector3 => v !== null);
      const xs = front.map((v) => v.x);
      const ys = front.map((v) => v.y);
      const overlaps = Math.max(...xs) > -1 && Math.min(...xs) < 1 && Math.max(...ys) > -1 && Math.min(...ys) < 1;
      const contained = front.length === 4 && xs.every((x) => x >= -1 && x <= 1) && ys.every((y) => y >= -1 && y <= 1);
      // a far sign a few pixels tall is scenery, not a word the viewer reads: below 14 px (of 1920) it cannot be "cut"
      const tallPx = front.length ? ((Math.max(...ys) - Math.min(...ys)) / 2) * 1920 : 0;
      if (overlaps && !contained && tallPx >= 14) {
        push({ frame: f, beat: bi, who: sg.tag, kind: "sign-cropped", gate: "block", detail: `sign "${sg.text}" on ${sg.tag} is cut by the frame edge in shot "${beat.shot}"` });
      }
    }
    for (const role of beat.cast) {
      const { at } = castPosition(L, beat, role, f);
      const h = castHeight(spec, role.who);

      const standingIn = solids.find((p) => p.boxes.some((b) => b.y0 < 0.5 && inBox(b, at.x, at.z, 0.18)));
      if (standingIn) {
        push({ frame: f, beat: bi, who: role.who, kind: "inside", gate: "block", detail: `standing inside ${standingIn.tag}` });
      }

      const head = at.clone().setY(at.y + h * 0.92);
      const foot = at.clone().setY(at.y + 0.02);
      if (!frustum.containsPoint(head)) {
        push({ frame: f, beat: bi, who: role.who, kind: "offscreen", gate: "block", detail: `head outside the frame of shot "${beat.shot}"` });
        continue;
      }
      const dir = head.clone().sub(cam.position);
      const dist = dir.length();
      ray.set(cam.position, dir.normalize());
      ray.far = dist - 0.05;
      const hit = ray.intersectObjects(occ, false)[0];
      if (hit) {
        push({ frame: f, beat: bi, who: role.who, kind: "occluded", gate: "block", detail: `head hidden by ${hit.object.userData.tag} at ${hit.distance.toFixed(1)}m (subject at ${dist.toFixed(1)}m) in shot "${beat.shot}"` });
        continue;
      }
      // keep faces and chests out of the caption band (frame fraction from the top)
      const down = (v: THREE.Vector3) => (1 - v.clone().project(cam).y) / 2;
      const chest = at.clone().setY(at.y + h * 0.6);
      if (down(head) > CAPTION_BAND[0] && down(head) < CAPTION_BAND[1]) {
        push({ frame: f, beat: bi, who: role.who, kind: "under-captions", gate: "block", detail: `head is in the caption band (${(down(head) * 100).toFixed(0)}% down) in shot "${beat.shot}"` });
      } else if (down(chest) > CAPTION_BAND[0] && down(chest) < CAPTION_BAND[1]) {
        push({ frame: f, beat: bi, who: role.who, kind: "under-captions", gate: "advise", detail: `chest is in the caption band (${(down(chest) * 100).toFixed(0)}% down) in shot "${beat.shot}"` });
      }
      // a walk-in may start small; judge size once it is under way
      const span = Math.max(1, beat.end - beat.start);
      const into = (f - beat.start) / span;
      if (role.action === "walk" && into < 0.25) continue;
      const px = (Math.abs(head.clone().project(cam).y - foot.clone().project(cam).y) / 2) * 1920;
      if (px < MIN_SUBJECT_PX) {
        push({ frame: f, beat: bi, who: role.who, kind: "tiny", gate: "advise", detail: `${px.toFixed(0)}px tall of 1920 in shot "${beat.shot}" (want >= ${MIN_SUBJECT_PX})` });
      }
    }
  }
  return { findings, counts: countPlaced(L) };
};

const countPlaced = (L: ReturnType<typeof layout>) => {
  const c: Record<string, number> = {};
  for (const p of L.placed) {
    const k = p.kind === "prop" ? `prop:${p.what}` : p.kind;
    c[k] = (c[k] ?? 0) + 1;
  }
  return c;
};
