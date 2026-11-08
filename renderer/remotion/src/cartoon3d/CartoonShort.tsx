// Adapted from mromidev/claude-animated-shorts (templates/bridge/Bridge.tsx), MIT License, Copyright (c) 2026 Mr omi.
// The Cartoon 3D runner (TMDEV-185): one three.js world (kit/world.ts) built from a VideoDef and posed per frame from
// its shots. The agent's generated scene renders <CartoonShort video={...} frame={f} /> inside Tubematic's
// CompositionBuilder (captions + voice on top). Post chain, same order and values as the bridge:
//   RenderPass (MSAA 4) -> InkPass (world ink, own pass) -> lens blur pre + main (thin-lens DOF per shot from dofAt)
//   -> [bloom (emissive only) + NEUTRAL tone mapping + colour grade] (one merged EffectPass).
// Changed from the template: the composer is the `postprocessing` EffectComposer driven from a priority-1 useFrame
// (as kit/post/PostStack.ts does) because @react-three/postprocessing is not a dependency here; the frame number
// arrives as a prop so the scene can sit inside Tubematic's CompositionBuilder (captions + voice on top).
import React, { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { AbsoluteFill, getInputProps, useCurrentFrame } from "remotion";
import { ThreeCanvas } from "@remotion/three";
import { useFrame, useThree } from "@react-three/fiber";
import { BlendFunction, BloomEffect, EffectComposer, EffectPass, RenderPass, ToneMappingEffect, ToneMappingMode } from "postprocessing";
import { World } from "./kit/world";
import { InkPass, noInkFallback, type InkOptions } from "./post/ink";
import { LensBlur } from "./post/lensblur";
import { GradeEffect, GRADES, gradeFor } from "./post/grade";
import { layersAt } from "./camera";
import type { ShotDef, VideoDef } from "./video";

/** ink per kind of shot, as the Chicago rounds settled them: exteriors keep the look-targets recipe; an aerial fades
 *  its far lines out over the rooftops; interiors draw no lines on wall/floor joins. A video's inkFor(shot) overrides. */
export const INK_DEFAULTS = {
  exterior: { widthNear: 5.1, widthFar: 3.3, fadeNear: 150, fadeFar: 450, concaveGain: 0.05, creaseScale: 0.64, depthLo: 0.01, depthHi: 0.03 } as Partial<InkOptions>,
  aerial: { fadeNear: 90, fadeFar: 320, concaveGain: 0.05 } as Partial<InkOptions>,
  interior: { widthNear: 5.1, widthFar: 3.3, fadeNear: 150, fadeFar: 450, concaveGain: 0.0, creaseScale: 0.5, depthLo: 0.01, depthHi: 0.03 } as Partial<InkOptions>,
};
const inkOf = (def: VideoDef, sh: ShotDef): Partial<InkOptions> => {
  const base = sh.aerial ? INK_DEFAULTS.aerial : def.outdoor(sh.set) ? INK_DEFAULTS.exterior : INK_DEFAULTS.interior;
  return { ...base, ...(def.inkFor?.(sh) ?? {}) };
};

type PostToggles = { ink: boolean; lens: boolean; bloom: boolean; grade: boolean };
const toggles = (): PostToggles => ({ ink: true, lens: true, bloom: true, grade: true, ...((getInputProps() as { post?: Partial<PostToggles> }).post ?? {}) });

/** Bloom for emissive sources only. Its MIP chain always starts at 540x960 (half of 1080x1920), whatever the output
 *  size, so the glow keeps the same size relative to the frame. ADD blend: HDR-safe. */
const makeBloom = () => {
  const b = new BloomEffect({ blendFunction: BlendFunction.ADD, intensity: 0.5, luminanceThreshold: 1.0, luminanceSmoothing: 0.2, mipmapBlur: true, levels: 6, radius: 0.6 });
  const mip = b.mipmapBlurPass;
  const setSize = mip.setSize.bind(mip);
  mip.setSize = (w: number, h: number) => setSize(Math.round((1920 * w) / Math.max(h, 1)), 1920);
  return b;
};

const fwd = new THREE.Vector3(), fpt = new THREE.Vector3();
const gradeLight = (l: string): "day" | "golden" => (l === "golden" || l === "lamp" ? "golden" : "day");

type Rig = { world: World; composer: EffectComposer; ink: InkPass; lens: LensBlur; grade: GradeEffect; passes: EffectPass[] };

const Inner: React.FC<{ video: VideoDef; id: number; frame: number }> = ({ video, id, frame }) => {
  const { gl, scene, camera } = useThree();
  const frameRef = useRef(frame);
  frameRef.current = frame;
  const on = useMemo(toggles, []);
  const rig = useRef<Rig | null>(null);
  useEffect(() => () => { rig.current?.ink.dispose(); rig.current?.composer.dispose(); }, []);
  useFrame(() => {
    const cam = camera as THREE.PerspectiveCamera;
    if (!rig.current) {
      const world = new World(video);
      scene.add(world.root);
      const size = gl.getDrawingBufferSize(new THREE.Vector2());
      gl.toneMapping = THREE.NoToneMapping;
      gl.outputColorSpace = THREE.SRGBColorSpace;
      const composer = new EffectComposer(gl, { multisampling: 4, frameBufferType: THREE.HalfFloatType });
      composer.addPass(new RenderPass(scene, cam));
      // the look-targets ink recipe (LOOK-TARGETS 5, as kit/post/PostStack uses it): creases 0.64 x silhouette, concave joins faint
      const ink = new InkPass(scene, cam, { creaseScale: 0.64, concaveGain: 0.3, angleLo: 40, angleHi: 58 });
      if (on.ink) composer.addPass(ink);
      const lens = new LensBlur({ maxCoC: 24, nearScale: 1.2 });
      const passes: EffectPass[] = [];
      if (on.lens) { passes.push(new EffectPass(cam, lens.pre), new EffectPass(cam, lens.main)); for (const p of passes) composer.addPass(p); }
      const grade = new GradeEffect(GRADES.day, 1);
      const last = [on.bloom ? makeBloom() : null, new ToneMappingEffect({ mode: ToneMappingMode.NEUTRAL }), on.grade ? grade : null].filter((e): e is NonNullable<typeof e> => !!e);
      passes.push(new EffectPass(cam, ...last));
      composer.addPass(passes[passes.length - 1]);
      composer.setSize(size.x, size.y, false);
      rig.current = { world, composer, ink, lens, grade, passes };
    }
    const { world, composer, lens, grade, ink, passes } = rig.current;
    const sh = video.shots[id - 1], inkKey = `${sh.aerial ? "aerial" : sh.set}`;
    if ((ink as unknown as { _k?: string })._k !== inkKey) {
      ink.set(inkOf(video, sh));
      (ink as unknown as { _k?: string })._k = inkKey;
    }
    const f = frameRef.current;
    const target = world.update(id, f, cam, scene);
    noInkFallback(world.root);
    // an EffectPass copies the camera's near/far only when it is built: hand them over every frame, so depth-based
    // effects (the lens) linearise depth with the clip planes this shot actually uses (story.ts clipAt)
    for (const p of passes) (p.fullscreenMaterial as unknown as { uniforms: Record<string, { value: THREE.Vector2 }> }).uniforms.cameraNearFar?.value.set(cam.near, cam.far);
    // thin-lens focus: distance along the view axis to the shot's focus point (default: the camera's look target)
    const d = video.dofAt(f);
    cam.getWorldDirection(fwd);
    if (d.focus) fpt.set(...d.focus(f)); else fpt.copy(target);
    lens.focus = Math.max(0.3, fpt.sub(cam.position).dot(fwd));
    lens.cInf = d.cInf;
    gradeFor(grade, gradeLight(sh.light));
    gl.outputColorSpace = THREE.SRGBColorSpace;
    gl.toneMapping = THREE.NoToneMapping;
    gl.shadowMap.enabled = true;
    gl.shadowMap.type = THREE.PCFSoftShadowMap;
    gl.shadowMap.autoUpdate = true;
    composer.render();
  }, 1);
  return null;
};

/** test stills only: inputProps `{ post: { dpr: 0.5 } }` forces the WebGL buffer size (R3F clamps dpr to >= 1 by default) */
const dprOverride = () => (getInputProps() as { post?: { dpr?: number } }).post?.dpr;
const ShotView: React.FC<{ video: VideoDef; id: number; frame: number; alpha: number }> = ({ video, id, frame, alpha }) => (
  <AbsoluteFill style={{ opacity: alpha }}>
    <ThreeCanvas width={1080} height={1920} {...(dprOverride() ? { dpr: dprOverride() } : {})} shadows flat
      gl={{ antialias: false, stencil: false, powerPreference: "high-performance", toneMappingExposure: 1.0, preserveDrawingBuffer: true }}
      camera={{ fov: 40, near: 0.2, far: 2500 }}>
      <Inner video={video} id={id} frame={frame} />
    </ThreeCanvas>
  </AbsoluteFill>
);

/** the whole short; `frame` overrides the Remotion frame (a generated scene spanning the video passes the absolute
 *  frame, which equals the Sequence-relative one when the scene starts at frame 0) */
export const CartoonShort: React.FC<{ video: VideoDef; frame?: number }> = ({ video, frame }) => {
  const cur = useCurrentFrame();
  const f = frame ?? cur;
  const fa = video.flashAt;
  const flash = fa !== undefined && f >= fa && f < fa + 4 ? [1, 0.75, 0.45, 0.2][f - fa] : 0;
  return (
    <AbsoluteFill style={{ background: "#cfe3f2" }}>
      {layersAt(video.shots, video.xfade, f).map((l, i) => <ShotView key={i ? "over" : "base"} video={video} id={l.id} frame={f} alpha={l.alpha} />)}
      {flash > 0 && <AbsoluteFill style={{ background: "#ffffff", opacity: flash }} />}
    </AbsoluteFill>
  );
};
