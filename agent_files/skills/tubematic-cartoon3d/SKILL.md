---
name: tubematic-cartoon3d
description: Author a Cartoon 3D narrated Short as TypeScript written for this one video against the renderer's frozen kit (shots timed to the narration, a camera built from the grammar, three.js sets, a staged cast), look at it, take it through the beat gate with fresh judges, give it a synthesised soundtrack, and submit it
---

# Tubematic Cartoon 3D authoring skill

**Invoke this skill when:** a video is at `VOICE_READY` (`generate_voice` has produced its timeline) and it is
a **Cartoon 3D** Short: its `visual_style` is `cartoon_3d`, or it is `auto` and the `tubematic-scene-config`
skill has just resolved the renderer to `cartoon_3d` (`resolved_renderer` on `get_video`). Every other video
takes the skill `get_video` names in `style.authoring_skill` (`tubematic-scene-config` unless its style has its own). A video with a mascot (`mascot` on `get_video` is set) is never a
Cartoon 3D Short, so it never reaches this skill: under `auto` the scene-config skill resolves it to the scene
renderer. Also take this skill, on its **Revising an existing video** branch,
for a `REVISION_REQUESTED` video whose scene-config carries a Cartoon 3D scene (`props.cartoon3d`). The style
renders on the GPU only: `cartoon_3d_available` on `get_video` is true while it can; the pipeline refused the
style otherwise.

---

## What you are making

A vertical 1080x1920 Short at 30 fps: flat, inked cartoon characters standing in a painted 3D world with
black ink outlines, saturated colour, soft depth of field and a camera that glides; the narration's captions
are burned in across the lower part of the frame. **You write code for this video**: a few TypeScript modules
under the video's own generated directory, against a frozen kit the renderer ships. The kit is the look
(ink, lens blur, grade, two-tone lighting, the sky, the figure drawer, the camera grammar, the builders);
the video is everything that is this story: its shots and their timing, its camera, its sets, who stands
where doing what, its lens and its soundtrack. Nothing per video is data except the beat list in the
scene-config, which the beat gate reads.

The kit's API is in `reference/kit.md` in this skill's directory; the soundtrack spec in
`reference/soundtrack.md`; the look verifier's prompt in `reference/verifier.md`. Read `kit.md` before
writing a line, then read the worked example with `cartoon_kit_read` (below). Nothing here repeats them.

## Rules that are not yours to bend

- **You never grade your own work.** The beat gate is answered by **judges**: fresh subagents with no context
  but the prompt. You never answer a judge prompt yourself, never edit a judge's answers, never call
  `cartoon_beat_gate_record` yourself, and never re-run a judge whose answer you dislike. See **Spawning a
  judge** below. The look verifier is a fresh subagent too.
- **Only the tools write.** Every source file is written with `write_scene_file`, the scene-config with
  `write_scene_config`, verdicts by the record tool from a judge's own call. There is no other path.
- **The kit is frozen.** You import from it (`../../cartoon3d/...`); you never copy a kit file into the
  video, never edit one, never add a dependency. What the kit cannot do, your set code does with three.js.
- **One scene.** The video is one generated scene, `CartoonShort.tsx`, spanning every frame. Never one scene
  per beat: the world is one WebGL mount, and remounting it breaks shadows and continuity.
- **The render is gated.** `validate_job` and `submit_render` refuse a video until its source typechecks and
  two fresh judges have passed the beat sheet for exactly the source on disk (a changed file re-opens the
  gate). Their error names the tool that closes it.
- **Every sentence is illustrated literally**, on screen, as the subject of the frame, at the time it is
  spoken. A character reacting while the named thing is off screen fails the beat gate, and should.

---

## Step 0 — read first

1. `get_video(video_id)` — the topic, the script segments and their `visual` briefs, the comments.
2. `get_timeline(video_id, include_words=True)` — `total_frames`, `fps`, the segments and **every word's
   `startFrame`/`endFrame`**. Shots are cut to sentences and reactions timed to words from this.
3. `reference/kit.md` — the contract (`VideoDef`), the camera grammar, the cast staging helpers, the
   builders, the lights, the numbers the look is measured against.
4. The worked example, through the tools: `cartoon_kit_list()` names every kit file;
   `cartoon_kit_read("examples/chicago/index.ts")`, then `story.ts`, `scenes.ts`, one set
   (`sets/river.ts` is the smallest complete one; `sets/street.ts` the richest) and one staging file
   (`stage/river.ts`). Read how it does a thing before inventing a way.
5. **Facts.** Two or three concrete, checkable details of the topic that become set dressing or props (a sign,
   a measurement, a named object). The spoken words are fixed; the picture is yours.

## Step 1 — the shot plan, to the words

Before any code, write a table with one row per shot:

