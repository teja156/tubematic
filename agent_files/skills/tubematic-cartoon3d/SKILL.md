---
name: tubematic-cartoon3d
description: Author a Cartoon 3D narrated Short as data (a painted 3D world, a cast, a beat sheet timed to the narration) and take it through the frame check, the part gate and the beat gate to a render
---

# Tubematic Cartoon 3D authoring skill

**Invoke this skill when:** a video is at `VOICE_READY` (`generate_voice` has produced its timeline) and it is
to be a **Cartoon 3D** Short: the video's visual style says so, or the person running the pipeline asked for
one in a comment on the video or in the user preferences. Every other video takes the `tubematic-scene-config`
skill. Also take this skill, on its **Revising an existing video** branch, for a `REVISION_REQUESTED` video
whose scene-config carries a `Cartoon3D` scene.

---

## What you are making

A vertical 1080x1920 Short at 30 fps: flat, inked cartoon characters standing in a painted 3D world with black
ink outlines, saturated colour, soft depth of field and a camera that glides; the narration's captions are
burned in across the lower part of the frame. You do not write a component. You write **data**: a world (a
town plan with slots, parts placed in them, marks the cast walks between, shots the camera glides through,
water, fog, time of day), a cast (people described by their clothes and what they hold), and a beat sheet
(one beat per sentence: a shot, who is in it, what the props do, when a reaction lands). The renderer builds
and lights the world from that data, draws the cast on lit cards inside it, and the pipeline checks the data
before any frame is rendered.

The data contract is in `reference/world-data.md` in this skill's directory. Read it before writing a world;
nothing below repeats it.

## Rules that are not yours to bend

- **You never grade your own work.** The part gate and the beat gate are answered by **judges**: fresh
  subagents with no context but the prompt. You never answer a judge prompt yourself, never edit a judge's
  answers, never call `cartoon_gate_record` or `cartoon_beat_gate_record` yourself, and never re-run a judge
  whose answer you dislike. See **Spawning a judge** below.
- **Only the tools write.** The scene-config is written with `write_scene_config` and nothing else; verdicts
  are written by the record tools from a judge's own call. There is no other path, and there must not be.
- **Only data.** Parts come from the catalog (`cartoon_catalog`) or are written in the part grammar and pass
  the gate. There is no code to write in this style.
- **Budgets.** A part or cast name gets **two** judged attempts; a world may have at most **eight** names
  refused by the judge. The beat gate has no cap on rounds, but every round costs two judges: look at the
  stills yourself before you spend them.
- **The render is gated.** `validate_job` and `submit_render` refuse a video while any part lacks a PASS for
  its current spec, while the beat sheet lacks its judges' PASS, or while the frame check blocks. Their error
  names the tool that closes the gate.

---

## Step 0 — read first

1. `get_video(video_id)` — the topic, the script segments and their `visual` briefs, the comments.
2. `get_timeline(video_id, include_words=True)` — `total_frames`, `fps`, the segments and **every word's
   `startFrame`/`endFrame`**. Beats are cut to sentences and reactions are timed to words from this.
3. `cartoon_catalog()` — every part you may name, with its footprint in metres and what it is; the promoted
   cast; the gestures, hats, holds and coats the cast grammar knows.
4. `reference/world-data.md` — the data contract and a complete small example.

## Step 1 — the shot plan, to the words

Before any world exists, write a table with one row per beat:

| beat | frames | sentence | the noun or action it names | what is ON SCREEN that proves it | shot | cast | props | tod / fog |

- **One beat per sentence**; split a long sentence at a comma where the picture changes. Beats **tile the
  video exactly**: the first starts at frame 0, each starts the frame after the last ended, the last ends at
  `total_frames - 1`. The checks refuse anything else.
- **Every sentence is illustrated literally.** If the sentence names a boat, a barge, a door, a telegraph,
  that thing is the subject of the frame. A character reacting while the named thing is off screen fails the
  beat gate. A beat may have **no cast at all** (`cast: []`) when the sentence is about a thing: use that.
- **Reactions land on their word.** A gesture change inside a beat is a cue on the cast member:
  `cues: [{frame, gesture}]`, with `frame` the word's `startFrame` (the renderer lands it two frames early
  and blends it over ten). Aim for the first stressed word of the phrase, not the sentence start.
