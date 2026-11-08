// PROBE 2 — renders one WorldSpec + beat sheet. Shared by the probe's own
// compositions and by scenes/installed/Cartoon3D.tsx, through which the
// REAL pipeline's CompositionBuilder renders a 3D world as one scene entry.
import { useFrame, useThree } from "@react-three/fiber";
import { ThreeCanvas } from "@remotion/three";
import { useEffect, useRef, useState } from "react";
import { AbsoluteFill, continueRender, delayRender, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import * as THREE from "three";
import { FxFlags, InkPipeline } from "../kit/InkPipeline";
import { PostStack } from "../kit/post/PostStack";
import { WorldScene } from "./WorldScene";
import type { SceneOpts } from "./sceneOpts";
import type { BeatSpec, WorldSpec } from "./worldKit";

const Runner: React.FC<{ frame: number; flags: FxFlags; spec: WorldSpec; beats: BeatSpec[]; tex: THREE.Texture | null; opts: SceneOpts }> = ({
  frame, flags, spec, beats, tex, opts,
}) => {
  const { gl } = useThree();
  const frameRef = useRef(frame);
  frameRef.current = frame;
  const state = useRef<{ world: WorldScene; pipe: InkPipeline | null; post: PostStack | null } | null>(null);
  // priority 1 takes over rendering; everything is a function of the Remotion
  // frame. Built lazily once ThreeCanvas has sized the drawing buffer.
  useFrame(() => {
    if (!state.current) {
      const world = new WorldScene(spec, beats, flags.shadows, tex ?? undefined, opts);
      if (opts.post === "v2") {
        // ink: the reference recipe (LOOK-TARGETS 5): creases 0.64 x silhouette, concave joins faint (wall into
        // deck, cabin into floor read as seams, not outlines), creases from 40 deg so rail lips carry one line
        const post = new PostStack(gl, world.scene, world.camera, { creaseScale: 0.64, concaveGain: 0.3, angleLo: 40, angleHi: 58 }, opts.debugPost ?? {});
        post.ink.debug = opts.debugInk ?? 0;
        world.setResolution(post.height);
        state.current = { world, pipe: null, post };
      } else {
        const pipe = new InkPipeline(gl, flags, 0);
        world.setResolution(pipe.height);
        state.current = { world, pipe, post: null };
      }
    }
    const { world, pipe, post } = state.current;
    world.update(frameRef.current);
    if (post) {
      // same re-assertion the v1 pipeline makes: R3F's configure() resets shadowMap.enabled on re-render
      gl.shadowMap.enabled = flags.shadows;
      gl.shadowMap.type = THREE.PCFShadowMap;
      gl.shadowMap.autoUpdate = false;
      gl.shadowMap.needsUpdate = flags.shadows;
      post.render(gl, world.scene, world.post);
    } else if (pipe) {
      pipe.render(gl, world.scene, world.camera, world.grade, world.dof);
    }
  }, 1);
  return null;
};

export interface WorldViewProps {
  spec: WorldSpec;
  beats: BeatSpec[];
  opts?: SceneOpts;
  shadows?: boolean;
  noBackdrop?: boolean;
}

export const WorldView: React.FC<WorldViewProps> = ({ spec, beats, opts = {}, shadows = true, noBackdrop = false }) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const flags: FxFlags = { shadows: shadows && opts.shadows !== false, ink: true, grade: true, dof: true };
  const dpr = typeof window !== "undefined" ? window.devicePixelRatio : 1;
  const useBackdrop = !noBackdrop && !!spec.backdrop;
  const [tex, setTex] = useState<THREE.Texture | null>(null);
  const [handle] = useState(() => delayRender(`loading backdrop for ${spec.name}`));
  useEffect(() => {
    if (!useBackdrop || !spec.backdrop) {
      continueRender(handle);
      return;
    }
    // a generated image arrives as the served URL (/public/<video_id>/images/<file>, the generate_image
    // tool's public_path) and is used as-is; a bare name is a file under the project's public/
    const file = spec.backdrop.file;
    new THREE.TextureLoader().load(
      file.startsWith("/public/") ? file : staticFile(file),
      (t) => {
        setTex(t);
        continueRender(handle);
      },
      undefined,
      () => continueRender(handle),
    );
  }, [handle, spec.backdrop, useBackdrop]);

  return (
    <AbsoluteFill style={{ backgroundColor: "#1a1440" }}>
      {tex || !useBackdrop ? (
        <ThreeCanvas
          width={width}
          height={height}
          dpr={dpr}
          flat
          linear
          shadows={{ enabled: flags.shadows, type: THREE.PCFShadowMap }}
          gl={{ antialias: false, alpha: false, powerPreference: "high-performance" }}
        >
          <Runner frame={frame} flags={flags} spec={spec} beats={beats} tex={tex} opts={opts} />
        </ThreeCanvas>
      ) : null}
    </AbsoluteFill>
  );
};
