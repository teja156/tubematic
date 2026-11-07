// The one place that knows how a Cartoon 3D world sits inside a scene-config:
// as a single installed scene whose props carry the world, the beats and the
// scene options. Pure (Node), shared by the QA and gate command lines.
import type { SceneOpts } from "../sceneOpts";
import type { BeatSpec, WorldSpec } from "../worldKit";

export const CARTOON_SCENE_SRC = "Cartoon3D";

export interface CartoonScene {
  world: WorldSpec;
  beats: BeatSpec[];
  opts: SceneOpts;
}

/** the Cartoon 3D scene of a scene-config object; throws when there is none */
export const cartoonScene = (config: unknown): CartoonScene => {
  const scenes = (config as { scenes?: unknown[] } | null)?.scenes;
  if (!Array.isArray(scenes)) throw new Error("scene-config has no scenes list");
  const scene = scenes.find((s) => (s as { src?: string })?.src === CARTOON_SCENE_SRC) as { props?: Partial<CartoonScene> } | undefined;
  if (!scene) throw new Error(`scene-config has no "${CARTOON_SCENE_SRC}" scene`);
  const p = scene.props ?? {};
  if (!p.world || !Array.isArray(p.beats) || !p.beats.length) throw new Error(`the ${CARTOON_SCENE_SRC} scene needs props.world and a non-empty props.beats`);
  return { world: p.world, beats: p.beats, opts: p.opts ?? {} };
};
