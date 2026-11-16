---
name: tubematic-lowpoly-skit
description: Author a Low-Poly Skit narrated Short as TypeScript written for this one video against the renderer's frozen low-poly kit (about one shot per second, flat-shaded toy people in small 3D dioramas, hard cuts, push-ins, footstep and impact jolts), look at it, take it through the beat gate with fresh judges, give it a synthesised soundtrack, and submit it
---

# Tubematic Low-Poly Skit authoring skill

**Invoke this skill when:** a video is at `VOICE_READY` (`generate_voice` has produced its timeline) and its
`visual_style` is `low_poly_skit` (`get_video` names this skill in `style.authoring_skill`), or it is a
`REVISION_REQUESTED` video whose scene-config carries a generated scene with `props.cartoon3d` and whose
style is `low_poly_skit`. Low-Poly Skit shares its engine with Cartoon 3D (one generated scene, a beat gate,
a synthesised soundtrack, a frozen source) but not its look, its kit or its GPU rule: it renders on a CPU or a
GPU. A video with a mascot is never a Low-Poly Skit video, and it takes no insert scenes.

---

## What you are making

A vertical 1080x1920 Short at 30 fps: flat-shaded toy people (one house figure, about four heads tall, with
faceted heads and blank dot eyes) acting out the narration in small diorama sets built from basic shapes, on a
plain void. **A new shot about every second**, hard cuts only, a slow push-in on nearly every hold, a camera
jolt on every footstep and impact, yellow star bursts and flying chips on a hit, crowds of hundreds, scale
jumps from a room to the planet. The narration's captions are burned in (white words turning yellow as they are
spoken). There are no outlines, no shadows, no lens blur and no generated images: the look is flat colour and
facets, which is also why it is cheap to render.

**You write code for this video**: a few TypeScript modules under the video's own generated directory against a
frozen kit the renderer ships. The kit is the figure, its faces, poses and cycles, the crowd, the effects, the
diorama builders, the camera moves and the runner; the video is everything that is this story: its shots and
their timing, its sets, who stands where doing what, its camera and its soundtrack. Nothing per video is data
except the beat list in the scene-config, which the beat gate reads.

The kit's API is in `reference/kit.md`; the look verifier's prompt in `reference/verifier.md`; the soundtrack
spec in the **tubematic-cartoon3d** skill's `reference/soundtrack.md` (the same engine). Read `kit.md` before
writing a line, then read the worked example with `cartoon_kit_read` (below). Nothing here repeats them.

## Rules that are not yours to bend

- **You never grade your own work.** The beat gate is answered by **judges**: fresh subagents with no context
  but the prompt. You never answer a judge prompt yourself, never edit a judge's answers, never call
  `cartoon_beat_gate_record` yourself, and never re-run a judge whose answer you dislike. See **Spawning a
  judge** below. The look verifier is a fresh subagent too.
- **Only the tools write.** Every source file is written with `write_scene_file`, the scene-config with
  `write_scene_config`, verdicts by the record tool from a judge's own call.
- **The kit is frozen.** You import from it; you never copy a kit file into the video, never edit one, never add
  a dependency. What the kit cannot do, your set code does with three.js.
- **One scene.** The video is one generated scene, `CartoonShort.tsx` (the name every 3D world uses), spanning
  every frame. Never one scene per beat: the world is one WebGL mount.
- **The render is gated.** `validate_job` and `submit_render` refuse a video until its source typechecks and
  two fresh judges have passed the beat sheet for exactly the source on disk (a changed file re-opens the
  gate). Their error names the tool that closes it.
- **Every sentence is shown literally**, on screen, as the subject of the frame, at the time it is spoken.

---

## Step 0: read first

1. `get_video(video_id)`: the topic, the script segments and their `visual` briefs, the comments.
2. `get_timeline(video_id, include_words=True)`: `total_frames`, `fps`, the segments and **every word's
   `startFrame`/`endFrame`**. Shots are cut to sentences and hits are timed to words from this.
3. `reference/kit.md`: the contract (`LowPolyDef`), the figure, poses, cycles, crowd, effects, builders, camera.
4. The worked example, through the tools: `cartoon_kit_list()` names every kit file; read
   `cartoon_kit_read("lowpoly/examples/dig/index.ts")`, then `story.ts` and `sets.ts` (a garden, a cutaway, a
   street with a crowd, a planet). Read how it does a thing before inventing a way.
5. **Facts.** Two or three concrete, checkable details of the topic that become set dressing or props (a sign
   with a number, a labelled layer, a named object). The spoken words are fixed; the picture is yours.

## Step 1: the shot plan, to the words

Before any code, write a table with one row per shot:

| id | frames a-b | the words | what is ON SCREEN that proves them | set | cast and pose | camera (move) | hit / jolt |

- **About one shot a second.** A sentence of six to ten words is one or two shots; split a long sentence where
  the picture changes. Shots **tile the video exactly**: shot 1 starts at frame 0, each starts where the last
  ended (`b` exclusive), the last ends at `total_frames`. The beats you later put in the scene-config are these
  shots, `start = a`, `end = b - 1`. Never a shot shorter than 15 frames or longer than about 75.
- **Sets.** Two to six small places, each a `SetPiece` built once, placed far apart in x (the example uses 100 m
  steps). A set is a few dozen primitives, not a world. A scale ladder (a room, a street, a stadium, a planet)
  is the style's best trick: give every rung its own set.
- **Camera.** Hard cuts between shots. Every hold pushes in (0.3 to 0.5 % a frame); locked-off shots are the
  exception (about one in six). A footstep gets `joltAt` on each `footfalls()` frame; a strike gets a jolt on
  its frame; one or two shots per video carry a `whip` to a second framing inside the shot.
- **Action.** Poses snap in 2 to 6 frames with no anticipation. Walks and jigs are cycles; a fall is a pose
  change. A face is a hard swap between frames and never follows the speech. A prop is parented to a hand
  (`fig.handR.add(prop)`) on the frame it is picked up.
- **Hits.** On the strongest sentence of a turn: a `Burst`, `Debris` and one `ComicWord`, all started on the
  hit's frame, with a jolt on that frame. Do not put a burst on every shot.
- **Reactions land on their word.** A pose or face change is timed to the word's `startFrame`, landing 2 frames
  early.

## The opening and the beats

`get_timeline` gives each segment a `beat` and a `role`, and the result a `first_frame` (the formula's line on
what the first frame shows). `get_video`'s `style.picture` says how this style does each; in short:

- Opening: shot 1 is already in motion at frame 0, a figure mid-action in the set the first sentence names,
  the camera already pushing in. Never a title or an empty set.
- Turn or re-opening: a hard cut to a new shot on its first word, with a jolt or a burst on it.
- Payoff: the biggest scale of the video or the strongest hit, held a little longer than the other shots.
- Ending: hold the payoff to the last frame. No closing card, logo, recap or sign-off.

## Step 2: write the video

Write these files with `write_scene_file(video_id, scene_name, content)`; `scene_name` carries the extension for
a module (`story.ts`, `sets.ts`), and is the bare `CartoonShort` for the scene:

| file | what it holds |
|---|---|
| `story.ts` | `TOTAL`, `SHOTS: LPShot[]`, the cameras (`camAt(id, f)`, built from `camera.ts`), the jolt and hit frames, `blurAt` |
| `sets.ts` (or `sets/<name>.ts`) | one `SetPiece` class per place: `root` built once, `pose(id, f, cam)` for everything that moves |
| `index.ts` | `export const VIDEO: LowPolyDef = { total, shots, camAt, sets, background, light?, blurAt? }` |
| `CartoonShort.tsx` | `import { LowPolyShort } from "../../../cartoon3d/lowpoly/LowPolyShort"; import { VIDEO } from "./index"; export default function Scene() { return <LowPolyShort video={VIDEO} frame={useCurrentFrame()} />; }` with `useCurrentFrame` from `remotion` |

Imports: the kit is `"../../../cartoon3d/lowpoly/<file>"` and `"../../../cartoon3d/camera"` from a file at the
top of your directory, and `../../../../cartoon3d/...` from one a level deeper (the example's own paths are
shorter because it sits inside the kit). `three` is `import * as THREE from "three"`. Everything is a pure
function of the frame: no `Math.random`, no `Date`; use the kit's seeded helpers. Write the smallest set first
and look at it before building the rest.

Then write the config with `write_scene_config(video_id, config)`: `totalFrames` from the timeline, `fps` 30,
`canvas: "dark"`, one scene

```json
{"type": "generated", "src": "<video_id>/CartoonShort", "startFrame": 0, "durationInFrames": <totalFrames>,
 "props": {"cartoon3d": {"beats": [{"start": 0, "end": 29, "shot": "you walk to the lawn with a shovel"}, ...]}}}
```

