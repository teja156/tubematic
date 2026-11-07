# Agent-made parts and the gate (TMDEV-181, spike)

The Cartoon 3D kit ships a curated set of parts (`partsSpec.ts` `PART_KINDS`). A world may
also bring its own, written as data in the **part grammar** (`partGrammar.ts`) under
`WorldSpec.parts`, and name them in props, clusters and foreground slots exactly like kit
kinds. The grammar, the compiler and the footprint derivation are shared with six kit parts
(`partSpecs/`), so an agent part is drawn, inked, shadowed and collision-checked by the same
code as a kit part. What is extra for an agent part is the **gate**.

## The grammar in one screen

```jsonc
{
  "name": "cottonBale",                      // lowerCamelCase, not a kit kind
  "blurb": "pressed cotton bale in burlap with two iron straps",
  "prims": [                                 // the part stands on y = 0, faces +z, long things along x
    { "kind": "box", "size": [1.4, 0.8, 0.7], "at": [0, 0.4, 0], "mat": "burlap" },
    { "kind": "box", "size": [0.06, 0.84, 0.74], "at": [-0.35, 0.42, 0], "mat": "iron",
      "repeat": { "n": 2, "step": [0.7, 0, 0] } }
  ],
  "smoke": [], "lamp": [],                   // attach points (optional)
  "solid": true, "walkable": false, "lightAtNight": false
}
```

Primitives: `box`, `cylinder` (rTop 0 = cone), `rod` (from/to), `sphere`, `torus`, `lathe`,
`shape` (flat or extruded outline), `plane`, `card` (canvas `figure` or `plate`), `group`.
Each takes `at`, `rot` (degrees), `mat` (a kit material name from `KIT_MATS`, a list of them,
or `{hsl: [h, s, l]}`), `noInk`, `repeat {n, step, turn}`, `jitter`. The footprint box is
**derived** from the primitives (`deriveDims`), never declared.

## The gate

```
node gate.mjs <scene-config.json | world.json> <outdir>                      # check + stills + judge prompts
node gate.mjs <...> <outdir> --record <part> <answers.json> [--promote]      # store a judge's verdict
```

(`node cartoon-tools/build.mjs` bundles this and the other command lines into
`cartoon-tools/dist/*.mjs`; run them from the Remotion project, or set `REMOTION_ROOT`.) For every part in the world's `parts`:

1. **Deterministic check** (`validatePartSpec`): name, blurb, primitive shapes, kit materials,
   size limits (`PART_LIMITS`), triangle budget, nothing below the ground, and **nothing
   floating** (every primitive must touch, through others, one that touches the ground). The
   headless QA (`qa.ts` `checkParts`) runs the same check and reports each failure as a
   BLOCK, so a world with a bad part can never be laid out.
2. **Two stills** of `gallery/PartGate.tsx` (composition `Cartoon3DPartGate`): three-quarter and
   near end-on, with a townsman and a crate beside the part for scale and style (a cast figure
   gets a third, alone and close), and a fixed **judge prompt** written to
   `<outdir>/<part>-judge-prompt.md`. Stills come through `gate/stills.ts`: the stills server
   when one is up (`STILLS_SERVER`), else the Remotion Node API with the project bundled once
   and one browser for the run (`GATE_GL` for the GL flags, `CARTOON_BROWSER` for a Chromium
   executable such as the container's).
3. **The judge**: a separate model call that sees only that prompt and the two stills, and
   answers five fixed questions, each with a reason: recognisable, grounded, silhouette,
   scale, style. In Claude Code that is a fresh subagent (Agent tool): no key, no vendor,
   none of the author's context. Its JSON answer is stored with `--record`. Pass = all
   five yes. The author never grades its own work.

Verdicts go to `<outdir>/verdict.json` with every attempt, keyed by a hash of the spec. A
part gets **two** judged attempts under one name; the third is refused with "fall back to a
kit part". An unchanged spec is never re-rendered or re-judged.

**Enforcement** is in the tooling, not in the author's good will: `video/stage-config.ts`
refuses to write a scene-config whose `world.parts` lack a PASS verdict for their current
spec (`gate/verdicts.ts` `unpassed`), so an unjudged part can never reach a render.

`--record ... --promote` copies a passed part into `partSpecs/promoted.json` (and its still
into `partSpecs/promoted/`), after which every world can name it like a kit kind, and the
name is reserved.

`write_scene_config` (mcp/server.py) checks only the *shape* of `props.world.parts` so a
malformed file is refused with a reason before it reaches the renderer.

## The beat gate

`gate/beatGateCli.ts` asks a different question of the finished sheet: does the frame at the
middle of every beat show what the narrator says during it? It renders one still per beat
(the real composition, captions burned in), writes `<outdir>/beat-judge-prompt.md` with each
beat's sentence, and records judges' answers with `--record`. **Two fresh judges** must
answer; a beat they split on goes to a third and the majority decides (`gate/beatVerdict.ts`).
Verdicts are keyed by a hash of world + beats + opts, so a changed shot is judged again and an
unchanged one is not. The render scripts refuse without a PASS.

Beats may carry **gesture cues** (`BeatSpec.cast[].cues`): at a frame inside the beat, taken
from the timeline's word timings, a cast member changes gesture or turns the head, so a
reaction lands on its word instead of at the cut. The checker refuses a cue outside its beat,
out of order, or naming a gesture that cast member cannot make.

## Running the checks on a scene-config

`video/qa-config.ts` runs the deterministic frame QA on the scene-config.json the agent
wrote (the `Cartoon3D` scene's `world`, `beats` and `opts`), exit 2 on any BLOCK.
