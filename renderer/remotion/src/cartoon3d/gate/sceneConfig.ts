// The Cartoon 3D scene of a scene-config (TMDEV-185): one generated scene spanning the video whose props carry
// `cartoon3d: { beats: [...] }`, the shots as beats for the beat gate. Keep the shape in sync with mcp/cartoon.py.
export type BeatRow = { start: number; end: number; shot: string };
export type CartoonScene = { src: string; beats: BeatRow[] };

export const cartoonScene = (config: unknown): CartoonScene => {
  const scenes = (config as { scenes?: unknown[] })?.scenes;
  if (!Array.isArray(scenes)) throw new Error("scene-config has no scenes");
  for (const sc of scenes) {
    const s = sc as { src?: string; props?: { cartoon3d?: { beats?: BeatRow[] } } };
    const beats = s?.props?.cartoon3d?.beats;
    if (Array.isArray(beats) && typeof s.src === "string") return { src: s.src, beats };
  }
  throw new Error("scene-config has no Cartoon 3D scene (a scene with props.cartoon3d.beats)");
};