with one beat per shot, `"sfx": []` (the soundtrack is the engine's, below), and the captions from the style:
`{"look": "karaoke", "background": "outline", "uppercase": true, "position": 0.65, "accent": "#FFD221",
"fontFamily": "Montserrat", "fontSize": 70, "maxWords": 4}` unless the person asked otherwise. The config is
refused unless the scene spans the video and the beats tile it.

## Step 3: the loop: typecheck, look, fix

1. `validate_job(video_id)` typechecks your video's source and what it imports; its first error lines name your
   file and line. A file that does not compile renders nothing: fix every error first. (Its readiness error
   about the beat gate is expected at this point.)
2. `cartoon_still(video_id, frames)` on the **middle frame of every shot**, six at a time, and look at every
   picture: is the sentence's subject the subject of the frame; is any figure cropped, floating, buried in a
   wall or floor, or standing under the caption band (the lower third of the frame, from about 60 % down); is the
   set small enough to read and big enough to fill the frame; does a crowd have colour variety; is a hit
   actually on screen. A still renders the source as it is on disk (the first after an edit takes longer).
3. Fix the code, write the file again, look again. Do not move on while a frame you can see is wrong.
4. **The look verifier**, once the frames are presentable: render six to eight stills spanning the sets, then
   spawn a **fresh subagent** whose entire prompt is `reference/verifier.md` with its placeholders filled. It
   scores areas out of ten and lists numbered fixes. Do the fixes you agree are real; aim for 6 or better
   everywhere. Two rounds are normal; stop when a round moves nothing.

## Step 4: the beat gate

Call `cartoon_beat_gate(video_id)`. It renders one frame at the middle of every beat and returns the
`judge_prompt` that pairs each frame with its sentence. **Look at the stills first** (`cartoon_read_still` with
kind `"beatgate"`) and fix any beat whose frame plainly does not show its sentence before spending a judge. Then
spawn **two judges, one after the other**, each with the prompt verbatim; call `cartoon_beat_gate` again to read
the status. A beat the two split on needs a **third**. Any beat marked **NO**: do what the judge's `fix` line
says, write the file, and call `cartoon_beat_gate` again. Any edit to the source gives a new hash and needs its
two judges again, so finish the look before the gate, and touch nothing after a PASS.

## Step 5: the soundtrack

With the shots final, write the soundtrack spec (the tubematic-cartoon3d skill's `reference/soundtrack.md`):
music sections by mood with spans in seconds, hits on the impacts, dips under quiet sentence ends, and sound
cues on the frames of what the picture shows. For this style: a low boom on every footstep (the `footfalls()`
frames), a hit sound on every burst, a short silence in the music for a deadpan beat, and a bed of the place
under each section. Call `cartoon_soundtrack(video_id, spec)`; read its `cues` sheet and `loudness`; fix a
refused cue by name. The render muxes the mix in place of the bare voice. Calling it again replaces the mix.

## Step 6: validate and submit

1. `validate_job(video_id)`: fix every error and read the warnings.
2. The look of this style is `cartoon_still` (Step 3) and the beat gate (Step 4): the gate already requires the
   stills of exactly this source, so there is no other look step. If any file or the config changed after the
   gate, it is open again: take it through the gate before you submit.
3. `submit_render(video_id)`. It queues the video and returns; the renderer renders it in segments and muxes the
   soundtrack. Do not poll. From here the source is frozen: `write_scene_file` refuses the video while it is
   queued or rendering, and the renderer renders exactly the tree the judges passed. Change nothing until the
   video is `REVISION_REQUESTED` or done.
4. `add_comment` with the shot table as sentence → what is on screen, the verifier's scores per round, the
   beat gate's verdict and the judges' words, and the soundtrack's section map.

## Revising an existing video

On `REVISION_REQUESTED`: read the current files with `read_scene_file(video_id=..., scene_name="story.ts")` (and
`list_scene_files(source="generated", video_id=...)` to see them all), change **only** what the feedback names,
and write them back. Any change re-opens the beat gate (two judges). If the video was **re-voiced**, the
timeline changed: re-derive every shot's frames, every hit and the soundtrack's spans to the new word timings
before anything else, then the gate, then `cartoon_soundtrack` again (an older mix is ignored by the render).
Then `validate_job` and `submit_render`.

---

## Spawning a judge

A judge is a **fresh subagent** with no other context: start a new general-purpose subagent whose **entire
prompt is the `judge_prompt` text verbatim**, nothing before it and nothing after it. Do not add the topic, the
script, your plan, your opinion or what you hope it answers. The prompt tells the judge which stills to read
(`cartoon_read_still`) and which record tool to call with its answers; the judge does both itself.

- One judge per subagent. The second beat-gate judge is a **new** subagent, spawned after the first has
  recorded; identical answers are refused by the record tool.
- Wait for the judge to finish; then call the gate tool again to read the verdict. Do not relay a judge's
  answers through your own hands.
- A judge that cannot see a still, or that the record tool refused, is reported in your comment; it is not
  answered on its behalf.
