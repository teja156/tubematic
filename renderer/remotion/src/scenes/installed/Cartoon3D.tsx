// PROBE (TMDEV-179 spike, throwaway): a whole Cartoon 3D world as ONE
// scene-config.json entry. The agent's world and beat sheet arrive as plain
// JSON props, so CompositionBuilder's captions, voice and watermark work
// unchanged on top of it. The real component would live here too.
import { WorldView } from "../../cartoon3d/probe2/WorldView";
import type { SceneOpts } from "../../cartoon3d/probe2/sceneOpts";
import type { BeatSpec, WorldSpec } from "../../cartoon3d/probe2/worldKit";

export default function Cartoon3D(props: { world: WorldSpec; beats: BeatSpec[]; opts?: SceneOpts }) {
  return <WorldView spec={props.world} beats={props.beats} opts={props.opts ?? {}} />;
}
