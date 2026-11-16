// The Low-Poly Skit runner (TMDEV-250): one three.js scene holding every set of the video, one shown per shot, drawn with
// a plain light rig and no ink, shadow, lens, bloom or grade pass (the look is flat colour and facets, and this keeps
// the CPU cost low). Hard cuts only. A generated scene renders <LowPolyShort video={...} frame={f} /> inside Tubematic's
// CompositionBuilder, which puts the captions and the voice on top. Frames flagged by `blurAt` are drawn as an average
// of a few sub-frames, so a whip or an impact smears like a real exposure.
import React, { useMemo, useRef } from "react";
import * as THREE from "three";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { ThreeCanvas } from "@remotion/three";
import { useFrame, useThree } from "@react-three/fiber";
import { DEFAULT_LIGHT, shotOf, type LowPolyDef, type LowPolyLight } from "./def";
import type { Cam } from "../camera";

const SUBFRAMES = 4;

const setCamera = (camera: THREE.PerspectiveCamera, c: Cam) => {
  camera.position.set(...c.pos);
  camera.fov = c.fov;
  camera.up.set(0, 1, 0);
  camera.lookAt(...c.look);
  if (c.roll) camera.rotateZ(c.roll);
  camera.updateProjectionMatrix();
};

type Rig = { sets: Record<string, import("../kit/set").SetPiece>; ambient: THREE.AmbientLight; key: THREE.DirectionalLight; fill: THREE.DirectionalLight; rt: THREE.WebGLRenderTarget; quad: THREE.Mesh; quadScene: THREE.Scene; quadCam: THREE.OrthographicCamera };

const Inner: React.FC<{ video: LowPolyDef; frame: number }> = ({ video, frame }) => {
  const { gl, scene, camera } = useThree();
  const rig = useRef<Rig | null>(null);
  useFrame(() => {
    const cam = camera as THREE.PerspectiveCamera;
    if (!rig.current) {
      const sets = video.sets();
      for (const s of Object.values(sets)) scene.add(s.root);
      const ambient = new THREE.AmbientLight("#ffffff", 1), key = new THREE.DirectionalLight("#ffffff", 1), fill = new THREE.DirectionalLight("#ffffff", 0.3);
      scene.add(ambient, key, key.target, fill);
      gl.outputColorSpace = THREE.SRGBColorSpace;
      gl.toneMapping = THREE.NoToneMapping;
      gl.shadowMap.enabled = false;
      const size = gl.getDrawingBufferSize(new THREE.Vector2());
      const rt = new THREE.WebGLRenderTarget(size.x, size.y, { depthBuffer: true });
      const quadScene = new THREE.Scene(), quadCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
      const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), new THREE.MeshBasicMaterial({ map: rt.texture, transparent: true, depthTest: false, depthWrite: false }));
      quadScene.add(quad);
      rig.current = { sets, ambient, key, fill, rt, quad, quadScene, quadCam };
    }
    const { sets, ambient, key, fill, rt, quad, quadScene, quadCam } = rig.current;
    const shot = shotOf(video.shots, frame);
    for (const [name, s] of Object.entries(sets)) s.root.visible = name === shot.set;
    const L: LowPolyLight = { ...DEFAULT_LIGHT, ...(video.light?.(shot) ?? {}) };
    ambient.color.set("#ffffff"); ambient.intensity = L.ambient;
    key.color.set(L.keyColor); key.intensity = L.key;
    fill.color.set(L.fillColor); fill.intensity = L.fill;
    const bg = new THREE.Color(video.background(shot.set));
    scene.background = bg;
    const blur = video.blurAt?.(shot.id, frame) ?? 0;
    const draw = (f: number) => {
      const c = video.camAt(shot.id, f);
      setCamera(cam, c);
      const o = sets[shot.set].root.position;
      key.position.set(o.x + L.keyFrom[0], o.y + L.keyFrom[1], o.z + L.keyFrom[2]);
      key.target.position.copy(o);
      fill.position.set(o.x - L.keyFrom[0], o.y + 1, o.z + L.keyFrom[2] * 0.5);
      sets[shot.set].pose(shot.id, f, cam);
      cam.updateMatrixWorld();
    };
    if (blur < 0.05) {
      draw(frame);
      gl.setRenderTarget(null);
      gl.render(scene, cam);
      return;
    }
    // average a few sub-frames spread across the frame: a stronger blur spreads wider (up to a full frame either side)
    gl.setRenderTarget(null);
    gl.autoClear = false;
    gl.setClearColor(0x000000, 1);   // the sub-frames add up to the average, so start from black
    gl.clear(true, true, true);
    (quad.material as THREE.MeshBasicMaterial).opacity = 1 / SUBFRAMES;
    (quad.material as THREE.MeshBasicMaterial).blending = THREE.AdditiveBlending;
    for (let i = 0; i < SUBFRAMES; i++) {
      draw(frame + (i / (SUBFRAMES - 1) - 0.5) * blur * 1.6);
      gl.setRenderTarget(rt);
      gl.autoClear = true;
      gl.render(scene, cam);
      gl.setRenderTarget(null);
      gl.autoClear = false;
      gl.render(quadScene, quadCam);
    }
    gl.autoClear = true;
    draw(frame);
  }, 1);
  return null;
};

/** the whole short; `frame` overrides the Remotion frame (a generated scene spanning the video passes the absolute frame) */
export const LowPolyShort: React.FC<{ video: LowPolyDef; frame?: number }> = ({ video, frame }) => {
  const cur = useCurrentFrame();
  const f = frame ?? cur;
  const bg = useMemo(() => video.background(video.shots[0].set), [video]);
  return (
    <AbsoluteFill style={{ background: bg }}>
      <ThreeCanvas width={1080} height={1920} camera={{ fov: 40, near: 0.05, far: 400 }} gl={{ antialias: true, stencil: false, preserveDrawingBuffer: true }}>
        <Inner video={video} frame={f} />
      </ThreeCanvas>
    </AbsoluteFill>
  );
};