- **Camera.** Every hold creeps; a move between beats is a glide of 18-40 frames unless the jump is big
  (then `cut: true`); impacts get a kick; one or two shots carry a 4-8 degree roll; about a third of shots
  have a foreground prop at one edge; the lens is at eye level (0.67-1.0 of a character's height) most of
  the time, high for an establishing aerial once or twice; the horizon sits at 0.40-0.50 of the frame. Depth
  of field (`dof`) on close-ups and inserts (12-14), medium shots (10-12), none on wides and aerials. Put the
  kicks, emphasis spans and rolls in `opts.motion` at the frames of their words.
- **Shot mix** of the reference, as a guide: medium 27 %, full 28 %, wide 12 %, extra wide 8 %, inserts
  22 %, close-ups 3 %. Visible character height: close-up 0.65, medium 0.50, full 0.35, wide 0.15 of the frame.
- **Time of day is per beat.** A sunset Short is day beats (`tod: 0`) and golden beats (`tod: 0.5`), never a
  clock drifting between them. Compose a golden beat against the sky and lit ground with the subject toward
  the sun (the sun disc sits low, right of the lens axis); a wall filling the frame at golden hour reads as a
  violet mass. A story fog is a beat's `fog` with a colour (white-grey for a river fog) and a near distance
  that hides what the story hides.

## Step 2 — the world and the cast

Write the **cast first**: who is in which beat, what they wear, what they **hold** (a captain with a frock
coat, a top hat and a cane; a clerk in shirtsleeves holding a paper; a lady with a flag). Blurbs say what the
viewer will see, because the judge judges recognisability from the costume and the held thing. Use the two
fixed characters (`newsboy`, `operator`) only when the story wants a newsboy or a telegraph operator.

Then build what the plan needs and nothing else: the plan (a street or a clearing), the ground, buildings
with styles and signs, props in slots, clusters of set dressing **upstage** of each mark (behind the subject
as seen from its shot: the only side a 9:16 frame reliably shows), scatter, water as a sheet, terrain beyond
the flat zone, marks for every place a cast member stands or walks to, a shot per beat (or shared), fog,
the clock, the look. Named props with cues for anything that moves, appears or vanishes.

When the catalog lacks a thing the story needs, write it in the **part grammar** under `world.parts`
(boxes, cylinders, rods, spheres, tori, lathes, shapes, planes, cards, groups; kit materials; it stands on
y = 0 and faces +z; nothing may float). It goes through the gate like a cast figure.

Write the config with `write_scene_config(video_id, config)`: one scene, `source: "installed"`,
`src: "Cartoon3D"`, spanning every frame, with `props: {world, beats, opts}`; `opts.post` is `"v2"`;
captions `{"background": "outline", "fontFamily": "Montserrat", "fontSize": 70, "maxWords": 4}` unless the
person asked otherwise. The exact shape is in the reference.

## Step 3 — gate the parts and the cast

Call `cartoon_gate(video_id)`. It checks every part and cast figure the world carries, renders each new one
beside a townsman and a crate, and returns per part a status and, for each one **awaiting judge**, a
`judge_prompt`. For each of those, **spawn a judge** (below). When every judge has recorded, call
`cartoon_gate` again and read the verdicts.

A **NO** comes with the judge's reasons: change the spec or the blurb (a vaguer blurb is never the fix) and
gate again; after the second refusal, drop the name and use a kit or promoted part. A part whose spec is
unchanged keeps its PASS: do not re-gate what you did not change.

## Step 4 — the loop: check, look, fix

1. `cartoon_qa(video_id)` until it reports **0 blocking**. Read every `advise` line and fix what is real
   (a tiny subject, a bare frame, a prop in front of the lens).
2. `cartoon_still(video_id, frames)` on the **middle frame of every beat**, six at a time, and look at every
   picture: is the sentence's subject the subject of the frame; is there a foreground, a midground and a
   far ground; is the lens at eye level and the horizon where it should be; is anyone cropped, hidden, or
   standing under the caption band; does the light come from somewhere; does a golden frame show sky.
3. Fix the data, `write_scene_config` again, repeat. Do not move to the beat gate while a frame you can see
   is wrong: a judge is for what you cannot see yourself.

## Step 5 — the beat gate

Call `cartoon_beat_gate(video_id)`. It renders one frame at the middle of every beat and returns the
`judge_prompt` that pairs each frame with its sentence. **Look at the stills first** (`cartoon_read_still`
with kind `"beatgate"`) and fix any beat whose frame plainly does not show its sentence before spending a
judge. Then spawn **two judges, one after the other**, each with the prompt verbatim; call
`cartoon_beat_gate` again to read the status. It says which judge is still owed; a beat the two split on
needs a **third**.

Any beat marked **NO**: do what the judge's `fix` line says (put the named thing on screen, move the shot,
drop the reacting character), `write_scene_config`, and call `cartoon_beat_gate` again. A changed beat sheet
has a new hash, new stills, and needs its two judges again; an unchanged one keeps its verdict.

## Step 6 — validate and submit

1. `validate_job(video_id)`: fix every error (a Cartoon 3D readiness error names the gate that is open and
   the tool that closes it) and read the warnings.
2. `submit_render(video_id)`. It queues the video and returns; the render worker does the rest. Do not poll.
3. `add_comment` with the beats as sentence → what is on screen, the parts and cast you gated and the
   judges' words, and the beat gate's verdict.

## Revising an existing video

On `REVISION_REQUESTED`: read the current config with `get_scene_config`, change **only** the data the
feedback names, and write the config back with everything else carried through unchanged. A part whose spec
is unchanged keeps its PASS; a changed beat sheet needs the beat gate again (two judges); the frame check
runs on whatever you wrote. If the video was **re-voiced**, the timeline changed: re-derive every beat's
frames and every cue to the new word timings before anything else. Then `validate_job` and `submit_render`.

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

## Not available in this version

The soundtrack (music sections and sound effects as a spec), the look verifier, agent-written code parts and
promotion of a passed part into the kit are not wired into the pipeline yet. Do not try to supply them by
other means: note in your comment what the video would have needed.
