// Cartoon 3D (TMDEV-179): a whole world as ONE scene-config.json entry. The
// agent's world and beat sheet arrive as plain JSON props (see
// agent_files/skills/tubematic-cartoon3d/reference/world-data.md), so
// CompositionBuilder's captions, voice and watermark work unchanged on top.
import { WorldView } from "../../cartoon3d/probe2/WorldView";
import type { SceneOpts } from "../../cartoon3d/probe2/sceneOpts";
import type { BeatSpec, WorldSpec } from "../../cartoon3d/probe2/worldKit";

export default function Cartoon3D(props: { world: WorldSpec; beats: BeatSpec[]; opts?: SceneOpts }) {
  return <WorldView spec={props.world} beats={props.beats} opts={props.opts ?? {}} />;
}
