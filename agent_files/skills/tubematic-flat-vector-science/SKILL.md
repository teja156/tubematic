---
name: tubematic-flat-vector-science
description: Author a Flat Vector Science narrated Short as data — flat glowing creatures, cells, planets and scale references drifting in the dark, named by word-lit pills — plan shots (a subject with a measuring rule, a ladder of sizes, a power-of-ten zoom, a descent with a depth gauge, a process in stages), time props, pills, counters and rungs to the narration, draw a prop of your own when the library lacks one and look at it with render_style_parts, then write it with write_scene_config, validate and submit it
---

# Tubematic Flat Vector Science authoring skill

**Invoke this skill when:** a video is at `VOICE_READY` and `get_video` says `style.authoring_skill` is
`tubematic-flat-vector-science` (its `visual_style` is `flat_vector_science`). Also take it, on
**Revising**, for a `REVISION_REQUESTED` video at that style. Every other video takes the skill its
`style.authoring_skill` names.

---

## What you are making

A vertical 1080x1920 Short in the look of a calm science channel: flat, outline-free subjects shaded in
two tones (creatures, cells, organs, planets, rockets, mountains, and a bus or a person for scale)
drift on a dark backdrop with small specks floating past. Words the narrator says light up white in
dark rounded **pills** on a leader line to the thing they name. The video is about **scale**: how deep,
how big, how far, how small. Exactly one number or word in a shot may be **red**: the one that lands.
Captions are small white words low in the frame.

The shot kinds:

| Kind | What it shows |
|---|---|
| `subject` | 1 to 3 props in named slots, drifting; up to 2 word-lit pills on leader lines; an optional measuring rule beside a prop |
| `ladder` | 2 to 5 rungs: each larger thing grows in from beyond the frame while the last one shrinks to a small mark, its name and size in a title pill |
| `zoom` | 2 to 6 levels of a power-of-ten zoom: the camera pulls back, the last thing shrinks away tenfold and the scale bar snaps to the next label |
| `descent` | 2 to 6 layers going down: the backdrop darkens with depth, a depth counter rolls, a gauge on the left fills, each layer's thing rises in |
| `stages` | 2 to 5 stages of a process: each stage's thing pops in large while the earlier ones line up small along the bottom, joined by arrows |

Any shot may also carry a `counter`, a big rolling number near the top (a depth, a temperature, a count).

Backdrops: `abyss`, `ocean`, `night`, `sky`, `strata`, `inside`. Slots: `center`, `left`, `right`, `top`, `bottom`. Sizes: `s`, `m`, `l` (a prop's longest side
is drawn at about 260, 460 or 780 pixels). How a shot arrives (`cut`): `cut`, `lens`, `flash`, `push`.

**You write data, and at most a few still drawings.** The whole video is one installed scene,
`FlatVectorScience`, and everything about it is its `props.flatVector`. You never call `generate_image`
or `generate_character`: this style has no photographs.

The full field reference is `reference/contract.md`; the worked example is
`reference/example-config.json` (narration in `reference/example-timeline.json`), and
`reference/example-prop-octopus.tsx` is a finished drawing of your own. Read all of them before you write.

## Rules the tools enforce

`write_scene_config` refuses a Flat Vector Science config that breaks any of these, and says which shot
and which field:

- 3 to 12 shots. The first starts at frame 0 on a `cut`; every other shot starts within 2 frames of a
  word's start and lasts at least 1.5 s.
- Every frame you give (an item's `at`, a pill part's `at`, a rule's, a counter's, a rung's, a level's,
  a layer's, a stage's) is inside its shot and within 2 frames of a word's start, in order within a list.
- A `subject` holds 1 to 3 items, each in its own slot; a pill names a slot that holds an item and has
  1 or 2 parts of 1 to 18 characters, and must fit the frame; a rule stands beside an item.
- A label is 1 to 14 characters, a value or a rule or level label 1 to 12, a unit at most 4.
- A descent's layers go deeper each time.
- At most one red thing in a shot (a pill part, a rung, a level, a layer, a stage or the counter).
- A ladder, zoom, descent or stages shot keeps its last arrival on screen at least 20 frames before the
  next shot; in a subject shot, the last pill word (16 frames) or the rule (12 frames) has finished lighting before
  the next shot.
- Nothing may sit still for more than 4 seconds: a prop, a pill word, a rule, a counter, a rung, a
  level, a layer or a stage must arrive on a word within every 4-second stretch (the drift does not count).
- A lens or push transition runs over the frames before its shot; it may not run inside an insert.
- Your own props: at most 8 in `customProps`, each `{"id", "src", "box", "light"?}`.

## Step 0 — read

