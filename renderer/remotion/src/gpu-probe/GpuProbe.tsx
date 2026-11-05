import React, { useMemo } from "react";
import { AbsoluteFill, Composition } from "remotion";

// The worker (renderer/api/worker.py::_run_gpu_probe) renders this as a still
// with exactly the GL flags a real render would get, and reads the tagged line
// from Remotion's output. console.error, not console.log: the CLI forwards a
// page's errors and warnings at its default log level, but not its logs.
//
// The renderer string is the only trustworthy answer. A render that "worked"
// proves nothing: without the right EGL vendor, Chromium silently renders on
// another GL device (an integrated GPU, or software), and that still succeeds.
export const PROBE_TAG = "TUBEMATIC_GPU_PROBE";

type ProbeResult = { webgl: boolean; renderer?: string; vendor?: string; error?: string };

const readWebGl = (): ProbeResult => {
  const canvas = document.createElement("canvas");
  const gl = (canvas.getContext("webgl2") ?? canvas.getContext("webgl")) as WebGLRenderingContext | null;
  if (!gl) return { webgl: false, error: "Chromium could not create a WebGL context" };
  const info = gl.getExtension("WEBGL_debug_renderer_info");
  return {
    webgl: true,
    renderer: String(gl.getParameter(info ? info.UNMASKED_RENDERER_WEBGL : gl.RENDERER)),
    vendor: String(gl.getParameter(info ? info.UNMASKED_VENDOR_WEBGL : gl.VENDOR)),
  };
};

const GpuProbe: React.FC = () => {
  const result = useMemo(() => {
    let r: ProbeResult;
    try {
      r = readWebGl();
    } catch (e) {
      r = { webgl: false, error: String(e) };
    }
    console.error(`${PROBE_TAG} ${JSON.stringify(r)}`);
    return r;
  }, []);
  return (
    <AbsoluteFill style={{ background: "#000", color: "#fff", fontSize: 28, padding: 24 }}>
      {JSON.stringify(result)}
    </AbsoluteFill>
  );
};

export const GpuProbeRoot: React.FC = () => (
  <Composition id="GpuProbe" component={GpuProbe} durationInFrames={1} fps={30} width={640} height={360} />
);
