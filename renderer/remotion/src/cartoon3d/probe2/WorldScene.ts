// PROBE 2 — the shipped scene machinery, with NO knowledge of any place.
// Everything place-specific arrives as a WorldSpec + BeatSpec[]. This is the
// file that would become the real installed Cartoon 3D component.
import * as THREE from "three";
import type { Beat } from "../kit/cameraPath";
import { applyCameraState, cameraStateAt } from "./cameraMotion";
import { motionOf, type SceneOpts } from "./sceneOpts";
import { Cutout } from "../kit/Cutout";
import { Figure, type FigureGesture, smoother } from "../kit/Figure";
import type { Dof, Grade } from "../kit/InkPipeline";
import { clamp01, hash, lerp } from "../kit/prng";
import { makeSky } from "../kit/Sky";
import type { PostFrame } from "../kit/post/PostStack";
import { TONE, twoTone } from "../kit/post/shade";
import { LIGHTS, LOOK } from "../kit/post/lights";
import { LEAD, lidAt } from "../kit/rig";
import { drawNewsboy, type BoyGesture } from "../carrington/newsboy";
import { drawOperator, type OpGesture } from "../carrington/operator";
import { makeCyc, type Cyc } from "./cyc";
import { goldAmount, gradeAt, lightsAt, num, S, skyAt, skyStops } from "./look";
import { updateWater } from "../kit/Water";
import { makeAtmosphere, makeSway } from "./atmosphere";
import { buildWorld, type BuiltWorld } from "./worldBuild";
import {
  BeatSpec, buildBeats, castPosition, followShift, FPS, layout, Layout, MAX_STRIDE, propPoseAt, STRIDE_PER_M, STEPS_PER_S,
  WALK_CYCLE_FRAMES, WorldSpec, gestureAt } from "./worldKit";
import { CODE_PARTS } from "./partSpecs/code/index";

export { FPS };

/** Per-video options that are not part of the world: camera grammar (kicks,
 *  emphasis, rolls) and anything else timed to the voice-over. Filled in as
 *  the round-3 pieces land. */
export type { SceneOpts } from "./sceneOpts";

const C = (r: number, g: number, b: number) => new THREE.Color(r, g, b);
const TONE_V = new THREE.Vector3();
export class WorldScene {
  readonly scene = new THREE.Scene();
  readonly camera = new THREE.PerspectiveCamera(50, 1080 / 1920, 0.1, 600);
  private sky = makeSky();
  private key = new THREE.DirectionalLight(0xffffff, 3);
  private hemi = new THREE.HemisphereLight(0xffffff, 0x444444, 1);
  /** CAMERA-SIDE FILL: a soft shadowless light from just above the lens, the
   *  cartoon equivalent of a reflector. Whatever faces the camera is never
   *  black, however the sun sits (Klondike's shaded storefronts went to mud). */
  private fill = new THREE.DirectionalLight(0xffffff, 0.8);
  private L: Layout;
  private world: BuiltWorld;
  private atmos: ReturnType<typeof makeAtmosphere>;
  private sway: (f: number) => void;
  private cyc: Cyc | null = null;
  private op = new Cutout(1.72);
  private boy = new Cutout(1.26);
  /** the world's own people (WorldSpec.cast), drawn by the cast grammar */
  private figures = new Map<string, Figure>();
  private fog: THREE.Fog;
  private beats: Beat[];
  private durationFrames: number;
  grade!: Grade;
  dof!: Dof;
  /** what the v2 post stack needs per frame (focus, blur, day/golden blend) */
  post: PostFrame = { focus: 8, cInf: 0, golden: 0 };
  private inkFog: PostFrame["inkFog"];

