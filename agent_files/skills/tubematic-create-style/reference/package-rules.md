# What a Tubematic style package must be

Tubematic checks every package when it is staged (`stage_style_install` returns `check` and the
scan's `refusals` and `flags`) and again when it loads one. This page is what those checks enforce
and what makes a package good, not only valid. `template/ext_template/` is a valid package to start
from.

## The folder

| Path | Holds |
|---|---|
| `style.json` | The pack (below) plus an `external` block: `version`, `author`, `source`, `licence`, `scene_api` (1), `props_key` |
| `MANIFEST.json` | `{"files": {"<path>": "<sha256>"}}` of every other file. Write it last, with `scripts/manifest.py`, after every change |
| `schema.json` | The JSON Schema every scene's `props[props_key]` must match (Draft 2020-12). `write_scene_config` enforces it |
| `components/*.tsx` | A scene style's components (`renderer` `dom`). Each default export is one scene |
| `runner/**` | A 3D world style's runner and kit (`renderer` `cartoon_3d`), built on the Cartoon 3D engine |
| `guide/guide.md` | What the authoring agent reads: the style's rules for writing a video in it |
| `guide/example-config.json` | A complete, valid scene-config in this style. `guide/example-timeline.json` is optional |
| `preview.mp4`, `preview.webp` | The picker's loop (at most 400,000 bytes) and poster (at most 40,000 bytes) |
| `fonts/` | Optional font files, with a licence file (`fonts/OFL.txt` or `fonts/LICENSE`) |
| `samples/` | Optional rendered sample videos. Never reference footage |

The folder name is the style id: `ext_` then lowercase letters, digits and `_` (at most 40). The pack's
`id` and `preview` are the same id. Plain files only: no symlinks, nothing a style has no use for (a
script, a binary). The scan refuses file types outside: `.ts .tsx .json .md .txt .css .mp4 .webm .webp
.png .jpg .jpeg .gif .svg .woff .woff2 .ttf .otf .glb .gltf .wav .mp3 .ogg` and licence files.

## The pack (`style.json`)

The fields are the built-in packs' fields; `template/ext_template/style.json` fills each one. What
Tubematic requires of an external pack: `role` `"main"`, `inserts` `{"host": false}` with
`messages.inserts` saying so, `mascot` `false`, `authoring_skill` `"tubematic-external-style"`,
`renderer` `"dom"` or `"cartoon_3d"`, `needs.gpu` true only if the style cannot render on a CPU, and
`needs.openai_key` false (external styles generate no images).

Write these fields from your study, not from the template:

- `label`, `tagline`: the style's name and one line a person reads under its preview.
- `review`: what the AI review must accept as the intended look (so it does not report the style as
  a defect) and what it must still report. Name the look's real features.
- `captions`: the caption look that matches the reference (position 0 to 1 of the height, colour,
  font, size, uppercase, `maxWords`).
- `script`: how the script writer writes for this style: the voice, sentence length, what each beat's
  `visual` must name.
- `picture`: `opening`, `turn`, `payoff`, `ending`: what the screen does at each.
- `routing`: `best_for`, `avoid_for`, `signals`, `moods`, `cannot_show` (one sentence), `images` 0.

## The schema carries the style's rules

A schema that only says `{"type": "object"}` lets an agent write anything, and the style's rules then
live only in prose. Write the rules into `schema.json` so `write_scene_config` refuses a config that
breaks them:

- `additionalProperties: false` on every object, and `required` for every field a scene needs.
- `enum` for every closed choice (scene kinds, palettes, slots, icons).
- `maxLength` on every text field, measured so it fits its box at the font size the component uses;
  `maxItems` on every list the layout can hold only so many of.
- Frame fields as integers with `minimum: 0`.
- A `description` on each field saying what it is for; the agent reads them.
- `oneOf`/`if-then` for scene kinds that take different fields.

Check the example config against your schema before you stage (a staged package whose example does
not validate is a broken package).

## Code

- Imports by name: only `react`, `react/jsx-runtime`, `remotion`, `@tubematic/scene-api`,
  `@remotion/noise`, `@remotion/paths`, `@remotion/shapes`, `@remotion/three`, `@remotion/transitions`,
  `three` (and `three/examples/jsm/…`), `@react-three/fiber`, `postprocessing`, `d3-geo`,
  `topojson-client`, `@dagrejs/dagre`, `zod`. Anything else is refused. Relative imports must stay
  inside the package.
- `@tubematic/scene-api` (version 1) exports: the `TimelineWord` and `SubtitleConfig` types;
  `FRAME_WIDTH`, `KEEP_OUT_GAP`, `KEEP_OUT_X`, `WATERMARK_BOTTOM`, `WATERMARK_HEIGHT`,
  `WATERMARK_LEFT`, `WATERMARK_RIGHT`, `WATERMARK_TOP`, `WATERMARK_WIDTH`; `estimateWidth`,
  `fitFontSize`, `wrapCount`; `fontFaceCss`, `useStyleFonts`, `FontFile`; for world styles
  `CartoonShort`, `INK_DEFAULTS`, `FPS` and the video types (`Camera`, `CamInfo`, `Dof`, `Light`,
  `SetPiece`, `ShotDef`, `Stage`, `V3`, `VideoDef`) and the camera helpers (`add`, `clamp01`,
  `dofAtOf`, `dolly`, `easeOut`, `glide`, `JOLT_FRAMES`, `joltAt`, `jolted`, `keyEnd`, `kicked`,
  `kicksAt`, `layersAt`, `lin`, `makeCamAt`, `pushK`, `rolled`, `runKeys`, `shotAt`, `smooth`, `whip`,
  `zoom`, `Cam`, `Key`, `Shot`).
- A component's default export receives `durationInFrames`, `words` (the whole video's word timings, in
  video frames) and its props under `props_key`. `useCurrentFrame()` counts from the scene's start.
- Everything is a pure function of the frame: no timers, no `Math.random()` (use a seeded generator),
  no network, no storage. The scan flags `fetch`, `eval`, `Function`, dynamic `import()`, storage and
  environment reads, and a person sees each flag before installing.
- The canvas is 1080x1920 at 30 fps. Keep text out of the watermark's box (`WATERMARK_*`,
  `KEEP_OUT_X`) and above the captions' band (the pack's `captions.position`).
- Fonts: ship `.woff2` files in `fonts/` with their licence and load them with `useStyleFonts`. Never
  load a font from the network.

## CPU cost (renders run on a CPU by default)

Measured on Tubematic's renderer: a full-frame CSS gradient costs more than twice a flat fill; SVG
`stroke-dasharray` costs 2.5x (draw dots as circles); a layer scaled every frame redraws every frame; a
full-frame image or canvas layer over changing content costs a lot (put a finish layer under the
content, drawn once); per-frame blur and SVG filters over large areas are slow (bake them, or use a
gradient disc); changing grain bloats the video. Prefer one canvas or flat SVG shapes.

## Content rules

Never put reference footage, frames from the studied videos, a channel's logo, watermark, named
characters or branding into the package. The style is the look, rebuilt in code; the package is
original work.