`get_video(video_id)` for the style block (`style.extra.props` lists the library by group, and
`style.extra.boxes` every prop's box), `get_timeline(video_id)` for the words, the segments, their
`beat`, `role` and `insert`.

## Step 1 — plan the shots

Give each sentence that names a new subject or a new number its own shot or its own arrival. Use a
`descent` when the narration goes down through depths, a `ladder` when it climbs through sizes, a
`zoom` when it steps through powers of ten, `stages` when it walks a process, and a `subject` for
one thing with its numbers. Put the one red mark on the number the video is building to.

## Step 2 — props

Use the library first:

- sea: `whale`, `shark`, `squid`, `jellyfish`, `anglerfish`, `fish`, `fish_school`, `diver`, `submarine`, `shipwreck`, `coral`
- body: `cell`, `red_blood_cell`, `neuron`, `virus`, `bacterium`, `dna`, `heart`, `lungs`, `brain`, `eye`, `mitochondrion`
- space: `sun`, `star`, `earth`, `moon`, `mars`, `jupiter`, `saturn`, `black_hole`, `galaxy`, `comet`, `rocket`, `astronaut`, `satellite`
- earth: `mountain`, `volcano`, `cloud`, `raindrop`, `lightning`, `iceberg`, `tree`, `rock`
- scale: `bus`, `person`, `skyscraper`, `plane`, `car`

Props that give light (`jellyfish`, `anglerfish`, `diver`, `submarine`, `neuron`, `sun`, `star`, `black_hole`, `galaxy`, `comet`, `rocket`, `volcano`, `lightning`) get a soft halo. Pick the size that reads: `l` for the one
subject of a shot, `m` for two side by side, `s` for a scale reference (a person, a bus) beside a big one.

When a thing the narration names is not in the library, draw it: a still React component in
`generated/<video_id>/prop-<name>.tsx`, written with `write_scene_file(video_id, "prop-<name>", tsx)`
(lowercase letters, digits and hyphens), modelled on the library (read it with `read_scene_file`,
source `installed`, `flatVector/props`). Import only from `react` and `../../installed/flatVector/toon`
(`Toon`, `GlowDot`, `Eye`, `circleD`, `ellipseD`, `rrectD`): flat two-tone shapes with a lighter rim and a
darker shadow plane, no outlines, no text, no images, no filters or gradients of your own, no hooks and
nothing that depends on the frame: the renderer draws it once and moves it. The file default-exports
the drawing as a function (`export default function Octopus() { ... }`). Centre it on (0, 0) inside
its `box` [width, height] (every pixel inside), and list it in `customProps`:
`{"id": "octopus", "src": "<video_id>/prop-octopus", "box": [360, 360]}` (add `"light": "#rrggbb"` for
a halo). Then look at it: `render_style_parts(video_id)` (after `write_scene_config`) draws your props as
the scene will, with their box. Fix what does not read and write again.

## Step 3 — pills, counters and rules

- A pill's first part lights on the word that names the thing, the second on the word that gives its
  number (`{"text": "SPERM WHALE", "at": ...}, {"text": "2,000 M", "at": ...}`). Write them in capitals.
- A counter rolls from the last shot's counter (or from `from`, or 0) to `value` on its word.
- A rule draws beside the item it measures, on the word of the size, with a short label (`16 M`).

## Step 4 — captions

Leave `subtitles` out of the config. The style fills in its own caption look; any key you set
overrides it.

## The opening and the beats

`get_timeline` gives each segment a `beat` and a `role`, and the result a `first_frame` (the formula's
line on what the first frame shows, `""` when the video has no formula). The first segment's role is
`opening`. A `turn` or `reopen` segment needs a visible change on its first word, the `payoff` segment
the video's strongest picture, and a segment with role `""` only its own brief. `get_video`'s
`style.picture` says how this style does each; in short:

- Opening: shot 1's subject is on screen from frame 0 (leave its `at` out), its pill or counter starting
  on the first words.
- Turn or re-opening: a new shot on its first word, or a new rung, level, layer or stage arriving then.
- Payoff: the biggest scale moment, its number in red.

`validate_job` returns a warning (advisory, never blocking) when a `turn`, `reopen` or `payoff` segment
has no new shot or arrival within about 0.4 s of its first word. Fix what is a real miss; say in the
handback why any warning stands.

## Inserts

If `get_timeline` shows a segment whose `insert` is not `""`, invoke the **tubematic-inserts** skill
and follow it: it places one insert inside each marked segment and has its data written with the
insert style's skill. This style dips to black into and out of an insert. The world is hidden while an
insert plays, so inside each insert's window no shot starts, no lens or push transition runs, and
nothing arrives. Start the next shot on the window's end (its last frame + 1), so the video comes back
on a new picture, or let the shot from before the insert carry on. The "never still" rule does not
count a window. With no marked segment, write no `inserts`.

## Step 5 — write, validate, submit

1. `write_scene_config(video_id, config)` with `totalFrames` from the timeline, `"canvas": "dark"` (or
   leave it out), the one scene and any `inserts`. Fix every problem it reports.
2. `validate_job(video_id)`: fix its errors, then read its `warnings`. The text audit measures the pills
   and readouts in a browser; an overlap is a measurement, so shorten the text it names.
3. Before submit_render: check the opening, the turn and the payoff shots against the narration once
   more (every number on screen matches what is said, and the red one is the one that lands).
4. `submit_render(video_id)`.

In the handback, say which shot kinds you used, which props you drew yourself, and any warning you left
and why.

## Revising

Read the comments on `get_video`. A comment about a shot, a number, a pill or the timing is fixed in
`props.flatVector`; a comment about a drawing of yours is fixed in its file (look at it again with
`render_style_parts`). Then write, validate and submit again as above. Never change the video's style.
If the voice was redone, the word frames have changed: re-time every shot and every arrival from the new
timeline.