  constructor(
    private spec: WorldSpec,
    private sheet: BeatSpec[],
    shadows: boolean,
    backdropTex?: THREE.Texture,
    readonly opts: SceneOpts = {},
  ) {
    const s = this.scene;
    // the worlds were authored against a heavier fog; a third more range
    // keeps the aerial perspective but stops the midground going hazy
    this.fog = new THREE.Fog(0xffffff, spec.fog.near * 1.3, spec.fog.far * 1.3);
    s.fog = this.fog;
    s.add(this.sky.sky);

    if (spec.backdrop && backdropTex) {
      this.cyc = makeCyc(backdropTex, spec.backdrop);
      s.add(this.cyc.mesh);
    }

    this.L = layout(spec);
    this.world = buildWorld(this.L);
    s.add(this.world.root);
    s.add(this.op.mesh, this.boy.mesh);
    for (const [name, fig] of Object.entries(spec.cast ?? {})) {
      const f = new Figure(fig);
      this.figures.set(name, f);
      s.add(f.mesh);
    }
    this.atmos = makeAtmosphere({ seed: spec.ground.seed + 11, ...(spec.atmos ?? {}), smoke: this.world.smoke });
    s.add(this.atmos.group);
    this.sway = makeSway(this.world.trees, spec.ground.seed + 13);

    this.beats = buildBeats(this.L, sheet);
    this.durationFrames = sheet[sheet.length - 1].end + 1;

    this.key.castShadow = shadows;
    this.key.shadow.mapSize.set(2048, 2048);
    const sc = this.key.shadow.camera;
    sc.left = -34;
    sc.right = 34;
    sc.top = 34;
    sc.bottom = -34;
    sc.near = 1;
    sc.far = 150;
    this.key.shadow.bias = -0.0008;
    this.key.shadow.normalBias = 0.03;
    this.key.target.position.set(0, 0, 0);
    this.fill.castShadow = false;
    s.add(this.key, this.key.target, this.hemi, this.fill, this.fill.target);
    if (opts.post === "v2" && opts.shade !== "lambert") this.applyTwoTone();
  }

  /** v2 look: every world Lambert material becomes two-tone (kit/post/shade.ts). Character cards keep their own
   *  lit-normal shader (they are the meshes with a customDepthMaterial); unlit materials are left alone. */
  private applyTwoTone() {
    const done = new WeakSet<THREE.Material>();
    this.scene.traverse((o) => {
      const m = o as THREE.Mesh;
      if (!m.isMesh || m.customDepthMaterial) return;
      const mats = Array.isArray(m.material) ? m.material : [m.material];
      for (const mat of mats) {
        if (!mat || done.has(mat)) continue;
        done.add(mat);
        if ((mat as THREE.MeshLambertMaterial).isMeshLambertMaterial) twoTone(mat as THREE.MeshLambertMaterial);
      }
    });
  }

  setResolution(heightPx: number) {
    void heightPx; // no point sprites in this world
  }

  private tmpV = new THREE.Vector3();
  /** A flat card is lit like the props around it: by the key (through a fixed
   *  "lit normal" that faces the sun, so no camera move changes its light) and
   *  the sky, plus every practical light near it (the campfire, a lamp, a lit
   *  doorway) summed into its emissive tint, since a point light beside or
   *  behind a card is otherwise lost. */
  private lightCharacter(cut: Cutout, at: THREE.Vector3, tod: number, f: number) {
    const tint = this.hemi.color.clone().lerp(C(1, 0.95, 0.9), 0.3).multiplyScalar(num([0.1, 0.1, 0.14, 0.18], tod));
    if (this.opts.post === "v2") {
      // a card is lit, not pasted, but never dim: the reference's heads sit at V 0.86-1.0 in every light, tinted by
      // the light colour (day #f8f1ef, sunset #fddeb6). The emissive floor carries most of that; the Lambert term adds
      // the sun side on top.
      const g = goldAmount(tod);
      const day = new THREE.Color(0.97, 0.94, 0.93), gold = new THREE.Color(0.99, 0.87, 0.71);
      tint.copy(day.lerp(gold, g)).multiplyScalar(0.72);
    }
    const chest = at.clone().setY(at.y + 1.0);
    let practical = 0;
    for (const l of this.world.lamps) {
      if (l.light.intensity <= 0.001) continue;
      l.light.getWorldPosition(this.tmpV);
      const d2 = this.tmpV.distanceToSquared(chest);
      const k = Math.min(0.55, (l.light.intensity * 0.05) / (1 + d2 / 6));
      tint.add(l.light.color.clone().multiplyScalar(k));
      practical = Math.max(practical, k);
    }
    cut.setTint(tint, 1);
    // lit from the sun's side, tilted up so the hemisphere term reads as sky
    const n = this.key.position.clone().normalize().multiplyScalar(0.8).add(new THREE.Vector3(0, 0.6, 0));
    cut.setLitNormal(n);
    cut.setContact(0.55 - 0.25 * practical);
    void f;
  }

