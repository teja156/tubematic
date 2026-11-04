// Inked3D visual-style spike: flat 2D characters in a lit, inked 3D world.
// Test piece: the 1859 Carrington Event, silent, 27 s.
import { useThree, useFrame } from "@react-three/fiber";
import { ThreeCanvas } from "@remotion/three";
import { useEffect, useRef, useState } from "react";
import { AbsoluteFill, continueRender, delayRender, useCurrentFrame, useVideoConfig } from "remotion";
import * as THREE from "three";
import { CarringtonScene } from "./carrington/scene";
import { DebugView, FxFlags, InkPipeline } from "./kit/InkPipeline";

export interface Inked3DProps {
  shadows?: boolean;
  ink?: boolean;
  grade?: boolean;
  dof?: boolean;
  debugView?: DebugView;
  showGlInfo?: boolean; // overlay the WebGL renderer string (proof of backend)
  [key: string]: unknown;
}

// Which WebGL backend actually ran (SwiftShader under --gl=swangle).
const rendererString = (gl: THREE.WebGLRenderer) => {
  const ctx = gl.getContext();
  const ext = ctx.getExtension("WEBGL_debug_renderer_info");
  const r = ext ? ctx.getParameter(ext.UNMASKED_RENDERER_WEBGL) : ctx.getParameter(ctx.RENDERER);
  const v = ext ? ctx.getParameter(ext.UNMASKED_VENDOR_WEBGL) : ctx.getParameter(ctx.VENDOR);
  return `WEBGL_RENDERER=${r} | VENDOR=${v} | ${ctx.getParameter(ctx.VERSION)}`;
};

const Runner: React.FC<{ frame: number; flags: FxFlags; debugView: DebugView }> = ({ frame, flags, debugView }) => {
  const { gl } = useThree();
  const frameRef = useRef(frame);
  frameRef.current = frame;
  const state = useRef<{ world: CarringtonScene; pipe: InkPipeline } | null>(null);
  // priority 1 takes over rendering; everything is a function of the Remotion frame.
  // Built lazily on the first frame, once ThreeCanvas has sized the drawing buffer.
  useFrame(() => {
    if (!state.current) {
      const pipe = new InkPipeline(gl, flags, debugView);
      const world = new CarringtonScene(flags.shadows);
      world.setResolution(pipe.height);
      state.current = { world, pipe };
    }
    const { world, pipe } = state.current;
    world.update(frameRef.current);
    pipe.render(gl, world.scene, world.camera, world.grade, world.dof);
  }, 1);
  return null;
};

export const Inked3DSpike: React.FC<Inked3DProps> = (props) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const flags: FxFlags = {
    shadows: props.shadows ?? true,
    ink: props.ink ?? true,
    grade: props.grade ?? true,
    dof: props.dof ?? true,
  };
  const dpr = typeof window !== "undefined" ? window.devicePixelRatio : 1;
  const [glInfo, setGlInfo] = useState("");
  const [handle] = useState(() => (props.showGlInfo ? delayRender("reading WebGL renderer string") : null));
  useEffect(() => {
    if (glInfo && handle !== null) continueRender(handle);
  }, [glInfo, handle]);
  return (
    <AbsoluteFill style={{ backgroundColor: "#1a1440" }}>
      <ThreeCanvas
        width={width}
        height={height}
        dpr={dpr}
        flat
        linear
        gl={{ antialias: false, alpha: false, powerPreference: "high-performance" }}
        onCreated={(st) => {
          if (props.showGlInfo) setGlInfo(`${rendererString(st.gl)} | buffer ${st.gl.domElement.width}x${st.gl.domElement.height}`);
        }}
      >
        <Runner frame={frame} flags={flags} debugView={props.debugView ?? 0} />
      </ThreeCanvas>
      {props.showGlInfo ? (
        <div style={{ position: "absolute", left: 30, right: 30, top: 60, padding: 20, fontSize: 30, fontFamily: "monospace", color: "#fff", background: "rgba(20,10,50,0.85)", wordBreak: "break-all" }}>
          {glInfo}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