| id | frames a-b | sentence (or the part of one) | the noun or action it names | what is ON SCREEN that proves it | set | light | cast | camera (type, move) | lens cInf |

- **One shot per sentence**; split a long sentence at a comma where the picture changes. Shots **tile the
  video exactly**: shot 1 starts at frame 0, each starts where the last ended (`b` exclusive), the last ends at
  `total_frames`. The beats you later put in the scene-config are these shots, `start = a`, `end = b - 1`.
- **Sets.** Two to five places, each a `SetPiece` built once and shown per shot, placed far apart in one
  world (the example puts them 1000 m apart). A set can be in several states over time (the example's
  street has four eras); pose() moves what moves.
- **Camera.** Every hold creeps (push-in 0.15–0.35 %/f, 0.6 %/f for ~35 f on a punch word); a move inside a
  shot is a glide of 18–40 f; a reframe bigger than half a frame width is a cut on its key; one or two shots
  carry a 4–8 degree roll; impacts get a kick; about a third of shots have a foreground object at one edge;
  the lens is at eye level (0.67–1.0 of a character's height) most of the time, high for an establishing
  aerial once or twice (`aerial: true`); the horizon sits at 0.40–0.50 of the frame. Depth of field on
  close-ups and inserts (12–14), medium shots (10–12), none on wides and aerials.
- **Shot mix** of the reference, as a guide: medium 27 %, full 28 %, wide 12 %, extra wide 8 %, inserts 22 %,
  close-ups 3 %. Visible character height: close-up 0.65, medium 0.50, full 0.35, wide 0.15 of the frame.
- **Light is per shot**: `day`, `golden` (sunset, the sun disc shows, long card shadows), `lamp` (a dim
  interior lit by lanterns), `hall` (a bright interior with windows). A golden shot is composed against the
  sky with the subject toward the sun. Crossfade (6–10 f) only at a change of place or time; cut otherwise.
- **Reactions land on their word.** An expression or gesture change inside a shot is timed to the word's
  `startFrame`, landing `LEAD` (2 frames) early. Aim for the first stressed word of the phrase.

## Step 2 — write the video

Write these files with `write_scene_file(video_id, scene_name, tsx_content)`; `scene_name` carries the
extension for a module (`story.ts`, `sets/street.ts`), and is the bare `CartoonShort` for the scene:

| file | what it holds |
|---|---|
| `story.ts` | `TOTAL`, the set origins, `SHOTS: ShotDef[]`, `XFADE`, `FLASH_AT?`, the story state as functions of the frame (what has moved, risen, lit by frame f), `CAMS` (camera keys per shot id), `KICKS`, `DOF`, and the exports `camAt`, `clipAt`, `dofAt` built with the grammar |
| `sets/<name>.ts` | one `SetPiece` class per place: `root` built once in the constructor (batches, blocks, water, props), `pose(id, f, cam)` for what moves |
| `scenes.ts` | the cast (outfits), the staging helpers you need (`stand`, `walk`, `pusher`, `fx`), and `stage(id, f, cam): Stage`, which calls `prepare(light, cam)` then the set's staging |
| `stage/<name>.ts` | the staging of one set, when `scenes.ts` would otherwise be long |
| `index.ts` | `export const VIDEO: VideoDef = { total, shots, xfade, flashAt, camAt, clipAt, dofAt, stage, sets, outdoor, skyVisible?, inkFor? }` |
| `CartoonShort.tsx` | the scene: `import { CartoonShort } from "../../../cartoon3d/CartoonShort"; import { VIDEO } from "./index"; export default function Scene() { return <CartoonShort video={VIDEO} frame={useCurrentFrame()} />; }` |

Imports: a module beside yours is `"./story"`, a set `"./sets/street"`; the kit is
`"../../../cartoon3d/kit/cast"`, `"../../../cartoon3d/camera"`, `"../../../cartoon3d/video"` from a file at the
top of your directory and `"../../../../cartoon3d/..."` from one under `sets/` or `stage/` (the example's own
paths are `../../kit/...` because it sits inside the kit; yours sit under `scenes/generated/<video_id>/`, three
levels below `src/`). Write the smallest set first and look at it before building the rest.

Then write the config with `write_scene_config(video_id, config)`: `totalFrames` from the timeline, `fps` 30,
`canvas: "dark"`, one scene

```json
{"type": "generated", "src": "<video_id>/CartoonShort", "startFrame": 0, "durationInFrames": <totalFrames>,
 "props": {"cartoon3d": {"beats": [{"start": 0, "end": 126, "shot": "a gentleman planks across the mud"}, ...]}}}
```

with one beat per shot (`start = a`, `end = b - 1`, `shot` = your note), captions
`{"background": "outline", "fontFamily": "Montserrat", "fontSize": 70, "maxWords": 4}` unless the person
asked otherwise, and `"sfx": []` (the soundtrack is the engine's, below). The config is refused unless the
scene spans the video and the beats tile it.

## Step 3 — the loop: typecheck, look, fix

1. `validate_job(video_id)` typechecks your video's source and what it imports; its first error lines name your file and line. A
   file that does not compile renders nothing: fix every error before looking at a frame. (Its readiness
   error about the beat gate is expected at this point; ignore it until step 4.)
2. `cartoon_still(video_id, frames)` on the **middle frame of every shot**, six at a time, and look at every
   picture: is the sentence's subject the subject of the frame; is there a foreground, a midground and a far
   ground; is the lens at eye level and the horizon where it should be; is anyone cropped, hidden, floating,
   or standing under the caption band; does the light come from somewhere; does a golden frame show sky; are
   the characters the size the shot type says. A still renders the source as it is on disk (the first after
   an edit takes ~20 s longer).
3. Fix the code, write the file again, look again. Do not move on while a frame you can see is wrong.
4. **The look verifier**, once the frames are presentable: render six to eight stills spanning the sets and
   lights, then spawn a **fresh subagent** whose entire prompt is `reference/verifier.md` with its
   placeholders filled (the frame names, read through `cartoon_read_still` kind `"stills"`). It scores eight
   areas out of ten against the measured targets and lists numbered fixes. Do its fixes that you agree are
   real; aim for 6 or better everywhere. Two rounds are normal; stop when a round moves nothing.

## Step 4 — the beat gate

Call `cartoon_beat_gate(video_id)`. It renders one frame at the middle of every beat and returns the
`judge_prompt` that pairs each frame with its sentence. **Look at the stills first** (`cartoon_read_still`
with kind `"beatgate"`) and fix any beat whose frame plainly does not show its sentence before spending a
judge. Then spawn **two judges, one after the other**, each with the prompt verbatim; call
`cartoon_beat_gate` again to read the status. It says which judge is still owed; a beat the two split on
needs a **third**.

Any beat marked **NO**: do what the judge's `fix` line says (put the named thing on screen, move the shot,
drop the reacting character), write the file, and call `cartoon_beat_gate` again. Any edit to the source
gives a new hash, new stills, and needs its two judges again; an unchanged source keeps its verdict. So
finish the look before the gate, and touch nothing after a PASS.

## Step 5 — the soundtrack

With the shots final, write the soundtrack spec (`reference/soundtrack.md`): music sections by mood with
their spans in seconds, hits on the impacts, dips under quiet sentence ends; sound-effect cues on the frames
of the things the picture shows (a bell when the bell is struck, hooves while the horse walks, a bed of the
place under every section). Call `cartoon_soundtrack(video_id, spec)` (about a minute); read its `cues`
sheet for the levels and its `loudness`; fix a refused cue by name. The render muxes the mix in place of the
bare voice. Calling it again replaces the mix.

## Step 6 — validate and submit

1. `validate_job(video_id)`: fix every error and read the warnings.
2. `submit_render(video_id)`. It queues the video and returns; the renderer renders it in segments and
   muxes the soundtrack. Do not poll. From here the source is frozen: `write_scene_file` refuses the video
   while it is queued or rendering, and the renderer renders exactly the tree the judges passed (a tree that
   differs fails the render back to you). Change nothing until the video is `REVISION_REQUESTED` or done.
3. `add_comment` with the shot table as sentence → what is on screen, the verifier's scores per round, the
   beat gate's verdict and the judges' words, and the soundtrack's section map.

## Revising an existing video

On `REVISION_REQUESTED`: read the current files with `read_scene_file(video_id=..., scene_name="story.ts")`
(and `list_scene_files(source="generated", video_id=...)` to see them all), change **only** what the
feedback names, and write them back. Any change re-opens the beat gate (two judges). If the video was
**re-voiced**, the timeline changed: re-derive every shot's frames, every cue and the soundtrack's spans to
the new word timings before anything else, then the gate, then `cartoon_soundtrack` again (an older mix is
ignored by the render). Then `validate_job` and `submit_render`.

---

## Spawning a judge

A judge is a **fresh subagent** with no other context: start a new general-purpose subagent whose **entire
prompt is the `judge_prompt` text verbatim**, nothing before it and nothing after it. Do not add the topic,
the script, your plan, your opinion or what you hope it answers. The prompt tells the judge which stills to
read (`cartoon_read_still`) and which record tool to call with its answers; the judge does both itself.

- One judge per subagent. The second beat-gate judge is a **new** subagent, spawned after the first has
  recorded; identical answers are refused by the record tool.
- Wait for the judge to finish; then call the gate tool again to read the verdict. Do not relay a judge's
  answers through your own hands.
- A judge that cannot see a still, or that the record tool refused, is reported in your comment; it is not
  answered on its behalf.