  /** the beat governing frame f: the containing one, else the last one started */
  private beatAt(f: number): BeatSpec {
    let found = this.sheet[0];
    for (const b of this.sheet) {
      if (f >= b.start) found = b;
      if (f >= b.start && f <= b.end) return b;
    }
    return found;
  }

  update(f: number) {
    const clock = lerp(this.spec.tod[0], this.spec.tod[1], clamp01(f / Math.max(1, this.durationFrames - 1)));
    // a beat may fix its own time of day (snapped at its start: beats are cuts); else the world's clock
    const tod = this.beatAt(f).tod ?? clock;
    const time = f / FPS;

    // ---- sky ----
    const look = this.spec.look ?? {};
    const sk = skyAt(tod, look);
    const u = this.sky.uniforms;
    // (v2 once pre-inverted the tone map here with untone(); measured, it over-darkened and rotated the sky toward
    // violet, so the sky stops in look.ts are authored against the chain's real output instead)
    u.zenith.value.copy(sk.zenith);
    u.horizon.value.copy(sk.horizon);
    u.ground.value.copy(sk.ground);
    u.cloudColor.value.copy(sk.cloud);
    u.cloudShade.value.copy(sk.cloudShade);
    u.cloudAmount.value = sk.cloudAmount;
    skyStops(tod, look).forEach((c, i) => (u.stopCol.value as THREE.Color[])[i].copy(c));
    u.sunGlow.value = sk.sunGlow;
    u.sunDir.value.set(-1, sk.sunElevation, 0.25).normalize(); // (v2 moves the disc to the key's direction below)
    u.sunColor.value.copy(sk.sun);
    u.stars.value = sk.stars;
    u.aurora.value = 0;
    u.time.value = time;
    // aerial perspective: the far land goes toward the sky at the horizon
    this.fog.color.copy(u.horizon.value).lerp(u.zenith.value, 0.2);
    if (this.cyc) this.cyc.setTod(this.fog.color, tod);

    // ---- lights ----
    const lt = lightsAt(tod, look);
    this.key.color.copy(lt.keyColor);
    this.key.intensity = lt.keyIntensity;
    this.key.position.set(lt.keyDir.r, lt.keyDir.g, lt.keyDir.b);
    this.hemi.color.copy(lt.hemiSky);
    this.hemi.groundColor.copy(lt.hemiGround);
    this.hemi.intensity = lt.hemiIntensity;
    // windows, lamps and the fire come up as the light goes
    const dark = clamp01((tod - 0.45) / 0.35);
    for (const g of this.world.glows) g.mat.emissive.copy(g.color).multiplyScalar(dark * g.peak);
    for (const l of this.world.lamps) {
      const flick = l.flicker ? 0.75 + 0.25 * hash(Math.floor(f / 2), 5) : 1;
      l.light.intensity = dark * l.peak * flick;
    }

    // ---- camera ----
    const cs = cameraStateAt(this.beats, f, motionOf(this.opts));
    {
      // a `follow` shot rides with its prop: camera and target shift by the prop's travel since the beat began
      const beatNow = this.beatAt(f);
      const sh = followShift(this.L, this.sheet, beatNow, f);
      if (sh.lengthSq() > 0) {
        cs.pose = { ...cs.pose, pos: [cs.pose.pos[0] + sh.x, cs.pose.pos[1], cs.pose.pos[2] + sh.z], target: [cs.pose.target[0] + sh.x, cs.pose.target[1], cs.pose.target[2] + sh.z] };
      }
      // fog per beat (range and colour), blended over the beat's first `blend` frames from the previous beat's
      const idx = this.sheet.indexOf(beatNow);
      const aerial = this.fog.color.clone();
      const fogOf = (b: BeatSpec | undefined) =>
        b?.fog ? { near: b.fog.near, far: b.fog.far, color: b.fog.color ? S(parseInt(b.fog.color.replace("#", ""), 16)) : aerial } : { near: this.spec.fog.near * 1.3, far: this.spec.fog.far * 1.3, color: aerial };
      const cur = fogOf(beatNow), prev = fogOf(this.sheet[idx - 1]);
      const k = clamp01((f - beatNow.start) / Math.max(1, beatNow.fog?.blend ?? 12));
      this.fog.near = lerp(prev.near, cur.near, k);
      this.fog.far = lerp(prev.far, cur.far, k);
      this.fog.color.copy(prev.color).lerp(cur.color, k);
      // a beat's own fog fades the ink with the geometry (a fogged boat must not read as a black wireframe)
      const dense = beatNow.fog ? 1 : 0;
      this.inkFog = { start: lerp(60, this.fog.near, dense), amount: lerp(0.3, 0.85, dense) };
      // a story fog (far under ~120 m) also greys the sky, most at the horizon; aerial haze leaves the sky alone
      (u.fogCol.value as THREE.Color).copy(this.fog.color);
      u.skyFog.value = clamp01((120 - this.fog.far) / 100) * 0.9;
    }
    applyCameraState(this.camera, cs);
    const pose = cs.pose;
    // the fill rides with the camera: from above-left of the lens, aimed at the subject
    {
      const cam = this.camera;
      const fwd = new THREE.Vector3(0, 0, -1).applyQuaternion(cam.quaternion);
      const up = new THREE.Vector3(0, 1, 0);
      const left = new THREE.Vector3(-1, 0, 0).applyQuaternion(cam.quaternion);
      this.fill.position.copy(cam.position).addScaledVector(up, 6).addScaledVector(left, 4).addScaledVector(fwd, -4);
      this.fill.target.position.copy(cam.position).addScaledVector(fwd, pose.focus);
      this.fill.color.copy(lt.hemiSky).lerp(C(1, 1, 1), 0.6);
      this.fill.intensity = num([0.7, 0.9, 0.9, 0.7], tod);
    }
    // atmosphere needs the posed camera (it fades motes near the lens)
    this.atmos.update(f, tod, this.camera);
    updateWater(this.camera, time, goldAmount(tod));
    this.sway(f);
    this.world.detail?.update(this.fog.color, tod);
    this.sky.sky.position.copy(this.camera.position);

    // ---- cast ----
    const beat = this.beatAt(f);

    // ---- named props: moved, shown, hidden and acted by the beats' cues; code parts animate every frame ----
    for (const np of this.world.props) {
      const pose = propPoseAt(this.L, this.sheet, np.placed, f);
      np.group.visible = pose.visible;
      np.group.position.copy(pose.pos);
      np.group.rotation.y = pose.yaw;
      // its smoke emitters travel with it (a sailing boat no longer leaves its plume behind); hidden = no smoke
      if (np.smoke.length) {
        np.group.updateMatrixWorld(true);
        for (const sm of np.smoke) {
          if (pose.visible) sm.at.copy(sm.local).applyMatrix4(np.group.matrixWorld);
          else sm.at.set(0, -500, 0);
        }
      }
      const code = CODE_PARTS[np.placed.what as string];
      if (code?.animate && pose.visible) code.animate(np.group, { f, t: time, beatT: pose.beatT, act: pose.act });
    }
    // code parts placed without a name still get their idle animation
    this.world.root.traverse((o) => {
      const kind = o.userData.codePart as string | undefined;
      if (!kind || this.world.props.some((np) => np.group === o)) return;
      CODE_PARTS[kind]?.animate?.(o as THREE.Group, { f, t: time, beatT: 0, act: {} });
    });

    // a cast member's gesture, the one before it, the blend and the head turn at frame f: the beat's own, or a cue's
    // (worldKit gestureAt). Gestures land LEAD frames early and blend in over ~10 frames.
    const cueAt = (role: BeatSpec["cast"][number], beatStart: number) => {
      const c = gestureAt(role, f, LEAD);
      const cued = Number.isFinite(c.since);
      const blend = clamp01((f + LEAD - (cued ? c.since : beatStart)) / 10);
      return { gesture: c.gesture, from: cued ? c.from : undefined, cued, blend, look: c.headFrom + (c.headTurn - c.headFrom) * smoother(blend) };
    };

    // grammar figures: same marks, walks and gestures as the fixed two, drawn by kit/Figure.ts
    for (const [name, fig] of this.figures) {
      const role = beat.cast.find((c) => c.who === name);
      if (!role) {
        fig.mesh.visible = false;
        continue;
      }
      fig.mesh.visible = true;
      const { at, walking } = castPosition(this.L, beat, role, f);
      const cue = cueAt(role, beat.start);
      const dflt: FigureGesture = role.action === "point" ? "point" : role.action === "react" ? "lookUp" : "none";
      const g = (cue.gesture as FigureGesture | undefined) ?? dflt;
      fig.redraw({
        phase: f / WALK_CYCLE_FRAMES, walk: walking ? 1 : 0, lid: lidAt(time, 7 + name.length, []), look: cue.look,
        gesture: g, gestureFrom: (cue.from as FigureGesture | undefined) ?? (cue.cued ? dflt : "none"), gestureBlend: cue.blend, beat: f / FPS, talk: g === "talk" ? 0.6 + 0.4 * Math.sin(f * 0.9) : 0,
        headTilt: role.action === "react" ? -5 * clamp01((f - beat.start) / 30) : 0,
      });
      fig.mesh.position.set(at.x, at.y + (walking ? 0 : Math.sin(time * 2.2) * 0.006), at.z);
      fig.cut.face(this.camera, 0.8);
      this.lightCharacter(fig.cut, at, tod, f);
    }

    for (const who of ["operator", "newsboy"] as const) {
      const role = beat.cast.find((c) => c.who === who);
      const cut = who === "operator" ? this.op : this.boy;
      if (!role) {
        cut.mesh.visible = false;
        continue;
      }
      cut.mesh.visible = true;
      const { at, walking, speed } = castPosition(this.L, beat, role, f);
      // stride follows real ground speed, so the stance foot keeps pace
      const stepM = speed / STEPS_PER_S;
      const beatSecs = f / FPS;

      if (who === "newsboy") {
        // the drawn stance foot only matches the ground when the walk crosses
        // the frame; toward/away from the lens there is little to match
        let footScale = 0.55;
        if (walking && role.to) {
          const dir = this.L.markAt(role.to).sub(this.L.markAt(role.mark)).setY(0).normalize();
          const right = new THREE.Vector3(1, 0, 0).applyQuaternion(this.camera.quaternion).setY(0).normalize();
          footScale = 0.55 + 0.45 * Math.abs(dir.dot(right));
        }
        const cue = cueAt(role, beat.start);
        const dflt: BoyGesture = role.action === "react" ? "lookUp" : "none";
        const g = (cue.gesture as BoyGesture | undefined) ?? dflt;
        this.boy.redraw(
          drawNewsboy({
            phase: f / WALK_CYCLE_FRAMES,
            walk: walking ? 1 : 0,
            stride: Math.min(MAX_STRIDE, stepM * STRIDE_PER_M),
            footScale,
            expr: role.action === "react" || role.action === "point" || g === "cheer" || g === "shout" ? "awe" : "smile",
            lid: lidAt(time, 11, []),
            point: role.action === "point" ? clamp01((f - beat.start - 10) / 22) : 0,
            headTilt: role.action === "react" ? -7 * clamp01((f - beat.start) / 30) : 0,
            gesture: g,
            gestureFrom: (cue.from as BoyGesture | undefined) ?? (cue.cued ? dflt : "none"),
            gestureBlend: cue.blend,
            beat: beatSecs,
            headTurn: cue.look,
          }),
        );
        this.boy.mesh.position.set(at.x, at.y + (walking ? 0 : Math.sin(time * 2) * 0.006), at.z);
        this.boy.face(this.camera, 0.8);
        this.lightCharacter(this.boy, at, tod, f);
      } else {
        const cue = cueAt(role, beat.start);
        const dflt: OpGesture = role.action === "point" ? "point" : "idle";
        const g = (cue.gesture as OpGesture | undefined) ?? dflt;
        const ff = f + LEAD;
        this.op.redraw(
          drawOperator({
            pose: "hold",
            poseTo: "hold",
            blend: 1,
            expr: role.action === "react" ? "grin" : "focus",
            lid: lidAt(time, 3, []),
            tap: 1,
            headTilt: 3 * Math.sin((2 * Math.PI * ff) / 140),
            stance: "stand",
            gesture: g,
            gestureFrom: (cue.from as OpGesture | undefined) ?? (cue.cued ? dflt : "idle"),
            gestureBlend: cue.blend,
            pointAngle: role.pointAngle ?? 30,
            beat: g === "talk" ? f / 24 : beatSecs,
            headTurn: cue.look,
            talk: g === "talk" ? 0.6 + 0.4 * Math.sin(f * 0.9) : 0,
          }),
        );
        this.op.mesh.position.set(at.x, at.y + Math.sin(time * 2.4) * 0.007, at.z);
        this.op.face(this.camera, 0.8);
        this.lightCharacter(this.op, at, tod, f);
      }
    }

    // ---- v2 post: two-tone light preset blended day -> golden by time of day, focus and blur per shot ----
    if (this.opts.post === "v2") {
      const g = goldAmount(tod);
      // the sun is CAMERA-RELATIVE and frozen per beat (the skill's lights.ts convention: az = degrees from the
      // shot camera's forward axis, 0 = straight ahead = backlight, +90 = screen right; el = elevation), so every
      // shot's subject is lit from the preset's side instead of whichever side the world-fixed sun happens to be.
      {
        const D = LIGHTS.day, G = LIGHTS.golden;
        // day az 75 (the skill's) puts the sun slightly in FRONT of the camera, so any face turned to the lens is
        // backlit and drops to shade; our subjects face the lens, so the day sun sits over the camera's right
        // shoulder (110): camera-facing, right-facing and top faces lit, left faces and undersides in shade.
        // golden: the reference is backlit in 10 of 15 sunset frames (az 0-40, el 3-15): the low sun sits ahead
        // and right of the lens, the disc shows low in the sky, lit faces go peach and camera-facing masses go to
        // the violet shade with warm rims; the sun rake from behind the shoulder (135) gave no disc and no violet.
        const DAY_AZ = 110, GOLDEN_AZ = this.opts.tune?.goldenAz ?? 45;
        const az = (lerp(DAY_AZ, GOLDEN_AZ, g) * Math.PI) / 180, el = (lerp(D.el, G.el, g) * Math.PI) / 180;
        const start = cameraStateAt(this.beats, beat.start, motionOf(this.opts)).pose;
        const fwd = new THREE.Vector3(start.target[0] - start.pos[0], 0, start.target[2] - start.pos[2]).normalize();
        const right = new THREE.Vector3(-fwd.z, 0, fwd.x);
        const from = fwd.clone().multiplyScalar(Math.cos(az)).addScaledVector(right, Math.sin(az)).multiplyScalar(Math.cos(el));
        from.y = Math.sin(el);
        // the light rides with the subject so the 68 m shadow box covers the shot, not the world origin
        this.key.target.position.set(pose.target[0], 0, pose.target[2]);
        this.key.position.copy(this.key.target.position).addScaledVector(from, 80);
        // the sky's sun disc hangs low AHEAD of the lens at golden hour (az 12: inside the 9:16 frame's ~22 deg field),
        // while the key itself sits 45 deg off so walls get a warm band; by day the disc follows the key (out of frame)
        {
          const daz = (lerp(DAY_AZ, 12, g) * Math.PI) / 180, del = (lerp(D.el, 7, g) * Math.PI) / 180;
          const disc = fwd.clone().multiplyScalar(Math.cos(daz)).addScaledVector(right, Math.sin(daz)).multiplyScalar(Math.cos(del));
          disc.y = Math.sin(del);
          (this.sky.uniforms.sunDir.value as THREE.Vector3).copy(disc);
        }
        // (bias stays ours: the skill's values belong to its 4096 map and its frustum, and gave acne everywhere here)
      }
      const mix3 = (a: readonly number[], b: readonly number[], t: number) =>
        (TONE_V.set(lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)));
      const D = LIGHTS.day, G = LIGHTS.golden;
      // shade: the reference's day shade is ~0.35-0.5 of lit in the surface's own hue (the skill's 0.3 blue-grey went
      // violet on white walls); its sunset shade keeps a violet cast but not the skill's near-black, which turned
      // every shaded mass in a frame-filling subject into "an almost black teal mass" (verifier, every round)
      // (round 3 measured white cabins at shade/lit 0.68 against the target 0.45-0.55 with 0.55 here; and the golden
      // shade must put MORE blue in shade than in lit (B ratio >= 1.3, the violet replacement), which 0.48 never did)
      const DAY_SHADE = [0.44, 0.42, 0.45] as const, DAY_LIFT = [0.04, 0.04, 0.07] as const;
      // (round 4 measured golden frames at Y' p50 0.30-0.38 against 0.516 with [0.2,0.19,0.4]: a frame-filling boat in
      // the backlight was one flat violet mass; the lifted shade keeps the violet, the key 45 deg off the axis puts a
      // warm band on the walls that face half toward it)
      const GOLD_SHADE = this.opts.tune?.goldShade ?? ([0.3, 0.28, 0.52] as const), GOLD_LIFT = this.opts.tune?.goldLift ?? ([0.08, 0.1, 0.26] as const);
      // golden lit x1.35: measured golden frames sat at Y' p50 0.30-0.35 against 0.516 with the skill's lit values
      // the world's look knobs act on the v2 chain too: warmth tints the lit colour, saturation scales the albedo
      // saturation around the chain's own 1.2 default
      const wv = look.warmth ?? 0, warmLit = (c: readonly number[]) => [c[0] * (1 + 0.1 * wv), c[1] * (1 + 0.02 * wv), c[2] * (1 - 0.12 * wv)] as const;
      const DAY_LIT = warmLit(D.lit);
      const GOLD_LIT = warmLit([G.lit[0] * 1.35, G.lit[1] * 1.35, G.lit[2] * 1.35]);
      (TONE.uLitCol.value as THREE.Vector3).copy(mix3(DAY_LIT, GOLD_LIT, g));
      (TONE.uShadeCol.value as THREE.Vector3).copy(mix3(DAY_SHADE, GOLD_SHADE, g));
      (TONE.uShadeLift.value as THREE.Vector3).copy(mix3(DAY_LIFT, GOLD_LIFT, g));
      TONE.uLambert.value = lerp(D.lambert, G.lambert, g);
      TONE.uSideK.value = lerp(D.sideK, G.sideK, g);
      TONE.uTerm.value = lerp(D.term, G.term, g);
      (TONE.uBounce.value as THREE.Vector3).copy(mix3(LOOK.day.bounce, LOOK.golden.bounce, g));
      TONE.uSat.value = lerp(LOOK.day.sat, LOOK.golden.sat, g) * ((look.saturation ?? 1.2) / 1.2);
      if (this.opts.debugTone) {
        (TONE.uLitCol.value as THREE.Vector3).set(0, 2, 0);
        (TONE.uShadeCol.value as THREE.Vector3).set(2, 0, 0);
        (TONE.uShadeLift.value as THREE.Vector3).set(0, 0, 0);
        TONE.uLambert.value = 0;
        TONE.uSat.value = 0;
      }
      // the skill's table: close-ups 12-14 px, medium shots 10-12, wides and aerials 0 (focus > 15 m)
      const shotDof = this.spec.shots.find((sh) => sh.name === beat.shot)?.dof;
      const cInf = shotDof ?? (pose.focus <= 3 ? 10 : lerp(8, 0, clamp01((pose.focus - 3) / 12)));
      this.post = { focus: pose.focus, cInf, golden: g, inkFog: this.inkFog };
    }

    // ---- grade + dof ----
    this.grade = gradeAt(tod, look);
    // DOF is a hint of depth, not a smear: the reference keeps its backgrounds
    // readable. Strongest in close-ups, mild on wide shots.
    const near = clamp01((pose.focus - 2) / 9);
    this.dof = { focus: pose.focus, strength: lerp(7, 2.5, near), maxRadius: 6 };
  }
}
